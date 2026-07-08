"""
상가 매물 (프로토타입 합성 데이터)
=====================================

실제 시중 매물은 직방/네이버부동산/한방 등 유료·이용약관 제한 API가 필요하므로,
이 프로토타입에서는 지역 특성(임대료·유동·소득 지수)에 맞춰 **결정론적으로 생성한
현실적인 합성 매물**을 제공한다. 실 API 키가 생기면 for_gu()/get()가 반환하는
스키마(월세·보증금·면적·층·좌표)만 실데이터로 채우면 프론트/분석은 그대로 돈다.

각 매물은 클릭 시 그 지점 좌표로 생존 예측(survival.predict)을 돌리고,
임대료(월세+관리비) 대비 예상 월매출 비율로 '부담' 분석을 덧붙인다.
"""

from __future__ import annotations

import hashlib
import random

from . import data

# 업종별 평당 매출 배수 (회전율/객단가 차이의 대략 반영)
SALES_MULT = {
    "카페": 0.90, "디저트카페": 0.85, "한식음식점": 1.10, "치킨전문점": 1.00,
    "편의점": 1.20, "베이커리": 1.00, "호프_주점": 1.05, "분식": 0.80,
    "미용실": 0.75, "패스트푸드": 1.15,
    "일식집": 1.15, "중식당": 1.10, "고깃집": 1.25, "피자전문점": 1.05,
    "의류매장": 0.95, "화장품매장": 1.05, "꽃집": 0.70, "정육점": 1.10,
    "반려동물샵": 0.85, "휴대폰매장": 1.20, "네일샵": 0.70, "피부관리실": 0.80,
    "세탁소": 0.65, "학원": 0.90, "약국": 1.35, "자동차정비": 1.00,
    "PC방": 0.80, "노래방": 0.85, "스터디카페": 0.60, "헬스장": 0.85,
}

# (층 표시, 층 계수) — 1층 가중, 지하/상층부는 임대료·매출 계수 낮음
FLOOR_OPTIONS = [
    ("지하 1층", 0.55), ("1층", 1.0), ("1층", 1.0), ("1층", 1.0),
    ("2층", 0.62), ("2층", 0.62), ("3층", 0.48),
]

# 매물 중개사무소 이름 생성용 (프로토타입 — 실제 업체 아님)
AGENCY_PREFIX = ["으뜸", "제일", "미래", "중앙", "행복", "대박", "한신", "새롬",
                 "우리", "정든", "믿음", "365", "그린", "탑", "웰빙", "명가"]
AGENCY_SUFFIX = ["공인중개사사무소", "부동산공인중개사", "공인중개사", "부동산"]

_LISTINGS: dict[str, dict] = {}
_BY_GU: dict[str, list[dict]] = {}


def _seed(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def _rent_per_pyeong(rent_index: float, floor_factor: float) -> float:
    """평당 월세(만원) ≈ 지역 임대료 지수 × 층 계수."""
    return (3.0 + rent_index / 100.0 * 22.0) * floor_factor


def _title(gu: str, floor: str, corner: bool, area: int) -> str:
    tag = "코너 " if corner else ""
    return f"{gu} {floor} {tag}상가 · 전용 {area}평"


def _build() -> None:
    lid = 0
    for gu, d in data.DISTRICTS.items():
        rng = random.Random(_seed("listing:" + gu))
        n = 5 + int(d["commercial_intensity"] / 22)   # 5~9개
        rows = []
        for _ in range(n):
            floor_label, ff = rng.choice(FLOOR_OPTIONS)
            area = rng.randint(8, 42)
            corner = rng.random() < 0.28
            road = rng.random() < 0.62
            ppw = _rent_per_pyeong(d["rent"], ff) * (1.12 if corner else 1.0)
            rent = max(30, int(round(ppw * area / 5.0)) * 5)              # 5만원 단위
            deposit = int(round(rent * (10 + rng.random() * 5) / 10.0)) * 10
            maint = max(3, round(area * (0.3 + rng.random() * 0.35)))
            has_prem = (floor_label == "1층") and rng.random() < 0.55
            premium = (int(round(area * d["rent"] / 100.0 * (0.6 + rng.random() * 1.8))) * 10) if has_prem else 0
            lat = d["lat"] + (rng.random() - 0.5) * 0.022
            lon = d["lon"] + (rng.random() - 0.5) * 0.028
            lid += 1
            # 중개사무소명 + 지역번호 기반 전화번호 (프로토타입 데모)
            gu_core = gu.split(" ")[-1]
            agency = f"{gu_core[:-1] if gu_core[-1] in '구시군' else gu_core} {rng.choice(AGENCY_PREFIX)}{rng.choice(AGENCY_SUFFIX)}"
            code = data.area_code(gu)
            mid = rng.randint(200, 989) if code == "02" else rng.randint(200, 899)
            phone = f"{code}-{mid}-{rng.randint(1000, 9999)}"
            listing = dict(
                id=f"L{lid:04d}", gu=gu, region=data.district_region(gu),
                macro=data.district_macro(gu),
                lat=round(lat, 6), lon=round(lon, 6),
                floor=floor_label, floor_factor=ff, area_pyeong=area,
                corner=corner, road_facing=road,
                rent_manwon=rent, deposit_manwon=deposit,
                maintenance_manwon=maint, premium_manwon=premium,
                title=_title(gu, floor_label, corner, area),
                agency=agency, agency_phone=phone,
            )
            _LISTINGS[listing["id"]] = listing
            rows.append(listing)
        # 월세 낮은 순 정렬 (탐색 편의)
        rows.sort(key=lambda r: r["rent_manwon"])
        _BY_GU[gu] = rows


def for_gu(gu: str) -> list[dict]:
    return _BY_GU.get(gu, [])


def get(lid: str) -> dict | None:
    return _LISTINGS.get(lid)


def expected_sales_manwon(gu: str, industry: str, area: int, floor_factor: float) -> float:
    """이 지점·업종의 예상 월매출(만원) 근사 — 유동·소득·배후 + 면적·층·업종 배수."""
    d = data.DISTRICTS[gu]
    resident = 0.6 * d["resident_support"] + 0.4 * d["daytime_pop"]
    demand = 0.5 * d["foot_traffic"] + 0.25 * d["income"] + 0.25 * resident
    per_pyeong = 18.0 + demand / 100.0 * 82.0        # 18~100 만원/평·월
    mult = SALES_MULT.get(industry, 1.0)
    return per_pyeong * area * floor_factor * mult


def recommend(industry: str, scope: str = "전체", max_rent: int = 100000,
              max_deposit: int = 100000000, min_area: int = 0, limit: int = 8) -> list[dict]:
    """예산(최대 월세·보증금, 최소 면적) 안의 매물을 생존율 내림차순으로 추천."""
    from . import survival  # 지연 import (순환 방지)
    cands = []
    for gu, rows in _BY_GU.items():
        # scope: "전체" | 권역(수도권·충청·영남·호남·강원·제주) | 시·도명
        if scope not in ("전체", "", data.district_macro(gu), data.district_region(gu)):
            continue
        for l in rows:
            if l["rent_manwon"] > max_rent or l["deposit_manwon"] > max_deposit or l["area_pyeong"] < min_area:
                continue
            core = survival._predict_core(gu, industry, l["lat"], l["lon"])
            s36 = core["surv"][36]
            a = analyze(l, industry)
            cands.append({
                "id": l["id"], "gu": gu, "region": l["region"], "lat": l["lat"], "lon": l["lon"],
                "title": l["title"], "floor": l["floor"], "area_pyeong": l["area_pyeong"],
                "rent_manwon": l["rent_manwon"], "deposit_manwon": l["deposit_manwon"],
                "y3": round(s36 * 100, 1), "band": survival._band(s36),
                "verdict": a["verdict"], "rent_to_sales_pct": a["rent_to_sales_pct"],
            })
    # 생존율 높은 순 → 임대료 부담 낮은 순
    cands.sort(key=lambda r: (-r["y3"], r["rent_to_sales_pct"]))
    return cands[:limit]


def analyze(listing: dict, industry: str) -> dict:
    """임대료(월세+관리비) 대비 예상 월매출 비율로 부담도 분석."""
    gu = listing["gu"]
    sales = expected_sales_manwon(gu, industry, listing["area_pyeong"], listing["floor_factor"])
    fixed = listing["rent_manwon"] + listing["maintenance_manwon"]
    pct = round((fixed / sales) * 100, 1) if sales > 0 else 100.0
    if pct <= 15:
        verdict, band = "여유", "good"
    elif pct <= 22:
        verdict, band = "적정", "good"
    elif pct <= 32:
        verdict, band = "부담", "warning"
    else:
        verdict, band = "과다", "critical"
    return dict(
        expected_sales_manwon=int(round(sales)),
        monthly_fixed_manwon=fixed,
        rent_to_sales_pct=pct,
        verdict=verdict, band=band,
        note="예상 월매출 대비 고정비(월세+관리비) 비율입니다. 외식·소매업은 통상 15~25%가 적정선으로, "
             "이 비율이 높을수록 매출이 조금만 흔들려도 폐업 위험이 커집니다.",
    )


_build()
