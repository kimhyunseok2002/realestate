"""
LLM 인터페이스 레이어 (Claude CLI)
====================================

문서의 원칙 그대로: **LLM은 예측 엔진이 아니라 번역·설명·오케스트레이션 레이어**다.
survival.py 가 뱉은 숫자를 자영업자가 읽는 자연어 리포트로 옮기고, what-if 질문에
답한다. 예측(생존율 계산)에는 절대 관여하지 않는다.

- 백엔드가 로컬 Claude CLI(`claude -p`)를 서브프로세스로 호출 (키 관리 불필요).
- CLI가 없거나 실패/타임아웃이면 **규칙 기반 템플릿 리포트**로 자동 폴백 →
  LLM 없이도 서비스는 항상 동작한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from . import data

# 모델: 리포트=번역 작업이므로 균형 모델(Sonnet) 기본, 환경변수로 교체 가능
MODEL = os.environ.get("SANGKWON_LLM_MODEL", "claude-sonnet-5")
TIMEOUT = int(os.environ.get("SANGKWON_LLM_TIMEOUT", "150"))

# 리포트는 순수 텍스트 생성 — 도구 사용 차단(안전·속도)
_BLOCK_TOOLS = ["Bash", "Edit", "Write", "Read", "WebFetch", "WebSearch",
                "Glob", "Grep", "Task", "NotebookEdit"]

_SYSTEM = (
    "당신은 상권 분석 리포트를 쓰는 한국어 카피라이터입니다. "
    "입력으로 받은 '생존 예측 수치'는 이미 별도의 ML 생존분석 엔진이 계산한 값입니다. "
    "당신의 역할은 그 수치를 소상공인·창업자가 이해할 수 있는 자연어로 '번역'하는 것뿐입니다. "
    "숫자를 새로 지어내거나 스스로 생존율을 계산하지 마세요. 주어진 수치만 사용하세요. "
    "과장 없이 담백하게, 결정에 도움이 되도록 씁니다. 마크다운 헤더(#)는 쓰지 말고 "
    "짧은 문단과 '- ' 불릿만 사용하세요."
)


def _cli_path() -> str | None:
    p = os.environ.get("CLAUDE_CODE_EXECPATH")
    if p and os.path.exists(p):
        return p
    known = ("/home/kim/.vscode/extensions/anthropic.claude-code-2.1.198-linux-x64/"
             "resources/native-binary/claude")
    if os.path.exists(known):
        return known
    return shutil.which("claude")


def available() -> bool:
    return _cli_path() is not None


def _run_claude(prompt: str, timeout: int = TIMEOUT) -> str | None:
    cli = _cli_path()
    if not cli:
        return None
    args = [cli, "-p", "--output-format", "text",
            "--model", MODEL,
            "--append-system-prompt", _SYSTEM,
            "--disallowed-tools", *_BLOCK_TOOLS]
    try:
        # 중첩 세션이 프로젝트 파일을 뒤지지 않도록 중립 임시 디렉터리에서 실행
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(
                args, input=prompt, capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None
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
        f"[분석 대상] {data.district_region(inp['gu'])} {inp['gu']} · 업종: {inp['industry_label']}",
        f"[예측 생존율] 1년 {s['y1']}% / 3년 {s['y3']}% / 5년 {s['y5']}%  "
        f"(수도권 동일업종 평균 3년 {p['seoul_avg_3y']}%, 차이 {p['vs_seoul_avg_3y']:+}%p)",
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
    diff_word = ("수도권 평균보다 높습니다" if diff > 1 else
                 "수도권 평균보다 낮습니다" if diff < -1 else "수도권 평균과 비슷합니다")

    lines = []
    lines.append(
        f"{data.district_region(inp['gu'])} {inp['gu']}에서 {inp['industry_label']}의 3년 생존율은 약 {s['y3']}%로, "
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
    text = _run_claude(build_report_prompt(pred))
    if text:
        return {"text": text, "source": "claude", "model": MODEL}
    return {"text": _template_report(pred), "source": "template", "model": None}


def answer_whatif(base: dict, question: str, alt: dict | None) -> dict:
    text = _run_claude(build_whatif_prompt(base, question, alt))
    if text:
        return {"text": text, "source": "claude", "model": MODEL}
    return {"text": _template_whatif(base, question, alt), "source": "template", "model": None}
