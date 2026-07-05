"""요청 스키마 (pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# 수도권(서울+경기) 좌표 범위 — 이 밖(NaN/Inf 포함)은 422로 거절
LAT = dict(ge=36.8, le=38.4)
LON = dict(ge=126.2, le=127.9)


class PredictRequest(BaseModel):
    industry: str = Field(..., description="업종 키 (예: 카페)")
    lat: float = Field(..., **LAT)
    lon: float = Field(..., **LON)
    gu: str | None = Field(None, description="자치구. 없으면 좌표/주소로 추론")
    address: str = Field("", max_length=300)


class ReportRequest(BaseModel):
    gu: str
    industry: str
    lat: float = Field(..., **LAT)
    lon: float = Field(..., **LON)


class WhatIfRequest(BaseModel):
    gu: str
    industry: str
    lat: float = Field(..., **LAT)
    lon: float = Field(..., **LON)
    question: str = Field(..., min_length=1, max_length=500)
