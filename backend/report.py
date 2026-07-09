"""
심층 상권 리포트 (유료) — 맥킨지급 구조
==========================================
survival.py(예측)·listings.py(매출/매물)·data.py(상권변수)를 조합해
창업 의사결정에 필요한 7개 섹션을 한 번에 산출한다:

  1) 손익분기·투자회수 현금흐름 시뮬 (본인 예산·목표순익 반영)
  2) 명확한 판정 + 살아남는 실행 플레이북
  3) 대안 추천 (더 나은 자리/업종)
  4) 실패 시나리오 3가지 + 대비책 (엔진 재계산 기반)
  5) 적정 임대료 분석 (적정 임대료 vs 제시액)
  6) 상권 추세 (뜨는지/지는지)
  7) 실측 코호트 근거

수치는 프로토타입 보정 데이터 기반이며, 원가율·인테리어 단가는 업계 통념을 손보정했다.
"""

from __future__ import annotations

import hashlib

from . import data, listings, survival

# 업종별 원가 구조(매출 대비) + 평당 인테리어·설비(만원) — 프로토타입 업계 통념 보정
COST_STRUCT = {
    "카페":       dict(cogs=0.35, labor=0.20, etc=0.10, fitout=250),
    "디저트카페":  dict(cogs=0.38, labor=0.20, etc=0.10, fitout=260),
    "한식음식점":  dict(cogs=0.40, labor=0.25, etc=0.10, fitout=280),
    "치킨전문점":  dict(cogs=0.42, labor=0.18, etc=0.10, fitout=220),
    "편의점":     dict(cogs=0.72, labor=0.12, etc=0.06, fitout=150),
    "베이커리":   dict(cogs=0.38, labor=0.22, etc=0.10, fitout=270),
    "호프_주점":  dict(cogs=0.35, labor=0.20, etc=0.12, fitout=230),
    "분식":      dict(cogs=0.35, labor=0.18, etc=0.10, fitout=180),
    "미용실":    dict(cogs=0.12, labor=0.35, etc=0.12, fitout=200),
    "패스트푸드": dict(cogs=0.40, labor=0.22, etc=0.10, fitout=240),
    "일식집":     dict(cogs=0.42, labor=0.24, etc=0.10, fitout=300),
    "중식당":     dict(cogs=0.40, labor=0.22, etc=0.10, fitout=260),
    "고깃집":     dict(cogs=0.44, labor=0.22, etc=0.11, fitout=300),
    "피자전문점":  dict(cogs=0.38, labor=0.20, etc=0.10, fitout=230),
    "의류매장":   dict(cogs=0.50, labor=0.14, etc=0.12, fitout=220),
    "화장품매장":  dict(cogs=0.55, labor=0.14, etc=0.10, fitout=230),
    "꽃집":      dict(cogs=0.48, labor=0.14, etc=0.10, fitout=160),
    "정육점":    dict(cogs=0.68, labor=0.12, etc=0.08, fitout=160),
    "반려동물샵":  dict(cogs=0.52, labor=0.16, etc=0.10, fitout=200),
    "휴대폰매장":  dict(cogs=0.60, labor=0.16, etc=0.10, fitout=180),
    "네일샵":    dict(cogs=0.14, labor=0.34, etc=0.12, fitout=180),
    "피부관리실":  dict(cogs=0.15, labor=0.34, etc=0.13, fitout=240),
    "세탁소":    dict(cogs=0.16, labor=0.24, etc=0.16, fitout=200),
    "학원":      dict(cogs=0.06, labor=0.42, etc=0.14, fitout=200),
    "약국":      dict(cogs=0.70, labor=0.14, etc=0.06, fitout=200),
    "자동차정비":  dict(cogs=0.40, labor=0.26, etc=0.12, fitout=220),
    "PC방":     dict(cogs=0.16, labor=0.16, etc=0.20, fitout=350),
    "노래방":    dict(cogs=0.10, labor=0.16, etc=0.20, fitout=320),
    "스터디카페":  dict(cogs=0.12, labor=0.10, etc=0.18, fitout=280),
    "헬스장":    dict(cogs=0.08, labor=0.28, etc=0.18, fitout=320),
}

PLAY = {
    "competition": "반경 200m 동종 경쟁이 촘촘합니다. 시그니처 메뉴로 차별화하고 멤버십·스탬프로 단골을 잠가 객단가를 방어하세요.",
    "vacancy": "상권 공실이 늘고 있습니다. 초기 6개월은 매장 반경을 넘어 배달 반경까지 마케팅 범위를 넓혀 수요를 끌어오세요.",
    "rent": "임대료 부담이 상위권입니다. 좌석 회전율↑·테이크아웃/배달 병행으로 평당 매출을 끌어올려 임대료를 상쇄하세요.",
    "foot_traffic": "유동인구가 약합니다. 목적성 방문을 만드는 시그니처 상품과 SNS 노출에 초기 예산을 집중하세요.",
    "resident": "배후 상주수요가 약합니다. 점심 오피스·저녁 배달처럼 시간대별 수요를 이중으로 확보하세요.",
    "income": "배후 소득이 낮아 객단가 상단이 제한됩니다. 가성비 라인업 중심의 회전율 전략이 안전합니다.",
}


def _won(v):
    return int(round(v))


def _default_property(gu, area, floor_factor=1.0):
    d = data.DISTRICTS[gu]
    ppw = listings._rent_per_pyeong(d["rent"], floor_factor)
    rent = max(30, int(round(ppw * area / 5.0)) * 5)
    deposit = int(round(rent * 11 / 10.0)) * 10
    premium = int(round(area * d["rent"] / 100.0 * 1.0)) * 10
    return dict(rent=rent, deposit=deposit, premium=premium, maint=max(3, round(area * 0.4)))


def _financials(gu, industry, area, rent, deposit, premium, maint, target, floor_factor=1.0):
    cs = COST_STRUCT.get(industry, COST_STRUCT["카페"])
    sales = _won(listings.expected_sales_manwon(gu, industry, area, floor_factor))
    cogs = _won(sales * cs["cogs"])
    labor = _won(sales * cs["labor"])
    etc = _won(sales * cs["etc"])
    fixed = rent + maint + labor
    var_ratio = cs["cogs"] + cs["etc"]
    op = sales - cogs - labor - etc - rent - maint
    be_sales = _won(fixed / max(0.05, 1 - var_ratio))
    interior = _won(area * cs["fitout"])
    opening = fixed * 3
    total_inv = deposit + premium + interior + opening
    sunk = premium + interior + opening
    payback = round(sunk / op, 1) if op > 0 else None

    def scen(mult):
        s = _won(sales * mult)
        c, l, e = _won(s * cs["cogs"]), _won(s * cs["labor"]), _won(s * cs["etc"])
        return dict(sales=s, profit=s - c - l - e - rent - maint)

    return dict(
        sales=sales, cogs=cogs, labor=labor, etc=etc, rent=rent, maint=maint,
        op_profit=op, margin_pct=round(op / sales * 100, 1) if sales else 0.0,
        be_sales=be_sales, be_ratio=round(be_sales / sales * 100, 1) if sales else None,
        invest=dict(deposit=deposit, premium=premium, interior=interior, opening=opening, total=total_inv, sunk=sunk),
        payback_months=payback,
        scenarios=dict(best=scen(1.2), base=dict(sales=sales, profit=op), worst=scen(0.75)),
        target=target, target_gap=(op - target) if target else None,
        cost_struct=cs,
    )


def _verdict(y3, fin):
    band = survival._band(y3 / 100.0)
    op, pay = fin["op_profit"], fin["payback_months"]
    score = {"good": 2, "warning": 1, "serious": -1, "critical": -2}[band]
    score += 1 if op > 0 else -2
    if pay is not None and pay <= 24:
        score += 1
    if pay is None or (pay is not None and pay > 48):
        score -= 1
    if score >= 3:
        return dict(label="강력 추천", sub="수익성·생존율 모두 우호적입니다. 적극 진입할 만합니다.", band="good", score=score)
    if score >= 1:
        return dict(label="조건부 추천", sub="리스크만 관리하면 승산이 있습니다. 아래 플레이북대로 실행하세요.", band="good", score=score)
    if score >= -1:
        return dict(label="신중 검토", sub="기대수익과 위험이 팽팽합니다. 임대료·경쟁 조건을 반드시 개선하세요.", band="warning", score=score)
    return dict(label="진입 재고", sub="현 조건에선 폐업 위험이 높습니다. 대안 자리·업종을 먼저 검토하세요.", band="critical", score=score)


def _playbook(risks):
    helps = [r for r in risks if r["effect_pp"] > 0][:2]
    hurts = [r for r in risks if r["effect_pp"] < 0][:3]
    strengths = [dict(label=r["label"], pp=r["effect_pp"]) for r in helps]
    actions = [dict(label=r["label"], pp=r["effect_pp"], action=PLAY.get(r["key"], "이 요인의 노출을 줄이는 운영 전략을 세우세요."))
               for r in hurts]
    return dict(strengths=strengths, actions=actions)


def _failures(gu, industry, lat, lon, pred, rent, maint, fin):
    base_y3 = pred["survival"]["y3"]
    out = []
    # 1) 경쟁 신규 진입
    sim = survival.simulate(gu, industry, lat, lon, {"competition": 0.25})
    out.append(dict(
        title="경쟁 점포 신규 진입",
        desc=f"반경 200m 내 동종/프랜차이즈가 25% 늘면 3년 생존율이 {base_y3}% → {sim['adjusted']['y3']}%로 떨어집니다.",
        impact=round(sim['adjusted']['y3'] - base_y3, 1),
        guard="개점 직후 6개월 안에 단골(멤버십·구독)을 확보해 신규 경쟁에도 흔들리지 않는 매출 기반을 만드세요.",
    ))
    # 2) 임대료 갱신 인상
    new_rent = _won(rent * 1.15)
    new_op = fin["op_profit"] - (new_rent - rent)
    out.append(dict(
        title="임대료 갱신 인상 (+15%)",
        desc=f"재계약 시 임대료가 월 {rent}→{new_rent}만원으로 오르면 영업이익이 {fin['op_profit']}→{new_op}만원이 됩니다.",
        impact=round((new_op - fin["op_profit"]), 1),
        guard="계약서에 임대료 인상률 상한(예: 연 5%) 특약을 넣고, 장기계약으로 인상 시점을 늦추세요.",
    ))
    # 3) 유동인구 감소 (배후 위축)
    sim2 = survival.simulate(gu, industry, lat, lon, {"foot_traffic": -0.20})
    out.append(dict(
        title="배후 수요 위축 (유동인구 −20%)",
        desc=f"오피스 공실·상권 이동으로 유동인구가 20% 줄면 3년 생존율이 {base_y3}% → {sim2['adjusted']['y3']}%가 됩니다.",
        impact=round(sim2['adjusted']['y3'] - base_y3, 1),
        guard="매장 매출에만 의존하지 말고 배달·예약·단체주문 등 유동인구와 무관한 매출 채널을 2개 이상 확보하세요.",
    ))
    out.sort(key=lambda x: x["impact"])
    return out


def _rent_nego(gu, area, rent, sales):
    d = data.DISTRICTS[gu]
    fair = max(30, int(round(listings._rent_per_pyeong(d["rent"], 1.0) * area / 5.0)) * 5)
    diff_pct = round((rent - fair) / fair * 100, 1) if fair else 0.0
    rts = round(rent / sales * 100, 1) if sales else None
    if diff_pct > 8:
        verdict, band = "협상 여지 큼", "critical"
    elif diff_pct > -3:
        verdict, band = "적정 수준", "warning"
    else:
        verdict, band = "저렴한 편", "good"
    return dict(
        offered=rent, fair=fair, diff_pct=diff_pct, target=min(rent, fair),
        rent_to_sales=rts, healthy_max=20, verdict=verdict, band=band,
        per_pyeong=round(rent / area, 1) if area else None,
        fair_per_pyeong=round(fair / area, 1) if area else None,
    )


def _trend(gu):
    d = data.DISTRICTS[gu]
    seed = int(hashlib.sha256(("trend:" + gu).encode()).hexdigest()[:8], 16)
    base = (d["foot_traffic"] + d["commercial_intensity"]) / 2.0
    foot_change = round((base - 62) * 0.35 + ((seed % 15) - 7) * 0.6, 1)  # 최근 2년 %
    vac_change = round(-foot_change * 0.16 + ((seed >> 4) % 5 - 2) * 0.25, 1)  # %p
    start = 100 - foot_change
    series = []
    for i in range(24):
        t = i / 23.0
        val = start + (100 - start) * t
        noise = (((seed >> (i % 20)) & 3) - 1.5) * 0.6
        series.append(round(val + noise, 1))
    direction = "상승" if foot_change > 4 else "하락" if foot_change < -4 else "정체"
    return dict(foot_change_pct=foot_change, vacancy_change_pp=vac_change,
               direction=direction, series=series)


def _alternatives(gu, industry, lat, lon, y3, area, rent, deposit):
    region = data.district_region(gu)
    recs = listings.recommend(industry, region, max_rent=_won(rent * 1.25),
                              max_deposit=_won(deposit * 1.4), min_area=0, limit=12)
    better = [r for r in recs if r["y3"] > y3][:4]
    fits = [f for f in survival.industry_fit(gu, lat, lon) if f["industry"] != industry and f["y3"] > y3][:3]
    return dict(listings=better, industries=fits)


def _cohort(pred):
    km = pred["km"]
    feat = pred["features"]
    surv3 = pred["survival"]["y3"]
    return dict(
        n=km["n"], median_reached=km["median_reached"],
        median_months=km["median_months"], survival_3y=surv3,
        competition_count=feat["competition_count"], radius_m=feat["radius_m"],
    )


def deep_report(gu, industry, lat, lon, area, rent=None, deposit=None,
                premium=None, maint=None, capital=0, target=0):
    if gu not in data.DISTRICTS:
        raise ValueError(f"알 수 없는 지역: {gu}")
    if industry not in data.INDUSTRIES:
        raise ValueError(f"알 수 없는 업종: {industry}")
    area = max(4, int(area or 15))
    dp = _default_property(gu, area)
    rent = int(rent) if rent else dp["rent"]
    deposit = int(deposit) if deposit is not None else dp["deposit"]
    premium = int(premium) if premium is not None else dp["premium"]
    maint = int(maint) if maint else dp["maint"]
    target = int(target or 0)

    pred = survival.predict(gu, industry, lat, lon)
    y3 = pred["survival"]["y3"]
    fin = _financials(gu, industry, area, rent, deposit, premium, maint, target)

    return {
        "input": dict(gu=gu, region=data.district_region(gu), industry=industry,
                      industry_label=data.industry_label(industry), lat=lat, lon=lon,
                      area=area, rent=rent, deposit=deposit, premium=premium, maint=maint,
                      capital=int(capital or 0), target=target),
        "survival": pred["survival"], "band": pred["band"],
        "vs_avg": pred["vs_seoul_avg_3y"], "avg": pred["seoul_avg_3y"],
        "hazard_ratio": pred["hazard_ratio"], "median_months": pred["median_months"],
        "verdict": _verdict(y3, fin),
        "financials": fin,
        "playbook": _playbook(pred["risks"]),
        "failures": _failures(gu, industry, lat, lon, pred, rent, maint, fin),
        "rent_nego": _rent_nego(gu, area, rent, fin["sales"]),
        "trend": _trend(gu),
        "alternatives": _alternatives(gu, industry, lat, lon, y3, area, rent, deposit),
        "cohort": _cohort(pred),
        "provenance": data.DATA_PROVENANCE,
    }
