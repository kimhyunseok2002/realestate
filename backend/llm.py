"""
LLM 인터페이스 레이어 (OpenAI API)
====================================

문서의 원칙 그대로: **LLM은 예측 엔진이 아니라 번역·설명 레이어**다.
survival.py 가 뱉은 숫자를 자영업자가 읽는 자연어 리포트로 옮기고, what-if 질문에
답한다. 예측(생존율 계산)에는 절대 관여하지 않는다.

- OpenAI Chat Completions API를 HTTP(urllib)로 직접 호출한다. SDK 의존성이 없어
  **Vercel 서버리스에서도 그대로 동작**한다(로컬 CLI가 없어도 됨).
- API 키는 코드에 넣지 않고 **환경변수 OPENAI_API_KEY** 로만 읽는다.
  (로컬: 프로젝트 루트 .env 또는 export / 배포: Vercel 프로젝트 환경변수)
- 키가 없거나 호출이 실패/타임아웃이면 **규칙 기반 템플릿**으로 자동 폴백 →
  LLM 없이도 서비스는 항상 동작한다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import data

# 모델: 기본 gpt-5.5. 환경변수 SANGKWON_LLM_MODEL 로 교체 가능.
#   (더 저렴하게: gpt-5.4-mini, gpt-4o-mini 등. gpt-5.5 는 프리미엄 추론모델 $5/$30·1M토큰)
MODEL = os.environ.get("SANGKWON_LLM_MODEL", "gpt-5.5")
TIMEOUT = int(os.environ.get("SANGKWON_LLM_TIMEOUT", "60"))
# 엔드포인트(호환 게이트웨이/프록시로도 교체 가능)
OPENAI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

# GPT-5 계열·o-시리즈는 '추론모델'이라 Chat Completions 파라미터 규칙이 다르다:
#   - max_tokens 거부 → max_completion_tokens 사용 (추론+출력 토큰 합산 상한)
#   - 커스텀 temperature 거부 → 기본값(1)만 허용 (그래서 temperature 를 아예 안 보낸다)
#   - reasoning_effort(none/low/medium/high/xhigh)로 추론량 제어
# 우리 리포트는 숫자 '번역'이라 추론이 불필요 → 기본 effort='none'(비용·지연 최소).
# gpt-4o·gpt-4.1 등 구형 모델이면 종전대로 temperature+max_tokens 를 쓴다.
_REASONING = MODEL.lower().startswith(("gpt-5", "o1", "o3", "o4"))
# effort 를 빈 문자열로 두면 파라미터 자체를 생략(effort 미지원 모델 대비 이스케이프 해치).
_REASONING_EFFORT = os.environ.get("SANGKWON_LLM_REASONING_EFFORT", "none").strip()
# 추론모델은 상한이 '추론+출력' 합산이라 여유 있게. (effort=none 이면 출력만 → 넉넉함)
_MAX_OUT = int(os.environ.get("SANGKWON_LLM_MAX_TOKENS", "2048"))

_SYSTEM = (
    "당신은 상권 분석 리포트를 쓰는 한국어 카피라이터입니다. "
    "입력으로 받은 '생존 예측 수치'는 이미 별도의 ML 생존분석 엔진이 계산한 값입니다. "
    "당신의 역할은 그 수치를 소상공인·창업자가 이해할 수 있는 자연어로 '번역'하는 것뿐입니다. "
    "숫자를 새로 지어내거나 스스로 생존율을 계산하지 마세요. 주어진 수치만 사용하세요. "
    "과장 없이 담백하게, 결정에 도움이 되도록 씁니다. 마크다운 헤더(#)는 쓰지 말고 "
    "짧은 문단과 '- ' 불릿만 사용하세요."
)


def _api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def available() -> bool:
    """OPENAI_API_KEY 가 설정돼 있으면 LLM 사용 가능."""
    return bool(_api_key())


def _run_llm(prompt: str, timeout: int = TIMEOUT) -> str | None:
    """OpenAI Chat Completions 호출 → 생성 텍스트. 실패 시 None(→ 템플릿 폴백)."""
    key = _api_key()
    if not key:
        return None
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    if _REASONING:
        # GPT-5 계열: max_completion_tokens 필수, temperature 는 보내지 않음(기본1만 허용)
        payload["max_completion_tokens"] = _MAX_OUT
        if _REASONING_EFFORT:
            payload["reasoning_effort"] = _REASONING_EFFORT
    else:
        # 구형 모델(gpt-4o/4.1 등): 종전대로 temperature + max_tokens
        payload["temperature"] = 0.4
        payload["max_tokens"] = 800
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        return text.strip() or None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
        return None


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------
def _fmt_pred(p: dict) -> str:
    inp = p["input"]
    s = p["survival"]
    risks = p["risks"]
    feat = p["features"]
    lines = [
        f"[분석 대상] {data.gu_full(inp['gu'])} · 업종: {inp['industry_label']}",
        f"[예측 생존율] 1년 {s['y1']}% / 3년 {s['y3']}% / 5년 {s['y5']}%  "
        f"(전국 동일업종 평균 3년 {p['seoul_avg_3y']}%, 차이 {p['vs_seoul_avg_3y']:+}%p)",
        f"[예상 중위 생존기간] 약 {p['median_months']:.0f}개월 (위험비 HR={p['hazard_ratio']})",
        f"[상권 변수] 반경 {feat['radius_m']}m 내 동종 약 {feat['competition_count']}개, "
        f"유동인구지수 {feat['foot_traffic']}, 공실률 {feat['vacancy']}%, "
        f"임대료지수 {feat['rent']}, 배후수요지수 {feat['resident']}, 소득지수 {feat['income']}",
        "[생존율에 미친 요인 (3년 생존율 기준, %p)]",
    ]
    for r in risks:
        lines.append(f"  - {r['label']}: {r['effect_pp']:+.1f}%p ({r['direction']}) — {r['desc']}")
    lines.append(f"[유사 상권 3년 생존율] " +
                 ", ".join(f"{x['gu']} {x['survival_3y']}%" for x in p["similar"]))
    lines.append(f"[업종 계절성] {p['industry_meta']['seasonality']}")
    return "\n".join(lines)


def build_report_prompt(p: dict) -> str:
    return (
        "아래는 특정 위치·업종에 대해 ML 생존분석 엔진이 계산한 결과입니다. "
        "이 수치를 바탕으로, 창업을 고민하는 사람이 읽을 상권 리포트를 한국어로 작성하세요.\n\n"
        f"{_fmt_pred(p)}\n\n"
        "다음 순서로, 전체 250~350자 내외로 담백하게 쓰세요:\n"
        "1) 한 문장 요약(이 자리에서 이 업종의 3년 생존 전망).\n"
        "2) 생존율을 '깎는' 핵심 위험요인 1~2개와 '받쳐주는' 요인 1개를, 위 %p 수치를 근거로.\n"
        "3) 실행 제안 1가지(무엇을 바꾸면 유리해지는지).\n"
        "반드시 위 수치 범위 안에서만 말하고, 새 숫자를 지어내지 마세요."
    )


def build_whatif_prompt(base: dict, question: str, alt: dict | None) -> str:
    ctx = "[현재 시나리오]\n" + _fmt_pred(base)
    if alt is not None:
        ctx += "\n\n[비교 시나리오 — 사용자가 물어본 변경안]\n" + _fmt_pred(alt)
        task = (
            "사용자가 업종/조건 변경을 가정한 what-if 질문을 했고, 두 시나리오 모두 "
            "ML 엔진으로 다시 계산했습니다. 두 결과를 비교해 무엇이 얼마나 달라지는지 "
            "(특히 3년 생존율 차이와 그 이유를) 150~250자로 설명하세요."
        )
    else:
        task = (
            "위 예측 결과의 범위 안에서, 사용자의 질문에 150~250자로 답하세요. "
            "생존율을 새로 계산하지 말고 위 수치와 요인만 근거로 설명하세요."
        )
    return f"{ctx}\n\n[사용자 질문] {question}\n\n{task}"


# ---------------------------------------------------------------------------
# 템플릿 폴백 (LLM 없이도 동작)
# ---------------------------------------------------------------------------
def _template_report(p: dict) -> str:
    inp = p["input"]
    s = p["survival"]
    risks = p["risks"]
    hurts = [r for r in risks if r["effect_pp"] < 0][:2]
    helps = [r for r in risks if r["effect_pp"] > 0][:1]
    band_word = {"good": "비교적 안정적", "warning": "평균 수준",
                 "serious": "다소 취약", "critical": "매우 취약"}[p["band"]]
    diff = p["vs_seoul_avg_3y"]
    diff_word = ("전국 평균보다 높습니다" if diff > 1 else
                 "전국 평균보다 낮습니다" if diff < -1 else "전국 평균과 비슷합니다")

    lines = []
    lines.append(
        f"{data.gu_full(inp['gu'])}에서 {inp['industry_label']}의 3년 생존율은 약 {s['y3']}%로, "
        f"이 자리·이 업종은 {band_word}입니다. 1년 {s['y1']}%, 5년 {s['y5']}% 수준이며 "
        f"동일 업종 {diff_word}(3년 기준 {diff:+.1f}%p)."
    )
    if hurts:
        h = ", ".join(f"{r['label']}({r['effect_pp']:+.1f}%p)" for r in hurts)
        lines.append(f"- 생존율을 깎는 요인: {h}. 특히 {hurts[0]['label']}이(가) 가장 크게 작용합니다.")
    if helps:
        r = helps[0]
        lines.append(f"- 받쳐주는 요인: {r['label']}({r['effect_pp']:+.1f}%p) 이 상권의 강점입니다.")
    if hurts:
        top = hurts[0]
        tip = {
            "competition": "동일 업종이 덜 밀집한 이면 블록이나 인접 상권으로 자리를 옮기면 생존율이 개선될 여지가 있습니다.",
            "vacancy": "공실이 적은 활성 구간(코너·주동선)으로 입지를 좁히는 것이 좋습니다.",
            "rent": "임대료 부담이 큰 만큼 초기 고정비를 낮추거나 회전율 높은 콘셉트가 유리합니다.",
            "foot_traffic": "유동인구가 약하므로 배후 거주·근무 수요를 겨냥한 단골형 운영이 안전합니다.",
            "resident": "배후 수요가 약하므로 유동인구 동선의 목 좋은 자리가 필수입니다.",
            "income": "구매력이 제한적이므로 객단가를 낮춘 대중적 콘셉트가 맞습니다.",
        }.get(top["key"], "핵심 위험요인을 낮출 수 있는 입지·콘셉트 조정을 검토하세요.")
        lines.append(f"- 제안: {tip}")
    lines.append(f"({p['industry_meta']['seasonality']})")
    return "\n".join(lines)


def _template_whatif(base: dict, question: str, alt: dict | None) -> str:
    if alt is not None:
        b, a = base["survival"]["y3"], alt["survival"]["y3"]
        d = round(a - b, 1)
        verb = "높아집니다" if d > 0 else "낮아집니다" if d < 0 else "비슷합니다"
        return (
            f"같은 자리에서 업종을 {base['input']['industry_label']} → "
            f"{alt['input']['industry_label']}(으)로 바꾸면 3년 생존율이 "
            f"{b}% → {a}% 로 약 {abs(d)}%p {verb}. "
            f"가장 큰 차이는 업종별 경쟁·유동인구 민감도에서 옵니다."
        )
    top = base["risks"][0]
    return (
        f"현재 예측 범위에서 보면, 이 자리의 3년 생존율({base['survival']['y3']}%)에 "
        f"가장 크게 작용하는 요인은 {top['label']}({top['effect_pp']:+.1f}%p)입니다. "
        f"질문하신 조건은 이 요인을 얼마나 개선하느냐에 따라 결과가 달라집니다."
    )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def generate_report(pred: dict) -> dict:
    text = _run_llm(build_report_prompt(pred))
    if text:
        return {"text": text, "source": "llm", "model": MODEL}
    return {"text": _template_report(pred), "source": "template", "model": None}


def answer_whatif(base: dict, question: str, alt: dict | None) -> dict:
    text = _run_llm(build_whatif_prompt(base, question, alt))
    if text:
        return {"text": text, "source": "llm", "model": MODEL}
    return {"text": _template_whatif(base, question, alt), "source": "template", "model": None}
