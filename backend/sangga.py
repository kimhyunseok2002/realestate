"""
소상공인시장진흥공단 상가(상권)정보 API 어댑터 (공공데이터포털 sdsc2)
=====================================================================

반경 내 '실제' 상가업소를 업종별로 조회한다. 국내 소상공인 상가 커버리지가
OSM(geocode.nearby_stores)보다 압도적이라, **실점포 표시**와 **실측 경쟁밀도**의
1차 소스로 쓴다. (data.py 가 말하는 "점포 변수 : 상가정보(공공데이터포털)" 소스)

- available()           : 인증키(SANGGA_API_KEY) 존재 여부
- stores_in_radius(...) : {stores, total, source, stdr_ym} | None
- competition(...)      : {count, radius_m, source, stdr_ym} | None  (반경 내 동종 실측 개수)

인증키는 코드에 하드코딩하지 않고 환경변수(SANGGA_API_KEY, .env)에서 읽는다.
실패(키 없음·타임아웃·오류·미지원 업종)하면 None 을 돌려주어, 호출부가
합성값/OSM 로 자연스럽게 폴백하도록 설계했다. (엔진·모델 수식은 건드리지 않음)
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
TIMEOUT = 7  # 초 — API 응답이 보통 2~3.5s. 실패해도 비치명(합성/OSM 폴백)
# data.go.kr 표준 결과코드: 00=정상, 03=NODATA(반경 내 0건 — '실패'가 아니라 '0개')
OK_CODES = {"00", "03"}


def _key() -> str:
    return (os.environ.get("SANGGA_API_KEY")
            or os.environ.get("DATA_GO_KR_KEY") or "").strip()


def available() -> bool:
    return bool(_key())


# 앱 30개 업종 → sdsc2 상권업종분류 (파라미터, 코드).
#   indsSclsCd = 소분류(정밀), indsMclsCd = 중분류(포괄).  2026.03 실 API로 확인해 매핑.
#   여러 소분류에 걸치는 업종(한식/일식/중식/주점/의류/학원/스터디)은 중분류로 묶어 집계한다.
INDUSTRY_CODE: dict[str, tuple[str, str]] = {
    "카페": ("indsSclsCd", "I21201"),         # 카페
    "디저트카페": ("indsSclsCd", "I21008"),   # 아이스크림/빙수 (디저트 근사)
    "한식음식점": ("indsMclsCd", "I201"),     # 한식 전체(백반/찌개/구이/국수…)
    "치킨전문점": ("indsSclsCd", "I21006"),   # 치킨
    "편의점": ("indsSclsCd", "G20405"),       # 편의점
    "베이커리": ("indsSclsCd", "I21001"),     # 빵/도넛
    "호프_주점": ("indsMclsCd", "I211"),      # 주점 전체(호프/생맥주/요리주점…)
    "분식": ("indsSclsCd", "I21007"),         # 김밥/만두/분식
    "미용실": ("indsSclsCd", "S20701"),       # 미용실
    "패스트푸드": ("indsSclsCd", "I21004"),   # 버거
    "일식집": ("indsMclsCd", "I203"),         # 일식 전체
    "중식당": ("indsMclsCd", "I202"),         # 중식 전체
    "고깃집": ("indsSclsCd", "I20107"),       # 돼지고기 구이/찜 (대표)
    "피자전문점": ("indsSclsCd", "I21003"),   # 피자
    "의류매장": ("indsMclsCd", "G209"),       # 섬유·의복·신발 소매
    "화장품매장": ("indsSclsCd", "G21503"),   # 화장품 소매업
    "꽃집": ("indsSclsCd", "G21901"),         # 꽃집
    "정육점": ("indsSclsCd", "G20503"),       # 정육점
    "반려동물샵": ("indsSclsCd", "G22001"),   # 애완동물/애완용품 소매업
    "휴대폰매장": ("indsSclsCd", "G20802"),   # 핸드폰 소매업
    "네일샵": ("indsSclsCd", "S20703"),       # 네일숍
    "피부관리실": ("indsSclsCd", "S20702"),   # 피부 관리실
    "세탁소": ("indsSclsCd", "S20901"),       # 세탁소
    "학원": ("indsMclsCd", "P106"),           # 기타 교육(입시/외국어/예체능 학원)
    "약국": ("indsSclsCd", "G21501"),         # 약국
    "자동차정비": ("indsSclsCd", "S20301"),   # 자동차 정비소
    "PC방": ("indsSclsCd", "R10406"),         # PC방
    "노래방": ("indsSclsCd", "R10407"),       # 노래방
    "스터디카페": ("indsMclsCd", "P107"),     # 교육 지원(독서실/스터디)
    "헬스장": ("indsSclsCd", "R10307"),       # 헬스장
}


def _call(op: str, params: dict) -> dict | None:
    """sdsc2 오퍼레이션 호출 → 파싱된 JSON | None(키없음·오류·타임아웃)."""
    key = _key()
    if not key:
        return None
    qs = urllib.parse.urlencode({"serviceKey": key, "type": "json", **params})
    url = f"{BASE}/{op}?{qs}"
    raw = None
    # 최초 호출은 연결 설정으로 느릴 수 있어, 타임아웃/일시적 네트워크 오류엔 1회 재시도.
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
            break
        except (socket.timeout, TimeoutError, urllib.error.URLError):
            continue
        except Exception:
            return None
    if raw is None:
        return None
    try:
        body = json.loads(raw)
    except Exception:
        return None
    code = (body.get("header") or {}).get("resultCode")
    if code is not None and code not in OK_CODES:
        return None  # 인증키 오류(30)·호출제한(22) 등 진짜 실패만 폴백
    return body


def _items(body: dict) -> list[dict]:
    """body.items 를 항상 list 로 정규화 (단건 dict·빈 문자열 방어)."""
    its = (body.get("body") or {}).get("items")
    if isinstance(its, dict):
        return [its]
    if isinstance(its, list):
        return its
    return []


def stores_in_radius(lat: float, lon: float, industry: str,
                     radius: int = 500, want_list: bool = True,
                     limit: int = 60) -> dict | None:
    """반경 내 해당 업종 실제 상가.
    반환: {stores:[{name,lat,lon,category}], total:int, source, stdr_ym} | None.
    want_list=False 면 개수만 필요한 경우로 numOfRows=1 (경량 집계용)."""
    if not available():
        return None
    params = {
        "cx": lon, "cy": lat, "radius": int(radius),
        "numOfRows": limit if want_list else 1, "pageNo": 1,
    }
    code = INDUSTRY_CODE.get(industry)
    if code:
        params[code[0]] = code[1]
    body = _call("storeListInRadius", params)
    if body is None:
        return None
    b = body.get("body") or {}
    total = b.get("totalCount")
    stores = []
    if want_list:
        for it in _items(body):
            try:
                slat, slon = float(it["lat"]), float(it["lon"])
            except (KeyError, ValueError, TypeError):
                continue
            stores.append({
                "name": it.get("bizesNm") or "이름 미상",
                "lat": slat, "lon": slon,
                "category": it.get("indsSclsNm") or it.get("indsMclsNm") or "",
            })
    return {
        "stores": stores,
        "total": int(total) if total is not None else len(stores),
        "source": "상가정보",
        "stdr_ym": (body.get("header") or {}).get("stdrYm"),
    }


def competition(lat: float, lon: float, industry: str,
                radius: int = 200) -> dict | None:
    """반경 내 동종 점포 '실측' 개수 (경쟁밀도 표시용). | None."""
    res = stores_in_radius(lat, lon, industry, radius=radius,
                           want_list=False, limit=1)
    if res is None:
        return None
    return {"count": res["total"], "radius_m": radius,
            "source": res["source"], "stdr_ym": res["stdr_ym"]}
