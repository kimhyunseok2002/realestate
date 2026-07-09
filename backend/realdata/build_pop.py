"""
서울 상주인구·직장인구 실데이터 스냅샷 생성기
=========================================================
서울 열린데이터광장 OpenAPI '우리마을가게 상권분석서비스'에서 행정동(洞)별 분기
  - 상주인구 (VwsmAdstrdRepopW,     TOT_REPOP_CO)       → 배후 거주수요(resident_support)
  - 직장인구 (VwsmAdstrdWrcPopltnW, TOT_WRC_POPLTN_CO)  → 주간 활동인구(daytime_pop)
를 받아, 행정동코드 앞 5자리(자치구 코드)로 자치구 합계를 집계해 최신 분기 스냅샷을
backend/realdata/seoul_pop.json 으로 저장한다. (build_flpop 과 동일 패턴)

실행:  SEOUL_OPENAPI_KEY=... python3 -m backend.realdata.build_pop
서비스 구동에는 필요 없다 — 생성된 seoul_pop.json(공개 통계, 커밋 대상)만 있으면 된다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict

from backend.realdata.build_flpop import SGG_TO_GU, _to_int, _quarter_txt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "seoul_pop.json")
BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 1000

# 서비스명 → (자치구 합계에 쓸 총계 필드)
SERVICES = {
    "resident": {"service": "VwsmAdstrdRepopW", "field": "TOT_REPOP_CO"},
    "daytime": {"service": "VwsmAdstrdWrcPopltnW", "field": "TOT_WRC_POPLTN_CO"},
}


def _fetch_all(key: str, service: str) -> list[dict]:
    rows: list[dict] = []
    page, total = 1, None
    while True:
        s, e = (page - 1) * PAGE + 1, page * PAGE
        url = f"{BASE}/{key}/json/{service}/{s}/{e}/"
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        blk = body.get(service)
        if not blk:
            raise RuntimeError(f"서울 OpenAPI 응답 형식 오류({service}): {list(body)[:3]}")
        res = blk.get("RESULT", {})
        if res and res.get("CODE") not in ("INFO-000", None):
            raise RuntimeError(f"서울 OpenAPI 오류({service}): {res}")
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


def _aggregate(rows: list[dict], field: str) -> tuple[str, dict[str, int]]:
    """최신 분기를 골라 자치구 단위로 field 합산."""
    if not rows:
        raise RuntimeError("수집된 행이 없습니다.")
    latest = max(r["STDR_YYQU_CD"] for r in rows)
    agg: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["STDR_YYQU_CD"] != latest:
            continue
        gu = SGG_TO_GU.get(str(r.get("ADSTRD_CD", ""))[:5])
        if gu:
            agg[gu] += _to_int(r.get(field))
    return latest, dict(agg)


def build(key: str) -> dict:
    per_gu: dict[str, dict] = defaultdict(dict)
    quarters: dict[str, str] = {}
    for feat, spec in SERVICES.items():
        rows = _fetch_all(key, spec["service"])
        latest, agg = _aggregate(rows, spec["field"])
        quarters[feat] = latest
        for gu, v in agg.items():
            per_gu[gu][feat] = v
        print(f"[{feat}] {spec['service']} 최신 {latest} · 자치구 {len(agg)}")

    districts = {gu: {"resident_pop": vals.get("resident"),
                      "daytime_pop": vals.get("daytime"),
                      "basis": "seoul_odp"}
                 for gu, vals in sorted(per_gu.items())}
    return {
        "meta": {
            "source": "우리마을가게 상권분석서비스(상주인구·직장인구-행정동)",
            "org": "서울 열린데이터광장 OpenAPI",
            "services": {k: v["service"] for k, v in SERVICES.items()},
            "unit": "분기 인구(명) — 행정동 합계를 자치구로 집계",
            "quarter": quarters.get("resident"),
            "quarter_txt": _quarter_txt(quarters.get("resident", "")),
            "series_years": "2021~현재(분기)",
            "note": "자치구 대표값 = 자치구 소속 행정동의 총 상주인구·직장인구 합계.",
        },
        "districts": districts,
    }


def main() -> int:
    key = (os.environ.get("SEOUL_OPENAPI_KEY") or "").strip()
    if not key:
        print("환경변수 SEOUL_OPENAPI_KEY 가 필요합니다.", file=sys.stderr)
        return 2
    snap = build(key)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    m = snap["meta"]
    print(f"✔ {OUT_PATH}\n  {m['quarter_txt']} · 자치구 {len(snap['districts'])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
