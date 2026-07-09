"""
R-ONE 임대료·공실률 실데이터 스냅샷 생성기
=========================================================
한국부동산원 R-ONE OpenAPI에서 '상업용부동산 임대동향조사(소규모 상가)'의
지역별 임대료(천원/㎡)·공실률(%)을 받아, 크로스워크(rone_crosswalk)로 자치구
단위 대표값을 계산해 backend/realdata/rone_lease.json 으로 저장한다.

실행:  RONE_API_KEY=... python3 -m backend.realdata.build_rone
      (또는 .env 에 RONE_API_KEY 를 넣고 python3 -m backend.realdata.build_rone)

서비스 구동에는 이 스크립트가 필요 없다 — 생성된 rone_lease.json(공개 통계, 커밋 대상)만
있으면 된다. 새 분기 데이터로 갱신할 때만 다시 실행하면 된다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "rone_lease.json")

BASE = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
# 상업용부동산 임대동향조사 — 소규모 상가, 지역별 (2022~), 분기(QY)
TABLES = {
    "rent": {"id": "A_2024_00279", "unit": "천원/㎡"},   # 임대료
    "vacancy": {"id": "A_2024_00255", "unit": "%"},      # 공실률
}
CATEGORY = "소규모 상가"


def _fetch_all(statbl_id: str, key: str) -> list[dict]:
    """한 통계표의 전 분기·전 지역 행을 페이지네이션(최대 1000/req)으로 모두 수집."""
    rows: list[dict] = []
    page = 1
    total = None
    while True:
        url = (f"{BASE}?KEY={key}&Type=json&pIndex={page}&pSize=1000"
               f"&STATBL_ID={statbl_id}&DTACYCLE_CD=QY")
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if "RESULT" in body:  # 최상위 RESULT = 에러
            raise RuntimeError(f"R-ONE 오류({statbl_id}): {body['RESULT']}")
        page_rows: list[dict] = []
        for v in body.values():
            if isinstance(v, list):
                for blk in v:
                    if "head" in blk:
                        for h in blk["head"]:
                            if "list_total_count" in h:
                                total = h["list_total_count"]
                    if "row" in blk:
                        page_rows += blk["row"]
        rows += page_rows
        if total is None or len(rows) >= total or not page_rows:
            break
        page += 1
    return rows


def _latest_maps(rows: list[dict]) -> tuple[str, dict, dict]:
    """가장 최근 분기의 (시·도 집계, 상권 leaf) 값 맵을 만든다.
    반환: (분기ID, {시도: val}, {(시도, leaf): val})"""
    quarters = sorted({r["WRTTIME_IDTFR_ID"] for r in rows})
    latest = quarters[-1]
    sido: dict[str, float] = {}
    leaf: dict[tuple[str, str], float] = {}
    for r in rows:
        if r["WRTTIME_IDTFR_ID"] != latest:
            continue
        full = r.get("CLS_FULLNM") or ""
        parts = full.split(">")
        s = parts[0]
        if len(parts) == 1:          # 시·도 집계행
            sido[s] = r["DTA_VAL"]
        else:                        # 상권 leaf
            leaf[(s, parts[-1])] = r["DTA_VAL"]
    return latest, sido, leaf


def build() -> dict:
    key = (os.environ.get("RONE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("RONE_API_KEY 환경변수가 없습니다. .env 에 넣거나 export 하세요.")

    # data.py 는 이 스냅샷을 로드하지만(순환 아님), 여기선 자치구→시도 매핑만 필요.
    from backend import data
    from backend.realdata.rone_crosswalk import CROSSWALK

    fetched = {}
    for feat, spec in TABLES.items():
        rows = _fetch_all(spec["id"], key)
        latest, sido, leaf = _latest_maps(rows)
        fetched[feat] = {"latest": latest, "sido": sido, "leaf": leaf}
        print(f"[{feat}] {spec['id']} 최신분기 {latest} · 시도 {len(sido)} · 상권 {len(leaf)}")

    rent_latest = fetched["rent"]["latest"]
    vac_latest = fetched["vacancy"]["latest"]

    # 크로스워크 leaf 이름 검증 (API에 없는 이름 = 오탈자)
    rent_leaf = fetched["rent"]["leaf"]
    missing = []
    for gu, leaves in CROSSWALK.items():
        sido_of = data.REGION_OF.get(gu)
        for lf in leaves:
            if (sido_of, lf) not in rent_leaf:
                missing.append(f"{gu}({sido_of})→'{lf}'")
    if missing:
        print("⚠️  크로스워크에서 API와 매칭 안 되는 상권:", ", ".join(missing))

    # 자치구별 대표값 계산
    districts_out: dict[str, dict] = {}
    for gu in data.DISTRICTS:
        sido_of = data.REGION_OF.get(gu)
        leaves = CROSSWALK.get(gu, [])
        rents = [fetched["rent"]["leaf"][(sido_of, lf)]
                 for lf in leaves if (sido_of, lf) in fetched["rent"]["leaf"]]
        # 공실률 0 이하는 결측 처리 → 제외
        vacs = [fetched["vacancy"]["leaf"][(sido_of, lf)]
                for lf in leaves
                if (sido_of, lf) in fetched["vacancy"]["leaf"]
                and fetched["vacancy"]["leaf"][(sido_of, lf)] > 0]
        matched = [lf for lf in leaves if (sido_of, lf) in fetched["rent"]["leaf"]]

        rent_val = (sum(rents) / len(rents)) if rents else fetched["rent"]["sido"].get(sido_of)
        vac_val = (sum(vacs) / len(vacs)) if vacs else fetched["vacancy"]["sido"].get(sido_of)
        districts_out[gu] = {
            "rent_kwon_m2": round(rent_val, 2) if rent_val is not None else None,
            "vacancy_pct": round(vac_val, 2) if vac_val is not None else None,
            "basis": "sangkwon" if rents else "sido",
            "n_sangkwon": len(matched),
            "sangkwon": matched,
        }

    snapshot = {
        "meta": {
            "source": "한국부동산원 R-ONE 상업용부동산 임대동향조사",
            "org": "한국부동산원(REB) R-ONE OpenAPI",
            "category": CATEGORY,
            "tables": {k: v["id"] for k, v in TABLES.items()},
            "unit": {"rent": TABLES["rent"]["unit"], "vacancy": TABLES["vacancy"]["unit"]},
            "quarter": {"rent": rent_latest, "vacancy": vac_latest},
            "series_years": "2022~현재(분기)",
            "note": "임대료는 소규모 상가 기준 실측(천원/㎡), 공실률은 실측(%). "
                    "자치구 대표값 = 자치구 내 R-ONE 주요상권 평균(basis=sangkwon), "
                    "상권이 없으면 해당 시·도 평균(basis=sido).",
        },
        "sido": {
            s: {
                "rent_kwon_m2": round(fetched["rent"]["sido"][s], 2),
                "vacancy_pct": round(fetched["vacancy"]["sido"].get(s, 0), 2),
            }
            for s in fetched["rent"]["sido"]
        },
        "districts": districts_out,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    n_sang = sum(1 for d in districts_out.values() if d["basis"] == "sangkwon")
    print(f"\n✅ 저장: {OUT_PATH}")
    print(f"   자치구 {len(districts_out)}개 · 상권기반 {n_sang} · 시도폴백 {len(districts_out)-n_sang}")
    return snapshot


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "vendor"))
    sys.path.insert(0, os.path.join(HERE, "..", ".."))
    build()
