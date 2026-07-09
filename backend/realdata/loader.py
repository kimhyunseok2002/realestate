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
_FLPOP_SNAPSHOT = os.path.join(_HERE, "seoul_flpop.json")
_POP_SNAPSHOT = os.path.join(_HERE, "seoul_pop.json")
_SGIS_SNAPSHOT = os.path.join(_HERE, "sgis_pop.json")


def _load(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_snapshot() -> dict | None:
    return _load(_SNAPSHOT)


def load_flpop_snapshot() -> dict | None:
    return _load(_FLPOP_SNAPSHOT)


def load_pop_snapshot() -> dict | None:
    return _load(_POP_SNAPSHOT)


def load_sgis_snapshot() -> dict | None:
    return _load(_SGIS_SNAPSHOT)


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


def apply_flpop(districts: dict[str, dict]) -> dict | None:
    """서울 유동인구 실측 스냅샷(seoul_flpop.json)으로 자치구 foot_traffic 을 제자리 대체.

    각 서울 자치구에:
      - foot_traffic_raw   ← 실측 분기 유동인구 합계(명, 행정동 합산)
      - foot_traffic       ← 위 실측값을 0~100 지수로 재환산
      - foot_traffic_basis ← 'flpop'(서울 유동인구 실측)
    을 채운다.

    척도(scale) 주의: 이 데이터는 서울 자치구만 존재하므로, 전국 min-max로 정규화하면
    서울만 0~100 전폭을 차지해 엔진의 z-표준화(전 지역 공통)를 왜곡한다. 그래서 실측값을
    '이 자치구들이 원래 차지하던 합성 유동인구 지수 범위[lo,hi]'에 다시 매핑한다 —
    서울의 전체 분포 위치는 보존하고, 자치구 간 순서·간격만 실데이터로 바꾼다.
    경기/전국 자치구는 이 스냅샷에 없으므로 합성값을 그대로 유지한다.

    스냅샷이 없거나 매칭되는 자치구가 없으면 조용히 아무것도 안 한다(합성값 유지).
    """
    snap = load_flpop_snapshot()
    if not snap:
        return None
    dsnap: dict = snap.get("districts", {})
    targets = [(gu, d) for gu, d in districts.items()
               if dsnap.get(gu, {}).get("flpop_tot")]
    if not targets:
        return None

    # 대체 전, 이 자치구들이 차지하던 합성 지수 범위를 보존(엔진 척도 안정성)
    syn = [d["foot_traffic"] for _, d in targets]
    lo, hi = min(syn), max(syn)
    raws = [dsnap[gu]["flpop_tot"] for gu, _ in targets]
    rmin, rmax = min(raws), max(raws)
    span = (rmax - rmin) or 1.0

    for gu, d in targets:
        raw = dsnap[gu]["flpop_tot"]
        d["foot_traffic_raw"] = raw
        d["foot_traffic"] = round(lo + (hi - lo) * (raw - rmin) / span, 1)
        d["foot_traffic_basis"] = "flpop"

    meta = snap.get("meta", {})
    return {
        "applied": len(targets),
        "quarter": meta.get("quarter"),
        "quarter_txt": meta.get("quarter_txt"),
        "source": meta.get("source"),
        "org": meta.get("org"),
        "service": meta.get("service"),
        "series_years": meta.get("series_years"),
    }


def _rescale_into_synthetic(targets, feat_key, raw_key, snap_field, dsnap):
    """서울 자치구 실측값(raw)을 '이 자치구들이 원래 차지하던 합성 지수 범위[lo,hi]'에
    다시 매핑한다(apply_flpop 과 동일한 척도 보존 전략 — 전국 z-표준화 왜곡 방지)."""
    syn = [d[feat_key] for _, d in targets]
    lo, hi = min(syn), max(syn)
    raws = [dsnap[gu][snap_field] for gu, _ in targets]
    rmin, rmax = min(raws), max(raws)
    span = (rmax - rmin) or 1.0
    for gu, d in targets:
        raw = dsnap[gu][snap_field]
        d[raw_key] = raw
        d[feat_key] = round(lo + (hi - lo) * (raw - rmin) / span, 1)


def apply_pop(districts: dict[str, dict]) -> dict | None:
    """서울 상주인구·직장인구 실측 스냅샷(seoul_pop.json)으로 자치구의
    resident_support(배후 거주수요)·daytime_pop(주간 활동인구)을 제자리 대체.

    각 서울 자치구에:
      - resident_support ← 상주인구(실측, 합성 지수범위로 재환산) + resident_pop_raw
      - daytime_pop      ← 직장인구(실측, 재환산)                 + daytime_pop_raw
      - pop_basis        ← 'seoul_odp'
    를 채운다. 척도 보존 전략은 apply_flpop 과 동일(서울만 존재 → 전국 z-왜곡 방지).
    경기/전국 자치구는 스냅샷에 없으므로 합성값 유지.
    """
    snap = load_pop_snapshot()
    if not snap:
        return None
    dsnap: dict = snap.get("districts", {})
    res_t = [(gu, d) for gu, d in districts.items()
             if dsnap.get(gu, {}).get("resident_pop")]
    day_t = [(gu, d) for gu, d in districts.items()
             if dsnap.get(gu, {}).get("daytime_pop")]
    if not res_t and not day_t:
        return None

    if res_t:
        _rescale_into_synthetic(res_t, "resident_support", "resident_pop_raw",
                                "resident_pop", dsnap)
    if day_t:
        _rescale_into_synthetic(day_t, "daytime_pop", "daytime_pop_raw",
                                "daytime_pop", dsnap)
    touched = {gu for gu, _ in res_t} | {gu for gu, _ in day_t}
    for gu in touched:
        districts[gu]["pop_basis"] = "seoul_odp"

    meta = snap.get("meta", {})
    return {
        "applied": len(touched),
        "quarter": meta.get("quarter"),
        "quarter_txt": meta.get("quarter_txt"),
        "source": meta.get("source"),
        "org": meta.get("org"),
        "services": meta.get("services"),
        "series_years": meta.get("series_years"),
    }


def apply_sgis(districts: dict[str, dict]) -> dict | None:
    """통계청 SGIS 스냅샷(sgis_pop.json)으로 경기·전국 자치구의
    resident_support(인구)·daytime_pop(종사자수)을 제자리 대체.

    서울은 이미 열린데이터광장(apply_pop, pop_basis='seoul_odp')으로 더 최신·상세하게
    채워졌으므로 건드리지 않고, SGIS는 그 외 자치구만 담당한다. 각 자치구에:
      - resident_support ← 인구(실측, 합성 지수범위로 재환산) + resident_pop_raw
      - daytime_pop      ← 종사자수(실측, 재환산)             + daytime_pop_raw
      - pop_basis        ← 'sgis'
    척도 보존(전국 z-왜곡 방지)은 apply_flpop/apply_pop 과 동일 전략.
    """
    snap = load_sgis_snapshot()
    if not snap:
        return None
    dsnap: dict = snap.get("districts", {})
    res_t = [(gu, d) for gu, d in districts.items()
             if dsnap.get(gu, {}).get("population") and d.get("pop_basis") != "seoul_odp"]
    day_t = [(gu, d) for gu, d in districts.items()
             if dsnap.get(gu, {}).get("employees") and d.get("pop_basis") != "seoul_odp"]
    if not res_t and not day_t:
        return None

    if res_t:
        _rescale_into_synthetic(res_t, "resident_support", "resident_pop_raw",
                                "population", dsnap)
    if day_t:
        _rescale_into_synthetic(day_t, "daytime_pop", "daytime_pop_raw",
                                "employees", dsnap)
    touched = {gu for gu, _ in res_t} | {gu for gu, _ in day_t}
    for gu in touched:
        districts[gu]["pop_basis"] = "sgis"

    meta = snap.get("meta", {})
    return {
        "applied": len(touched),
        "year": meta.get("year"),
        "source": meta.get("source"),
        "org": meta.get("org"),
        "service": meta.get("service"),
    }
