"""
상권 생존 예측 엔진 (ML 코어)
=================================

이 모듈이 문서에서 말하는 **'예측 엔진'**이다. LLM은 여기서 나온 숫자를 번역할 뿐,
예측 자체는 전적으로 이 안의 생존분석 + 위험분해가 담당한다.

방법론 (교과서적 생존분석):
  1. Cox 비례위험(proportional hazards) 선형예측자
       LP = Σ βⱼ · zⱼ        (zⱼ = 표준화된 상권 변수, βⱼ = 업종별 회귀계수)
       HR = exp(LP)          (위험비, hazard ratio)
  2. Weibull 기저 생존함수
       S₀(t) = exp(-(t/scale)^shape)     shape<1 → 초기 폐업위험이 큰 '죽음의 계곡'
  3. 점포 생존함수 (비례위험)
       S(t) = S₀(t)^HR
  4. Kaplan-Meier: 동일 (구·업종) 위험모형과 정합한 합성 코호트를 생성해
       비모수 생존곡선을 실제로 추정 → '유사 점포들의 실측 생존 이력'으로 제시.
  5. 위험분해: 각 변수의 LP 기여분을 3년 생존율 변화(%p)로 환산.

실데이터로 교체 시: 위 βⱼ·scale·shape 는 인허가(생존기간)+상가정보+상권분석 데이터에
lifelines 등으로 Cox / Weibull AFT 를 적합해 얻은 계수로 그대로 바꾸면 된다.
지금은 그 계수를 data.py 에 손으로 보정해 넣은 프로토타입이다.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from . import data

Z95 = 1.9599  # 95% 정규 분위수

# 예측 지평(개월): 1년/3년/5년
HORIZONS = {12: "1년", 36: "3년", 60: "5년"}
MAX_MONTH = 60

# 표준화에 쓰는 상권 변수 이름 → 각 구에서 raw 값을 뽑는 방법
# resident(배후수요) = 거주인구 0.6 + 주간활동인구 0.4
def _district_raw(d: dict) -> dict[str, float]:
    return {
        "foot_traffic": d["foot_traffic"],
        "vacancy": d["vacancy"],
        "rent": d["rent"],
        "resident": 0.6 * d["resident_support"] + 0.4 * d["daytime_pop"],
        "income": d["income"],
        "commercial": d["commercial_intensity"],
    }


def _fit_stats() -> dict[str, tuple[float, float]]:
    """자치구 전체에 대한 각 변수의 (평균, 표준편차) — 표준화(z-score)용."""
    cols: dict[str, list[float]] = {
        "foot_traffic": [], "vacancy": [], "rent": [],
        "resident": [], "income": [], "commercial": [],
    }
    for d in data.DISTRICTS.values():
        raw = _district_raw(d)
        for k in cols:
            cols[k].append(raw[k])
    stats = {}
    for k, vals in cols.items():
        arr = np.asarray(vals, dtype=float)
        std = float(arr.std(ddof=0))
        stats[k] = (float(arr.mean()), std if std > 1e-9 else 1.0)
    return stats


_STATS = _fit_stats()


def _z(name: str, value: float) -> float:
    mean, std = _STATS[name]
    return (value - mean) / std


def _coord_jitter(lat: float, lon: float) -> float:
    """좌표를 결정론적으로 [-1, 1] 지터로 매핑 — 같은 지점은 항상 같은 값.
    한 자치구 안에서도 '번화한 코너 vs 조용한 이면도로'를 흉내내기 위함."""
    key = f"{round(lat, 4)}:{round(lon, 4)}"
    h = hashlib.sha256(key.encode()).digest()
    # 0..1 → -1..1
    u = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    return (u - 0.5) * 2.0


def _weibull_survival(t: np.ndarray | float, scale: float, shape: float, hr: float):
    """S(t) = exp(-HR·(t/scale)^shape)."""
    tt = np.asarray(t, dtype=float)
    H = hr * np.power(np.clip(tt, 0, None) / scale, shape)
    return np.exp(-H)


def _median_month(scale: float, shape: float, hr: float) -> float:
    # S(t)=0.5 → HR·(t/scale)^shape = ln2
    val = scale * (math.log(2.0) / hr) ** (1.0 / shape)
    return float(val)


def _kaplan_meier(scale: float, shape: float, hr: float, n: int, seed: int):
    """모형과 정합한 합성 코호트를 만들어 Kaplan-Meier 비모수 추정.
    반환: 계단형 (month, survival) 리스트 + 관측수 n + 중위생존(개월)."""
    rng = np.random.RandomState(seed)
    u = rng.uniform(1e-6, 1.0, size=n)
    # 역변환 표본추출: HR·(T/scale)^shape = -ln(u) → T = scale·(-ln u / HR)^(1/shape)
    fail = scale * np.power(-np.log(u) / hr, 1.0 / shape)
    # 우측 절단(right censoring): 진입시점이 제각각인 아직 영업중 점포 흉내
    cens = rng.uniform(24.0, 72.0, size=n)
    admin = float(MAX_MONTH)
    obs = np.minimum(np.minimum(fail, cens), admin)
    event = (fail <= np.minimum(cens, admin)).astype(int)

    order = np.argsort(obs)
    obs = obs[order]
    event = event[order]

    at_risk = n
    surv = 1.0
    points = [(0.0, 1.0)]
    i = 0
    median = None
    N = len(obs)
    while i < N:
        t = obs[i]
        d = 0
        c = 0
        # 동일 시점 묶음 처리
        while i < N and obs[i] == t:
            if event[i] == 1:
                d += 1
            else:
                c += 1
            i += 1
        if d > 0 and at_risk > 0:
            surv *= (1.0 - d / at_risk)
            points.append((float(t), float(surv)))
            if median is None and surv <= 0.5:
                median = float(t)
        at_risk -= (d + c)
    # 60개월까지 계단 연장
    if points[-1][0] < MAX_MONTH:
        points.append((float(MAX_MONTH), points[-1][1]))
    # 관측 구간(60개월) 안에서 생존이 0.5에 도달하지 못하면 중위생존은 '미도달'(None)
    return points, n, median


def _band(surv_at_36: float) -> str:
    """3년 생존율 → 상태 밴드 (dataviz status 팔레트에 매핑)."""
    if surv_at_36 >= 0.55:
        return "good"
    if surv_at_36 >= 0.40:
        return "warning"
    if surv_at_36 >= 0.28:
        return "serious"
    return "critical"


def local_competition(gu: str, industry: str, lat: float, lon: float):
    """지점 경쟁밀도: 반경 200m 내 동종 점포 추정 개수 + 표준화 z."""
    d = data.DISTRICTS[gu]
    ind = data.INDUSTRIES[industry]
    jitter = _coord_jitter(lat, lon)
    # 사람용 개수 추정
    base_count = ind["prevalence"] * d["commercial_intensity"] * 0.12
    count = max(1, round(base_count * (1.0 + 0.18 * jitter)))
    # z: 상업집적도 표준화 + 지점 지터를 z 공간에서 소폭 가감
    z_comp = _z("commercial", d["commercial_intensity"]) + 0.55 * jitter
    return count, z_comp, jitter


def _feature_context(gu: str, industry: str, lat: float, lon: float):
    """이 지점의 6개 상권 변수 raw 값 + z + LP 기여분."""
    d = data.DISTRICTS[gu]
    ind = data.INDUSTRIES[industry]
    raw = _district_raw(d)
    count, z_comp, jitter = local_competition(gu, industry, lat, lon)

    # (변수키, raw값, z, 회귀계수)
    comps = {
        "competition": (float(count), z_comp, ind["sens_competition"]),
        "vacancy": (raw["vacancy"], _z("vacancy", raw["vacancy"]), ind["sens_vacancy"]),
        "rent": (raw["rent"], _z("rent", raw["rent"]), ind["sens_rent"]),
        "foot_traffic": (raw["foot_traffic"], _z("foot_traffic", raw["foot_traffic"]), ind["sens_foot_traffic"]),
        "resident": (round(raw["resident"], 1), _z("resident", raw["resident"]), ind["sens_resident"]),
        "income": (raw["income"], _z("income", raw["income"]), ind["sens_income"]),
    }
    lp = sum(z * beta for (_, z, beta) in comps.values())
    return comps, lp, jitter


def _predict_core(gu: str, industry: str, lat: float, lon: float):
    """생존곡선·HR·중위생존 등 핵심 산출 (리포트/유사상권에서 재사용)."""
    ind = data.INDUSTRIES[industry]
    comps, lp, jitter = _feature_context(gu, industry, lat, lon)
    lp = float(np.clip(lp, -1.25, 1.25))
    hr = math.exp(lp)

    scale, shape = ind["scale"], ind["shape"]
    surv = {m: float(_weibull_survival(m, scale, shape, hr)) for m in HORIZONS}
    return dict(comps=comps, lp=lp, hr=hr, scale=scale, shape=shape, surv=surv)


def _risk_decomposition(comps: dict, scale: float, shape: float) -> list[dict]:
    """각 변수의 LP 기여분을 '3년 생존율 변화(%p)'로 환산."""
    s_base = float(_weibull_survival(36, scale, shape, 1.0))  # 모든 변수 평균(LP=0)
    factor_meta = {f["key"]: f for f in data.RISK_FACTORS}
    out = []
    for key, (raw, z, beta) in comps.items():
        contrib_lp = z * beta
        s_with = float(_weibull_survival(36, scale, shape, math.exp(contrib_lp)))
        effect_pp = (s_with - s_base) * 100.0
        meta = factor_meta[key]
        out.append(dict(
            key=key, label=meta["label"], desc=meta["desc"],
            value=raw, z=round(z, 3),
            effect_pp=round(effect_pp, 1),
            direction=("보호" if effect_pp >= 0 else "위험"),
        ))
    out.sort(key=lambda r: abs(r["effect_pp"]), reverse=True)
    return out


def _similar_districts(gu: str, industry: str, this_lp: float, this_s36: float):
    """같은 업종에서 위험프로파일(LP)이 가장 비슷한 상위 3개 자치구 + 서울평균."""
    ind = data.INDUSTRIES[industry]
    scale, shape = ind["scale"], ind["shape"]
    rows = []
    all_s36 = []
    for name, d in data.DISTRICTS.items():
        core = _predict_core(name, industry, d["lat"], d["lon"])
        s36 = core["surv"][36]
        all_s36.append(s36)
        if name == gu:
            continue
        rows.append(dict(gu=name, lp=core["lp"], s36=s36,
                         dist=abs(core["lp"] - this_lp)))
    rows.sort(key=lambda r: r["dist"])
    similar = [dict(gu=r["gu"], survival_3y=round(r["s36"] * 100, 1)) for r in rows[:3]]
    seoul_avg = round(float(np.mean(all_s36)) * 100, 1)
    return similar, seoul_avg


def overview(industry: str) -> list[dict]:
    """전 자치구의 3년 생존율(+밴드) — 지도 위 버블(호갱노노식) 표시용. 경량 계산."""
    if industry not in data.INDUSTRIES:
        raise ValueError(f"알 수 없는 업종: {industry}")
    out = []
    for name, d in data.DISTRICTS.items():
        core = _predict_core(name, industry, d["lat"], d["lon"])
        s36 = core["surv"][36]
        out.append({
            "gu": name, "lat": d["lat"], "lon": d["lon"],
            "y3": round(s36 * 100, 1), "band": _band(s36),
            "y1": round(core["surv"][12] * 100, 1),
            "y5": round(core["surv"][60] * 100, 1),
        })
    return out


def simulate(gu: str, industry: str, lat: float, lon: float, adj: dict) -> dict:
    """what-if 시뮬레이션: 임대료·유동인구·경쟁 밀도를 비율로 조정해 생존율 재계산.
    adj = {"rent": -0.15, "foot_traffic": 0.2, "competition": -0.25} (fractional)."""
    if gu not in data.DISTRICTS:
        raise ValueError(f"알 수 없는 지역: {gu}")
    if industry not in data.INDUSTRIES:
        raise ValueError(f"알 수 없는 업종: {industry}")
    ind = data.INDUSTRIES[industry]
    comps, lp0, _ = _feature_context(gu, industry, lat, lon)
    lp = lp0
    for key, frac in adj.items():
        if not frac or key not in comps:
            continue
        raw, z, beta = comps[key]
        if key == "competition":
            new_z = z + float(frac) * 1.2                 # 경쟁: z 절대 이동(방향 안정)
        else:
            mean, std = _STATS[key]
            new_z = (raw * (1.0 + float(frac)) - mean) / std
        lp += (new_z - z) * beta
    lp = float(np.clip(lp, -1.25, 1.25))
    hr = math.exp(lp)
    hr0 = math.exp(float(np.clip(lp0, -1.25, 1.25)))
    scale, shape = ind["scale"], ind["shape"]

    def surv(h):
        return round(float(_weibull_survival(h, scale, shape, hr)) * 100, 1)

    def base(h):
        return round(float(_weibull_survival(h, scale, shape, hr0)) * 100, 1)

    s36 = float(_weibull_survival(36, scale, shape, hr))
    return {
        "base": {"y1": base(12), "y3": base(36), "y5": base(60)},
        "adjusted": {"y1": surv(12), "y3": surv(36), "y5": surv(60)},
        "hazard_ratio": round(hr, 3), "band": _band(s36),
    }


def industry_fit(gu: str, lat: float, lon: float) -> list[dict]:
    """이 지점에서 전체 업종의 3년 생존율을 계산해 내림차순 정렬 (역방향 추천)."""
    if gu not in data.DISTRICTS:
        raise ValueError(f"알 수 없는 지역: {gu}")
    out = []
    for key in data.INDUSTRIES:
        core = _predict_core(gu, key, lat, lon)
        s36 = core["surv"][36]
        out.append(dict(
            industry=key, label=data.industry_label(key),
            y1=round(core["surv"][12] * 100, 1),
            y3=round(s36 * 100, 1),
            y5=round(core["surv"][60] * 100, 1),
            band=_band(s36), hr=round(core["hr"], 2),
        ))
    out.sort(key=lambda r: r["y3"], reverse=True)
    return out


def predict(gu: str, industry: str, lat: float, lon: float) -> dict:
    """메인 예측 엔트리포인트. app.py 가 이걸 호출한다."""
    if gu not in data.DISTRICTS:
        raise ValueError(f"알 수 없는 자치구: {gu}")
    if industry not in data.INDUSTRIES:
        raise ValueError(f"알 수 없는 업종: {industry}")

    d = data.DISTRICTS[gu]
    ind = data.INDUSTRIES[industry]
    core = _predict_core(gu, industry, lat, lon)
    comps, lp, hr, scale, shape = (core["comps"], core["lp"], core["hr"],
                                   core["scale"], core["shape"])

    # 월별 생존곡선 + 95% CI (LP 불확실성 → HR 구간)
    se_lp = 0.12 + 0.12 * (1.0 - d["commercial_intensity"] / 100.0)  # 한산한 상권일수록 넓게
    hr_hi = math.exp(lp + Z95 * se_lp)   # 위험 상단 → 생존 하단
    hr_lo = math.exp(lp - Z95 * se_lp)   # 위험 하단 → 생존 상단
    months = list(range(0, MAX_MONTH + 1))
    marr = np.asarray(months, dtype=float)
    curve = [
        dict(
            month=m,
            s=round(float(_weibull_survival(m, scale, shape, hr)) * 100, 2),
            lo=round(float(_weibull_survival(m, scale, shape, hr_hi)) * 100, 2),
            hi=round(float(_weibull_survival(m, scale, shape, hr_lo)) * 100, 2),
        )
        for m in months
    ]

    # Kaplan-Meier 합성 코호트
    n_cohort = int(60 + d["commercial_intensity"] * 1.6)
    seed = int(hashlib.sha256(f"{gu}:{industry}".encode()).hexdigest()[:8], 16) % (2**31)
    km_points, km_n, km_median = _kaplan_meier(scale, shape, hr, n_cohort, seed)
    km_curve = [dict(month=round(t, 2), s=round(s * 100, 2)) for (t, s) in km_points]
    km_reached = km_median is not None  # 60개월 내 50% 도달 여부

    # 중위 생존기간: 관측 지평(60개월)을 넘으면 클램프하고 플래그로 구분
    raw_median = _median_month(scale, shape, hr)
    median_capped = raw_median > MAX_MONTH
    median_out = round(min(raw_median, float(MAX_MONTH)), 1)

    # 위험분해 · 유사상권
    risks = _risk_decomposition(comps, scale, shape)
    similar, seoul_avg = _similar_districts(gu, industry, lp, core["surv"][36])

    survival = {
        "y1": round(core["surv"][12] * 100, 1),
        "y3": round(core["surv"][36] * 100, 1),
        "y5": round(core["surv"][60] * 100, 1),
    }
    band = _band(core["surv"][36])

    return {
        "input": {
            "gu": gu, "gu_en": d["name_en"], "industry": industry,
            "industry_label": data.industry_label(industry),
            "lat": lat, "lon": lon,
        },
        "survival": survival,
        "band": band,
        "median_months": median_out,
        "median_capped": median_capped,
        "hazard_ratio": round(hr, 3),
        "vs_seoul_avg_3y": round(survival["y3"] - seoul_avg, 1),
        "seoul_avg_3y": seoul_avg,
        "curve": curve,
        "km": {"n": km_n, "median_reached": km_reached,
               "median_months": round(km_median, 1) if km_reached else None,
               "points": km_curve},
        "risks": risks,
        "risk_note": "각 값은 해당 요인만 서울 평균으로 되돌렸을 때의 3년 생존율 변화(ceteris paribus)입니다. "
                     "비선형 모형이라 개별 효과의 단순 합은 순효과와 다를 수 있습니다.",
        "similar": similar,
        "features": {
            "competition_count": int(comps["competition"][0]),
            "radius_m": data.BASE_COMPETITION_RADIUS_M,
            "foot_traffic": comps["foot_traffic"][0],
            "vacancy": comps["vacancy"][0],
            "rent": comps["rent"][0],
            "rent_kwon_m2": d.get("rent_kwon_m2"),
            "rent_basis": d.get("rent_basis"),
            "vacancy_basis": d.get("vacancy_basis"),
            "resident": comps["resident"][0],
            "income": comps["income"][0],
        },
        "industry_meta": {
            "seasonality": ind["seasonality"],
            "invest_manwon": ind["invest_manwon"],
        },
        "provenance": data.DATA_PROVENANCE,
    }
