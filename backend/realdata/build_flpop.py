"""
서울 유동인구 실데이터 스냅샷 생성기
=========================================================
서울 열린데이터광장 OpenAPI '우리마을가게 상권분석서비스(길단위인구-행정동)'
(서비스명 VwsmAdstrdFlpopW)에서 행정동(洞)별 분기 유동인구를 받아, 행정동코드
앞 5자리(표준 자치구 코드)로 자치구 단위 합계를 집계해 최신 분기 스냅샷을
backend/realdata/seoul_flpop.json 으로 저장한다.

실행:  SEOUL_OPENAPI_KEY=... python3 -m backend.realdata.build_flpop
      (또는 .env 에 SEOUL_OPENAPI_KEY 를 넣고 python3 -m backend.realdata.build_flpop)

서비스 구동에는 이 스크립트가 필요 없다 — 생성된 seoul_flpop.json(공개 통계, 커밋 대상)만
있으면 된다. 새 분기 데이터로 갱신할 때만 다시 실행하면 된다. (build_rone 과 동일한 패턴)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "seoul_flpop.json")

SERVICE = "VwsmAdstrdFlpopW"
BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 1000  # 서울 OpenAPI 요청당 최대 행수

# 행정동코드 앞 5자리(표준 자치구 코드, SGG) → 자치구 이름 (서울 25개)
#   이 데이터셋은 자치구명을 주지 않으므로(행정동명만 제공) 코드 기준 크로스워크가 필요하다.
SGG_TO_GU: dict[str, str] = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _fetch_all(key: str) -> list[dict]:
    """전 분기·전 행정동 행을 페이지네이션(최대 1000/req)으로 모두 수집."""
    rows: list[dict] = []
    page = 1
    total = None
    while True:
        s, e = (page - 1) * PAGE + 1, page * PAGE
        url = f"{BASE}/{key}/json/{SERVICE}/{s}/{e}/"
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        blk = body.get(SERVICE)
        if not blk:  # 최상위에 서비스 키가 없으면 에러(인증/서비스명 오류 등)
            raise RuntimeError(f"서울 OpenAPI 응답 형식 오류: {list(body)[:3]} …")
        res = blk.get("RESULT", {})
        if res and res.get("CODE") not in ("INFO-000", None):
            raise RuntimeError(f"서울 OpenAPI 오류: {res}")
        if total is None:
            total = blk.get("list_total_count", 0)
        page_rows = blk.get("row", []) or []
        if not page_rows:
            break
        rows += page_rows
        if e >= total:
            break
        page += 1
    return rows


def _aggregate(rows: list[dict]) -> tuple[str, dict[str, dict]]:
    """최신 분기를 골라 자치구 단위로 유동인구를 합산."""
    if not rows:
        raise RuntimeError("수집된 행이 없습니다.")
    latest = max(r["STDR_YYQU_CD"] for r in rows)

    agg: dict[str, dict] = defaultdict(lambda: {
        "flpop_tot": 0, "ml_tot": 0, "fml_tot": 0,
        "daytime": 0, "dong_count": 0,
    })
    skipped: set[str] = set()
    for r in rows:
        if r["STDR_YYQU_CD"] != latest:
            continue
        gu = SGG_TO_GU.get(str(r.get("ADSTRD_CD", ""))[:5])
        if not gu:
            skipped.add(str(r.get("ADSTRD_CD", ""))[:5])
            continue
        a = agg[gu]
        a["flpop_tot"] += _to_int(r.get("TOT_FLPOP_CO"))
        a["ml_tot"] += _to_int(r.get("ML_FLPOP_CO"))
        a["fml_tot"] += _to_int(r.get("FML_FLPOP_CO"))
        # 주간(06~17시) = 유통/근무 활동 시간대 — 향후 daytime_pop 실측 대체용 근거값
        a["daytime"] += (_to_int(r.get("TMZON_06_11_FLPOP_CO"))
                         + _to_int(r.get("TMZON_11_14_FLPOP_CO"))
                         + _to_int(r.get("TMZON_14_17_FLPOP_CO")))
        a["dong_count"] += 1

    districts: dict[str, dict] = {}
    for gu, a in agg.items():
        tot = a["flpop_tot"]
        districts[gu] = {
            "flpop_tot": tot,
            "ml_tot": a["ml_tot"],
            "fml_tot": a["fml_tot"],
            "daytime_share": round(a["daytime"] / tot, 4) if tot else None,
            "dong_count": a["dong_count"],
            "basis": "flpop",  # 행정동 합계(실측)
        }
    if skipped:
        print(f"  (참고) 자치구 매핑 밖 코드 {sorted(skipped)} 는 건너뜀", file=sys.stderr)
    return latest, districts


def _quarter_txt(q: str) -> str:
    return f"{q[:4]}년 {q[4:]}분기" if len(q) == 5 and q[4:].isdigit() else q


def build(key: str) -> dict:
    rows = _fetch_all(key)
    latest, districts = _aggregate(rows)
    snap = {
        "meta": {
            "source": "우리마을가게 상권분석서비스(길단위인구-행정동)",
            "org": "서울 열린데이터광장 OpenAPI",
            "service": SERVICE,
            "unit": "분기 유동인구(명) — 행정동 합계를 자치구로 집계",
            "quarter": latest,
            "quarter_txt": _quarter_txt(latest),
            "series_years": "2021~현재(분기)",
            "note": ("자치구 대표 유동인구 = 자치구에 속한 행정동(ADSTRD_CD 앞 5자리=자치구코드) "
                     "TOT_FLPOP_CO 합계. 25개 자치구 전체 수록(서비스 예측단위에 있는 자치구만 주입)."),
        },
        "districts": dict(sorted(districts.items())),
    }
    return snap


def main() -> int:
    key = (os.environ.get("SEOUL_OPENAPI_KEY") or "").strip()
    if not key:
        print("환경변수 SEOUL_OPENAPI_KEY 가 필요합니다 (.env 또는 셸에 설정).", file=sys.stderr)
        return 2
    snap = build(key)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    m = snap["meta"]
    print(f"✔ {OUT_PATH}")
    print(f"  {m['quarter_txt']} · 자치구 {len(snap['districts'])}개 집계")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
