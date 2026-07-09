"""
R-ONE 실데이터 스냅샷 → DISTRICTS 주입기
=========================================================
backend/realdata/rone_lease.json(한국부동산원 실측 임대료·공실률)을 읽어
data.DISTRICTS 의 각 자치구에:
  - vacancy         ← 실측 공실률(%)          (단위 동일, 그대로 대체)
  - rent_kwon_m2    ← 실측 임대료(천원/㎡)     (표시·근거용 원값)
  - rent            ← 위 임대료를 0~100 지수로 정규화 (엔진/표시 척도 유지)
  - rent_basis / vacancy_basis ← 'sangkwon'(상권 실측) | 'sido'(시·도 평균 폴백)
을 채운다. 나머지 5개 변수(유동/배후/소득/주간/상업집적)는 아직 합성값이다.

스냅샷이 없거나 깨지면 조용히 아무것도 안 하고 합성값을 유지한다(서비스는 항상 동작).
"""

from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SNAPSHOT = os.path.join(_HERE, "rone_lease.json")


def load_snapshot() -> dict | None:
    try:
        with open(_SNAPSHOT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def apply_rone(districts: dict[str, dict]) -> dict | None:
    """DISTRICTS 를 제자리(in-place)에서 실데이터로 덮어쓴다. 적용 요약(provenance)을 반환."""
    snap = load_snapshot()
    if not snap:
        return None
    dsnap: dict = snap.get("districts", {})

    # 1) 원값(임대료 천원/㎡, 공실률 %) 주입
    applied = 0
    for gu, d in districts.items():
        rec = dsnap.get(gu)
        if not rec:
            continue
        if rec.get("rent_kwon_m2") is not None:
            d["rent_kwon_m2"] = rec["rent_kwon_m2"]
            d["rent_basis"] = rec.get("basis", "sido")
        if rec.get("vacancy_pct") is not None:
            d["vacancy"] = rec["vacancy_pct"]
            d["vacancy_basis"] = rec.get("basis", "sido")
        applied += 1

    # 2) 임대료(천원/㎡) → 0~100 지수로 전 자치구 min-max 정규화 (표시·척도 일관성 유지)
    rents = [d["rent_kwon_m2"] for d in districts.values() if d.get("rent_kwon_m2") is not None]
    if rents:
        rmin, rmax = min(rents), max(rents)
        span = (rmax - rmin) or 1.0
        for d in districts.values():
            if d.get("rent_kwon_m2") is not None:
                d["rent"] = round(25 + 75 * (d["rent_kwon_m2"] - rmin) / span, 1)

    meta = snap.get("meta", {})
    n_sang = sum(1 for r in dsnap.values() if r.get("basis") == "sangkwon")
    return {
        "applied": applied,
        "sangkwon_based": n_sang,
        "sido_fallback": applied - n_sang,
        "quarter": meta.get("quarter"),
        "source": meta.get("source"),
        "org": meta.get("org"),
        "category": meta.get("category"),
        "series_years": meta.get("series_years"),
        "tables": meta.get("tables"),
    }
