"""
지오코딩 어댑터 (OpenStreetMap Nominatim, 무료·키 불필요)
==========================================================

- geocode(query)     : 주소/상호 텍스트 → 좌표 후보들 (서울 편향)
- reverse(lat, lon)  : 좌표 → 주소 문자열
- resolve_gu(...)    : 좌표/주소 → 지원하는 서울 자치구로 매핑
                       (지원 목록 밖이면 가장 가까운 지원 자치구로 스냅)

Nominatim 정책상 초당 1요청·User-Agent 필수라 헤더를 넣고 타임아웃을 둔다.
카카오/네이버 키가 생기면 이 파일만 교체하면 된다 (인터페이스 동일).
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

from . import data

NOMINATIM = "https://nominatim.openstreetmap.org"
UA = "SangkwonSurvival/1.0 (prototype; commercial-district survival demo)"
TIMEOUT = 8

# 수도권(서울+경기) 대략 bounding box (lon_min, lat_min, lon_max, lat_max) — 검색 편향용
METRO_VIEWBOX = "125.8,33.0,129.8,38.7"


def _get(path: str, params: dict) -> list | dict:
    url = f"{NOMINATIM}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "ko"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


import re

# 지원 지역 중심에서 이 거리(m)보다 멀면 '지원 상권 밖'으로 간주(근사 안내)
SNAP_DISTANCE_M = 12000


def nearest_gu(lat: float, lon: float) -> tuple[str, float]:
    """지원 자치구 중 좌표에서 가장 가까운 곳 (중심점 기준).
    비유한 좌표는 건너뛰고, 안전하게 기본값('중구')으로 폴백."""
    best, best_d = None, float("inf")
    if math.isfinite(lat) and math.isfinite(lon):
        for name, d in data.DISTRICTS.items():
            dist = _haversine(lat, lon, d["lat"], d["lon"])
            if math.isfinite(dist) and dist < best_d:
                best, best_d = name, dist
    if best is None:  # 비유한 좌표 등 — 안전 폴백
        return "중구", float("inf")
    return best, best_d


def resolve_gu(lat: float, lon: float, address: str = "") -> dict:
    """좌표/주소를 지원 자치구로 매핑.
    - 주소에 지원 자치구명이 있으면 그걸 사용 (snapped=False)
    - 주소에 '미지원 자치구명'이 있으면 가장 가까운 지원 구로 스냅 (snapped=True)
    - 주소가 없거나(역지오코딩 실패) 구명이 없으면, 가장 가까운 지원 구를 쓰되
      중심에서 너무 멀 때만 snapped=True (역지오코딩 실패만으로 오탐하지 않음)
    """
    near, dist_m = nearest_gu(lat, lon)

    supported_match = next((name for name in data.DISTRICTS if name in address), None)
    if supported_match is not None:
        gu, snapped = supported_match, False
    else:
        gu = near
        mentioned = re.search(r"([가-힣]+구)", address or "")
        if mentioned and mentioned.group(1) not in data.DISTRICTS:
            snapped = True                       # 미지원 자치구 → 근접 지원 구로 스냅
        else:
            snapped = dist_m > SNAP_DISTANCE_M   # 주소 불명 시 거리로만 판정

    return {
        "gu": gu,
        "gu_center": {"lat": data.DISTRICTS[gu]["lat"], "lon": data.DISTRICTS[gu]["lon"]},
        "snapped": snapped,
        "nearest_distance_m": round(dist_m) if math.isfinite(dist_m) else None,
        "in_support": gu in data.DISTRICTS,
    }


def geocode(query: str, limit: int = 5) -> list[dict]:
    """주소/상호 → 좌표 후보. 서울로 편향 검색."""
    q = (query or "").strip()
    if not q:
        return []
    # 수도권(서울+경기) viewbox로 편향, 전국 결과도 허용(bounded=0)
    try:
        rows = _get("/search", {
            "q": q, "format": "jsonv2", "limit": limit,
            "countrycodes": "kr", "viewbox": METRO_VIEWBOX, "bounded": 0,
            "addressdetails": 1,
        })
    except Exception:
        rows = []
    out = []
    for r in rows:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError):
            continue
        out.append({
            "display_name": r.get("display_name", q),
            "name": r.get("name") or r.get("display_name", q),
            "lat": lat, "lon": lon,
            "type": r.get("type", ""),
        })
    return out


# ---------------------------------------------------------------------------
# 실제 점포(OSM Overpass) — 업종별 실제 가게 위치
# ---------------------------------------------------------------------------
OVERPASS = "https://overpass-api.de/api/interpreter"

OSM_STORE_TAGS = {
    "카페": ["node[amenity=cafe]"],
    "디저트카페": ["node[amenity=cafe]", "node[shop=confectionery]", "node[shop=pastry]"],
    "한식음식점": ["node[amenity=restaurant]"],
    "치킨전문점": ["node[amenity=fast_food]", "node[amenity=restaurant]"],
    "편의점": ["node[shop=convenience]"],
    "베이커리": ["node[shop=bakery]"],
    "호프_주점": ["node[amenity=pub]", "node[amenity=bar]"],
    "분식": ["node[amenity=fast_food]"],
    "미용실": ["node[shop=hairdresser]", "node[shop=beauty]"],
    "패스트푸드": ["node[amenity=fast_food]"],
    "일식집": ["node[amenity=restaurant][cuisine=japanese]", "node[amenity=restaurant][cuisine=sushi]"],
    "중식당": ["node[amenity=restaurant][cuisine=chinese]"],
    "고깃집": ["node[amenity=restaurant][cuisine=korean]", "node[amenity=restaurant][cuisine=barbecue]"],
    "피자전문점": ["node[cuisine=pizza]", "node[amenity=fast_food]"],
    "의류매장": ["node[shop=clothes]"],
    "화장품매장": ["node[shop=cosmetics]", "node[shop=chemist]"],
    "꽃집": ["node[shop=florist]"],
    "정육점": ["node[shop=butcher]"],
    "반려동물샵": ["node[shop=pet]"],
    "휴대폰매장": ["node[shop=mobile_phone]"],
    "네일샵": ["node[shop=beauty]", "node[shop=nails]"],
    "피부관리실": ["node[shop=beauty]", "node[leisure=spa]"],
    "세탁소": ["node[shop=laundry]", "node[shop=dry_cleaning]"],
    "학원": ["node[amenity=prep_school]", "node[amenity=language_school]", "node[office=educational_institution]"],
    "약국": ["node[amenity=pharmacy]"],
    "자동차정비": ["node[shop=car_repair]"],
    "PC방": ["node[amenity=internet_cafe]", "node[shop=computer]"],
    "노래방": ["node[amenity=karaoke_box]", "node[amenity=karaoke]", "node[leisure=amusement_arcade]"],
    "스터디카페": ["node[amenity=cafe]", "node[amenity=library]"],
    "헬스장": ["node[leisure=fitness_centre]", "node[leisure=sports_centre]"],
}


def nearby_stores(lat: float, lon: float, industry: str, radius: int = 700, limit: int = 60) -> list[dict]:
    """좌표 반경 내 해당 업종의 '실제' 점포(OpenStreetMap) 위치."""
    tags = OSM_STORE_TAGS.get(industry, ["node[amenity=cafe]"])
    filt = "".join(f"{t}(around:{radius},{lat},{lon});" for t in tags)
    query = f"[out:json][timeout:20];({filt});out center {limit};"
    try:
        body = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT + 14) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    out = []
    for el in j.get("elements", []):
        elat = el.get("lat") or (el.get("center") or {}).get("lat")
        elon = el.get("lon") or (el.get("center") or {}).get("lon")
        if elat is None or elon is None:
            continue
        name = (el.get("tags") or {}).get("name") or "이름 미상"
        out.append({"name": name, "lat": elat, "lon": elon})
    return out


def _empty_context(radius: int) -> dict:
    return {
        "radius_m": radius, "available": False,
        "transit": {"subway": {"count": 0, "nearest_m": None},
                    "bus": {"count": 0, "nearest_m": None},
                    "parking": {"count": 0, "nearest_m": None}},
        "anchors": {"university": 0, "hospital": 0, "mall": 0,
                    "cinema": 0, "government": 0, "school": 0},
    }


def place_context(lat: float, lon: float, radius: int = 1000) -> dict:
    """좌표 주변의 실측 입지 인프라(OSM): 교통·접근성 + 앵커/집객시설."""
    R = radius
    q = (
        f"[out:json][timeout:25];("
        f"node[railway=station](around:{R},{lat},{lon});"
        f"node[station=subway](around:{R},{lat},{lon});"
        f"node[railway=subway_entrance](around:{R},{lat},{lon});"
        f"node[highway=bus_stop](around:{R},{lat},{lon});"
        f"nwr[amenity=parking](around:{R},{lat},{lon});"
        f"nwr[amenity=university](around:{R},{lat},{lon});"
        f"nwr[amenity=college](around:{R},{lat},{lon});"
        f"nwr[amenity=hospital](around:{R},{lat},{lon});"
        f"nwr[shop=mall](around:{R},{lat},{lon});"
        f"nwr[shop=department_store](around:{R},{lat},{lon});"
        f"node[amenity=cinema](around:{R},{lat},{lon});"
        f"nwr[amenity=townhall](around:{R},{lat},{lon});"
        f"nwr[office=government](around:{R},{lat},{lon});"
        f"nwr[amenity=school](around:{R},{lat},{lon});"
        f");out center;"
    )
    try:
        body = urllib.parse.urlencode({"data": q}).encode()
        req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT + 22) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return _empty_context(radius)

    ctx = _empty_context(radius)
    ctx["available"] = True

    def upd_transit(key, elat, elon, count=True):
        t = ctx["transit"][key]
        if count:
            t["count"] += 1
        d = round(_haversine(lat, lon, elat, elon))
        if t["nearest_m"] is None or d < t["nearest_m"]:
            t["nearest_m"] = d

    for el in j.get("elements", []):
        tags = el.get("tags") or {}
        elat = el.get("lat") or (el.get("center") or {}).get("lat")
        elon = el.get("lon") or (el.get("center") or {}).get("lon")
        if elat is None or elon is None:
            continue
        if tags.get("railway") == "station" or tags.get("station") == "subway":
            upd_transit("subway", elat, elon, count=True)
        elif tags.get("railway") == "subway_entrance":
            upd_transit("subway", elat, elon, count=False)   # 출입구는 거리만
        elif tags.get("highway") == "bus_stop":
            upd_transit("bus", elat, elon)
        elif tags.get("amenity") == "parking":
            upd_transit("parking", elat, elon)
        elif tags.get("amenity") in ("university", "college"):
            ctx["anchors"]["university"] += 1
        elif tags.get("amenity") == "hospital":
            ctx["anchors"]["hospital"] += 1
        elif tags.get("shop") in ("mall", "department_store"):
            ctx["anchors"]["mall"] += 1
        elif tags.get("amenity") == "cinema":
            ctx["anchors"]["cinema"] += 1
        elif tags.get("amenity") == "townhall" or tags.get("office") == "government":
            ctx["anchors"]["government"] += 1
        elif tags.get("amenity") == "school":
            ctx["anchors"]["school"] += 1
    return ctx


def reverse(lat: float, lon: float) -> dict:
    """좌표 → 주소 문자열 (+ 지원 자치구 매핑)."""
    address_text = ""
    try:
        r = _get("/reverse", {
            "lat": lat, "lon": lon, "format": "jsonv2",
            "addressdetails": 1, "zoom": 18,
        })
        address_text = r.get("display_name", "")
    except Exception:
        address_text = ""
    resolved = resolve_gu(lat, lon, address_text)
    return {"address": address_text, "lat": lat, "lon": lon, **resolved}
