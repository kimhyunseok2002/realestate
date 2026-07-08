"""
상권 생존 예측 서비스 — FastAPI 백엔드
========================================

문서의 '오케스트레이션' 레이어: 데이터 → ML 예측 엔진 → LLM 리포트 흐름을 조율한다.
  · /api/predict  : ML 생존분석 엔진(survival.py) 실행
  · /api/report   : 예측 수치를 LLM이 자연어 리포트로 번역(llm.py)
  · /api/whatif   : 업종/조건 변경을 엔진으로 재계산 후 LLM이 비교 설명
  · /api/geocode, /api/reverse : 주소 ↔ 좌표 (geocode.py)
프론트엔드(정적 파일)도 이 앱이 함께 서빙한다.
"""

from __future__ import annotations

import os
import sys

# vendor(로컬 설치 의존성)와 프로젝트 루트를 경로에 추가 — 어디서 실행해도 import 되도록
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in (os.path.join(_BACKEND_DIR, "vendor"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import math

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import data, geocode, listings, llm, report, survival
from backend.schemas import PredictRequest, ReportRequest, WhatIfRequest

app = FastAPI(title="상권 생존 예측 서비스", version="1.0")


def _clean_nonfinite(o):
    """검증 오류 상세에 NaN/Inf 입력이 섞이면 기본 JSONResponse 직렬화가 깨지므로 정리."""
    if isinstance(o, float) and not math.isfinite(o):
        return str(o)
    if isinstance(o, dict):
        return {k: _clean_nonfinite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean_nonfinite(v) for v in o]
    return o


@app.exception_handler(RequestValidationError)
def on_validation_error(request, exc: RequestValidationError):
    # lat/lon=NaN/Inf 같은 비유한 입력이 오류 응답에 그대로 들어가 500이 나지 않도록 방어
    return JSONResponse(status_code=422,
                        content={"detail": _clean_nonfinite(jsonable_encoder(exc.errors()))})

FRONTEND_DIR = os.path.join(_ROOT, "frontend")


# ---------------------------------------------------------------------------
# 메타 / 헬스
# ---------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    districts = [
        {"gu": name, "gu_en": d["name_en"], "lat": d["lat"], "lon": d["lon"],
         "region": data.district_region(name), "macro": data.district_macro(name)}
        for name, d in data.DISTRICTS.items()
    ]
    industries = [
        {"key": k, "label": data.industry_label(k)} for k in data.INDUSTRIES
    ]
    return {
        "districts": districts,
        "industries": industries,
        "macros": data.MACROS,
        "provenance": data.DATA_PROVENANCE,
        "llm_available": llm.available(),
        "default_center": {"lat": 37.5665, "lon": 126.9780},  # 서울시청
    }


# ---------------------------------------------------------------------------
# 지오코딩
# ---------------------------------------------------------------------------
@app.get("/api/geocode")
def api_geocode(q: str = Query(..., min_length=1)):
    return {"query": q, "results": geocode.geocode(q)}


@app.get("/api/reverse")
def api_reverse(lat: float = Query(..., ge=33.0, le=38.7),
                lon: float = Query(..., ge=125.8, le=129.8)):
    return geocode.reverse(lat, lon)


@app.get("/api/overview")
def api_overview(industry: str = Query(...)):
    """전 지역 3년 생존율 — 지도 버블용."""
    if industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {industry}")
    return {"industry": industry, "industry_label": data.industry_label(industry),
            "districts": survival.overview(industry)}


# ---------------------------------------------------------------------------
# 매물
# ---------------------------------------------------------------------------
@app.get("/api/listings")
def api_listings(gu: str = Query(..., description="지역(자치구/시·군)")):
    if gu not in data.DISTRICTS:
        raise HTTPException(400, f"알 수 없는 지역: {gu}")
    return {"gu": gu, "region": data.district_region(gu), "listings": listings.for_gu(gu)}


@app.get("/api/listing/{lid}")
def api_listing(lid: str, industry: str = Query(...)):
    """매물 상세 + 그 지점 생존 예측 + 임대료 대비 매출 부담 분석."""
    lst = listings.get(lid)
    if lst is None:
        raise HTTPException(404, "매물을 찾을 수 없습니다")
    if industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {industry}")
    prediction = survival.predict(lst["gu"], industry, lst["lat"], lst["lon"])
    analysis = listings.analyze(lst, industry)
    return {"listing": lst, "analysis": analysis, "prediction": prediction}


@app.get("/api/recommend")
def api_recommend(industry: str = Query(...), scope: str = Query("전체"),
                  max_rent: int = Query(100000), max_deposit: int = Query(100000000),
                  min_area: int = Query(0), limit: int = Query(8, le=20)):
    """예산 안에서 생존율이 높은 매물 추천 (예산 기반 역추천)."""
    if industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {industry}")
    results = listings.recommend(industry, scope, max_rent, max_deposit, min_area, limit)
    return {"industry": industry, "industry_label": data.industry_label(industry),
            "scope": scope, "results": results}


# ---------------------------------------------------------------------------
# 업종 적합도 (이 자리에 어떤 업종이 오래 사나)
# ---------------------------------------------------------------------------
@app.get("/api/industry_fit")
def api_industry_fit(gu: str = Query(...),
                     lat: float = Query(..., ge=33.0, le=38.7),
                     lon: float = Query(..., ge=125.8, le=129.8)):
    if gu not in data.DISTRICTS:
        raise HTTPException(400, f"알 수 없는 지역: {gu}")
    return {"gu": gu, "region": data.district_region(gu),
            "industries": survival.industry_fit(gu, lat, lon)}


# ---------------------------------------------------------------------------
# what-if 시뮬레이터 (변수 조정 → 생존율 재계산)
# ---------------------------------------------------------------------------
@app.get("/api/whatif_sim")
def api_whatif_sim(gu: str = Query(...), industry: str = Query(...),
                   lat: float = Query(..., ge=33.0, le=38.7),
                   lon: float = Query(..., ge=125.8, le=129.8),
                   rent: float = Query(0.0, ge=-0.6, le=0.6),
                   foot: float = Query(0.0, ge=-0.6, le=0.6),
                   comp: float = Query(0.0, ge=-0.6, le=0.6)):
    if gu not in data.DISTRICTS or industry not in data.INDUSTRIES:
        raise HTTPException(400, "알 수 없는 지역/업종")
    adj = {"rent": rent, "foot_traffic": foot, "competition": comp}
    return survival.simulate(gu, industry, lat, lon, adj)


# ---------------------------------------------------------------------------
# 실제 점포 (OSM)
# ---------------------------------------------------------------------------
@app.get("/api/stores")
def api_stores(lat: float = Query(..., ge=33.0, le=38.7),
               lon: float = Query(..., ge=125.8, le=129.8),
               industry: str = Query(...), radius: int = Query(700, ge=100, le=2000)):
    if industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {industry}")
    return {"industry": industry, "radius": radius,
            "stores": geocode.nearby_stores(lat, lon, industry, radius)}


# ---------------------------------------------------------------------------
# 입지 인프라 (실측 · OSM): 교통·접근성 + 앵커/집객시설
# ---------------------------------------------------------------------------
@app.get("/api/context")
def api_context(lat: float = Query(..., ge=33.0, le=38.7),
                lon: float = Query(..., ge=125.8, le=129.8),
                radius: int = Query(1000, ge=200, le=2000)):
    return geocode.place_context(lat, lon, radius)


# ---------------------------------------------------------------------------
# 예측
# ---------------------------------------------------------------------------
def _resolve_gu(gu: str | None, lat: float, lon: float, address: str) -> tuple[str, dict]:
    if gu and gu in data.DISTRICTS:
        return gu, {"gu": gu, "snapped": False, "in_support": True}
    resolved = geocode.resolve_gu(lat, lon, address)
    return resolved["gu"], resolved


@app.post("/api/predict")
def api_predict(req: PredictRequest):
    if req.industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {req.industry}")
    gu, resolved = _resolve_gu(req.gu, req.lat, req.lon, req.address)
    try:
        result = survival.predict(gu, req.industry, req.lat, req.lon)
    except ValueError as e:
        raise HTTPException(400, str(e))
    result["resolved_gu"] = resolved
    return result


# ---------------------------------------------------------------------------
# LLM 리포트
# ---------------------------------------------------------------------------
@app.post("/api/report")
def api_report(req: ReportRequest):
    if req.gu not in data.DISTRICTS:
        raise HTTPException(400, f"알 수 없는 자치구: {req.gu}")
    if req.industry not in data.INDUSTRIES:
        raise HTTPException(400, f"알 수 없는 업종: {req.industry}")
    pred = survival.predict(req.gu, req.industry, req.lat, req.lon)
    return llm.generate_report(pred)


@app.get("/api/deep_report")
def api_deep_report(gu: str = Query(...), industry: str = Query(...),
                    lat: float = Query(..., ge=33.0, le=38.7),
                    lon: float = Query(..., ge=125.8, le=129.8),
                    area: int = Query(15, ge=4, le=200),
                    rent: int = Query(0, ge=0), deposit: int = Query(-1),
                    premium: int = Query(-1), maint: int = Query(0),
                    capital: int = Query(0, ge=0), target: int = Query(0, ge=0)):
    """유료 심층 리포트 — 손익·판정·대안·실패시나리오·임대료·추세·코호트."""
    try:
        return report.deep_report(
            gu, industry, lat, lon, area,
            rent=(rent or None), deposit=(None if deposit < 0 else deposit),
            premium=(None if premium < 0 else premium), maint=(maint or None),
            capital=capital, target=target,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/whatif")
def api_whatif(req: WhatIfRequest):
    if req.gu not in data.DISTRICTS or req.industry not in data.INDUSTRIES:
        raise HTTPException(400, "알 수 없는 자치구/업종")
    base = survival.predict(req.gu, req.industry, req.lat, req.lon)
    # 질문에서 다른 업종이 감지되면 그 시나리오를 실제로 재계산
    alt_key = data.detect_industry(req.question, exclude=req.industry)
    alt = None
    if alt_key:
        alt = survival.predict(req.gu, alt_key, req.lat, req.lon)
    ans = llm.answer_whatif(base, req.question, alt)
    ans["compared_industry"] = data.industry_label(alt_key) if alt_key else None
    if alt is not None:
        ans["alt_survival"] = alt["survival"]
        ans["base_survival"] = base["survival"]
    return ans


# ---------------------------------------------------------------------------
# 정적 프론트엔드 (API 라우트 뒤에 마운트해야 우선순위가 맞음)
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.available()}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
