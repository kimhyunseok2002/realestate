"""
상권 생존 예측 — 지역·업종 피처 데이터셋 (프로토타입)
=========================================================

이 파일의 수치는 **작동하는 프로토타입을 위한 보정된(calibrated) 합성 데이터**다.
서울 자치구의 상대적 특성(유동인구·임대료·공실률·배후수요·소득·상업밀도)과
업종별 폐업 위험 특성을, 공개적으로 알려진 서울 상권의 경향에 맞춰 손으로 보정했다.

실서비스로 넘어갈 때는 아래 소스로 이 딕셔너리들을 그대로 교체하면 된다:
  - 라벨(생존기간)   : 인허가 데이터 (공공데이터포털 / 구 LOCALDATA)
  - 점포 변수        : 상가정보 (공공데이터포털)  — 업종·좌표·경쟁밀도
  - 상권 변수        : 서울 우리마을가게 상권분석 (매출·유동인구·임대료)
  - 상권 변수        : 한국부동산원 R-ONE (임대료·공실률)
  - 배후 변수        : 통계청 SGIS (인구·사업체 일자리)

즉 스키마(필드 이름)는 유지하고 값만 실데이터로 채우면 엔진은 그대로 돈다.
"""

from __future__ import annotations

import re

# 데이터 출처 표기 (프론트/리포트에서 신뢰성 고지에 사용)
DATA_PROVENANCE = {
    "mode": "prototype",
    "note": "수치는 서울 상권 경향에 맞춰 보정한 합성 데이터입니다. "
            "실데이터(인허가·상가정보·상권분석·R-ONE·SGIS) 연결 시 값만 교체하면 됩니다.",
    "sources": [
        {"role": "라벨(생존기간)", "name": "인허가 데이터", "org": "공공데이터포털 / 구 LOCALDATA"},
        {"role": "점포 변수", "name": "상가정보", "org": "공공데이터포털"},
        {"role": "상권 변수", "name": "우리마을가게 상권분석", "org": "서울 열린데이터광장"},
        {"role": "상권 변수", "name": "부동산 임대·공실", "org": "한국부동산원 R-ONE"},
        {"role": "배후 변수", "name": "인구·사업체", "org": "통계청 SGIS"},
    ],
}

# ---------------------------------------------------------------------------
# 서울 자치구 데이터
#   지수(index)는 0~100 상대 척도, vacancy는 실제 공실률(%) 근사치.
#   - foot_traffic     : 유동인구 지수 (높을수록 유리)
#   - rent             : 임대료 지수   (높을수록 비용부담 → 불리)
#   - vacancy          : 공실률 %      (높을수록 상권 침체 → 불리)
#   - resident_support : 배후 거주인구 지수 (높을수록 유리)
#   - income           : 소득 수준 지수 (높을수록 유리, 업종별로 가중 다름)
#   - daytime_pop      : 주간 활동인구 지수 (오피스/상주 근무 → 유리)
#   - commercial_intensity : 상업 집적도 (높을수록 동종 경쟁 심함 → 경쟁밀도의 기반)
# ---------------------------------------------------------------------------
SEOUL_DISTRICTS: dict[str, dict] = {
    "강남구": dict(name_en="Gangnam-gu", lat=37.5172, lon=127.0473,
                 foot_traffic=95, rent=96, vacancy=6.8, resident_support=64,
                 income=93, daytime_pop=97, commercial_intensity=96),
    "서초구": dict(name_en="Seocho-gu", lat=37.4837, lon=127.0324,
                 foot_traffic=82, rent=90, vacancy=6.2, resident_support=66,
                 income=91, daytime_pop=88, commercial_intensity=83),
    "송파구": dict(name_en="Songpa-gu", lat=37.5145, lon=127.1059,
                 foot_traffic=80, rent=78, vacancy=6.0, resident_support=82,
                 income=80, daytime_pop=79, commercial_intensity=81),
    "마포구": dict(name_en="Mapo-gu", lat=37.5663, lon=126.9019,
                 foot_traffic=90, rent=79, vacancy=7.9, resident_support=68,
                 income=74, daytime_pop=82, commercial_intensity=90),
    "용산구": dict(name_en="Yongsan-gu", lat=37.5326, lon=126.9905,
                 foot_traffic=78, rent=83, vacancy=8.4, resident_support=60,
                 income=82, daytime_pop=80, commercial_intensity=76),
    "종로구": dict(name_en="Jongno-gu", lat=37.5730, lon=126.9794,
                 foot_traffic=85, rent=80, vacancy=9.6, resident_support=52,
                 income=72, daytime_pop=94, commercial_intensity=84),
    "중구": dict(name_en="Jung-gu", lat=37.5636, lon=126.9976,
                foot_traffic=88, rent=84, vacancy=9.9, resident_support=48,
                income=73, daytime_pop=96, commercial_intensity=87),
    "성동구": dict(name_en="Seongdong-gu", lat=37.5634, lon=127.0369,
                 foot_traffic=72, rent=72, vacancy=7.1, resident_support=70,
                 income=76, daytime_pop=71, commercial_intensity=70),
    "광진구": dict(name_en="Gwangjin-gu", lat=37.5385, lon=127.0823,
                 foot_traffic=74, rent=68, vacancy=7.4, resident_support=74,
                 income=70, daytime_pop=68, commercial_intensity=73),
    "영등포구": dict(name_en="Yeongdeungpo-gu", lat=37.5264, lon=126.8963,
                  foot_traffic=79, rent=73, vacancy=8.7, resident_support=66,
                  income=71, daytime_pop=85, commercial_intensity=80),
    "관악구": dict(name_en="Gwanak-gu", lat=37.4784, lon=126.9516,
                 foot_traffic=70, rent=58, vacancy=8.1, resident_support=78,
                 income=60, daytime_pop=62, commercial_intensity=72),
    "동작구": dict(name_en="Dongjak-gu", lat=37.5124, lon=126.9393,
                 foot_traffic=64, rent=60, vacancy=7.0, resident_support=76,
                 income=68, daytime_pop=60, commercial_intensity=62),
    "은평구": dict(name_en="Eunpyeong-gu", lat=37.6027, lon=126.9291,
                 foot_traffic=58, rent=52, vacancy=6.7, resident_support=80,
                 income=63, daytime_pop=54, commercial_intensity=55),
    "노원구": dict(name_en="Nowon-gu", lat=37.6542, lon=127.0568,
                 foot_traffic=61, rent=50, vacancy=6.4, resident_support=85,
                 income=62, daytime_pop=55, commercial_intensity=58),
    "강서구": dict(name_en="Gangseo-gu", lat=37.5509, lon=126.8495,
                 foot_traffic=66, rent=57, vacancy=7.6, resident_support=79,
                 income=67, daytime_pop=64, commercial_intensity=64),
}

# ---------------------------------------------------------------------------
# 경기도 시·군 데이터 (28시 + 3군 = 31)
#   서울과 동일 스키마·척도. 도시 특성(소득·유동·상업집적)에 맞춰 보정한 합성값.
# ---------------------------------------------------------------------------
GYEONGGI_DISTRICTS: dict[str, dict] = {
    "수원시": dict(name_en="Suwon", lat=37.2636, lon=127.0286,
                 foot_traffic=82, rent=70, vacancy=7.2, resident_support=80, income=74, daytime_pop=78, commercial_intensity=84),
    "성남시": dict(name_en="Seongnam", lat=37.4200, lon=127.1267,
                 foot_traffic=84, rent=80, vacancy=6.5, resident_support=78, income=86, daytime_pop=80, commercial_intensity=82),
    "고양시": dict(name_en="Goyang", lat=37.6584, lon=126.8320,
                 foot_traffic=74, rent=64, vacancy=7.4, resident_support=82, income=72, daytime_pop=66, commercial_intensity=72),
    "용인시": dict(name_en="Yongin", lat=37.2411, lon=127.1776,
                 foot_traffic=70, rent=66, vacancy=7.0, resident_support=84, income=82, daytime_pop=64, commercial_intensity=70),
    "부천시": dict(name_en="Bucheon", lat=37.5034, lon=126.7660,
                 foot_traffic=78, rent=63, vacancy=8.1, resident_support=79, income=66, daytime_pop=70, commercial_intensity=80),
    "안산시": dict(name_en="Ansan", lat=37.3219, lon=126.8309,
                 foot_traffic=68, rent=58, vacancy=8.6, resident_support=76, income=63, daytime_pop=72, commercial_intensity=70),
    "안양시": dict(name_en="Anyang", lat=37.3943, lon=126.9568,
                 foot_traffic=76, rent=68, vacancy=6.8, resident_support=78, income=76, daytime_pop=74, commercial_intensity=76),
    "남양주시": dict(name_en="Namyangju", lat=37.6360, lon=127.2165,
                  foot_traffic=60, rent=55, vacancy=7.3, resident_support=82, income=68, daytime_pop=54, commercial_intensity=58),
    "화성시": dict(name_en="Hwaseong", lat=37.1996, lon=126.8310,
                 foot_traffic=66, rent=62, vacancy=7.6, resident_support=80, income=78, daytime_pop=70, commercial_intensity=68),
    "평택시": dict(name_en="Pyeongtaek", lat=36.9921, lon=127.1129,
                 foot_traffic=60, rent=52, vacancy=8.9, resident_support=74, income=66, daytime_pop=66, commercial_intensity=60),
    "의정부시": dict(name_en="Uijeongbu", lat=37.7381, lon=127.0339,
                   foot_traffic=66, rent=56, vacancy=8.2, resident_support=76, income=62, daytime_pop=58, commercial_intensity=66),
    "시흥시": dict(name_en="Siheung", lat=37.3800, lon=126.8031,
                 foot_traffic=60, rent=52, vacancy=8.4, resident_support=78, income=63, daytime_pop=64, commercial_intensity=60),
    "파주시": dict(name_en="Paju", lat=37.7601, lon=126.7800,
                 foot_traffic=56, rent=50, vacancy=8.0, resident_support=78, income=66, daytime_pop=58, commercial_intensity=55),
    "김포시": dict(name_en="Gimpo", lat=37.6152, lon=126.7156,
                 foot_traffic=60, rent=55, vacancy=7.7, resident_support=80, income=70, daytime_pop=58, commercial_intensity=58),
    "광명시": dict(name_en="Gwangmyeong", lat=37.4786, lon=126.8646,
                 foot_traffic=70, rent=62, vacancy=7.1, resident_support=78, income=72, daytime_pop=64, commercial_intensity=68),
    "광주시": dict(name_en="Gwangju-si", lat=37.4293, lon=127.2550,
                 foot_traffic=56, rent=52, vacancy=7.8, resident_support=76, income=68, daytime_pop=56, commercial_intensity=55),
    "군포시": dict(name_en="Gunpo", lat=37.3616, lon=126.9352,
                 foot_traffic=68, rent=60, vacancy=6.9, resident_support=78, income=72, daytime_pop=66, commercial_intensity=66),
    "오산시": dict(name_en="Osan", lat=37.1499, lon=127.0772,
                 foot_traffic=58, rent=52, vacancy=8.3, resident_support=74, income=64, daytime_pop=60, commercial_intensity=58),
    "이천시": dict(name_en="Icheon", lat=37.2722, lon=127.4350,
                 foot_traffic=52, rent=46, vacancy=8.5, resident_support=72, income=66, daytime_pop=58, commercial_intensity=50),
    "양주시": dict(name_en="Yangju", lat=37.7852, lon=127.0458,
                 foot_traffic=52, rent=46, vacancy=8.1, resident_support=74, income=62, daytime_pop=52, commercial_intensity=50),
    "안성시": dict(name_en="Anseong", lat=37.0080, lon=127.2797,
                 foot_traffic=50, rent=44, vacancy=9.0, resident_support=70, income=62, daytime_pop=56, commercial_intensity=48),
    "구리시": dict(name_en="Guri", lat=37.5943, lon=127.1296,
                 foot_traffic=70, rent=62, vacancy=6.9, resident_support=78, income=72, daytime_pop=62, commercial_intensity=68),
    "포천시": dict(name_en="Pocheon", lat=37.8949, lon=127.2003,
                 foot_traffic=46, rent=42, vacancy=9.4, resident_support=68, income=60, daytime_pop=54, commercial_intensity=46),
    "의왕시": dict(name_en="Uiwang", lat=37.3446, lon=126.9683,
                 foot_traffic=62, rent=58, vacancy=6.8, resident_support=76, income=74, daytime_pop=58, commercial_intensity=60),
    "하남시": dict(name_en="Hanam", lat=37.5393, lon=127.2149,
                 foot_traffic=68, rent=64, vacancy=6.7, resident_support=80, income=80, daytime_pop=60, commercial_intensity=66),
    "여주시": dict(name_en="Yeoju", lat=37.2982, lon=127.6370,
                 foot_traffic=46, rent=42, vacancy=9.2, resident_support=68, income=60, daytime_pop=54, commercial_intensity=46),
    "동두천시": dict(name_en="Dongducheon", lat=37.9036, lon=127.0606,
                   foot_traffic=48, rent=42, vacancy=9.6, resident_support=66, income=56, daytime_pop=52, commercial_intensity=48),
    "과천시": dict(name_en="Gwacheon", lat=37.4292, lon=126.9878,
                 foot_traffic=62, rent=66, vacancy=6.0, resident_support=74, income=88, daytime_pop=62, commercial_intensity=58),
    "양평군": dict(name_en="Yangpyeong", lat=37.4917, lon=127.4875,
                 foot_traffic=42, rent=40, vacancy=9.0, resident_support=66, income=60, daytime_pop=50, commercial_intensity=42),
    "가평군": dict(name_en="Gapyeong", lat=37.8315, lon=127.5105,
                 foot_traffic=40, rent=38, vacancy=9.3, resident_support=62, income=58, daytime_pop=52, commercial_intensity=40),
    "연천군": dict(name_en="Yeoncheon", lat=38.0966, lon=127.0748,
                 foot_traffic=36, rent=34, vacancy=10.2, resident_support=60, income=54, daytime_pop=46, commercial_intensity=36),
}

# ---------------------------------------------------------------------------
# 전국 광역시·도 대표 도시 (수도권 외) — 동일 스키마·척도, 도시 특성에 맞춘 합성값.
#   {시·도: {대표 시/군/구: 피처}} 구조. 광역시는 도심 + 대표 자치구 몇 곳.
# ---------------------------------------------------------------------------
NATIONAL_DISTRICTS: dict[str, dict[str, dict]] = {
    "인천": {
        "인천": dict(name_en="Incheon", lat=37.4956, lon=126.7217,
                   foot_traffic=80, rent=62, vacancy=7.6, resident_support=78, income=66, daytime_pop=72, commercial_intensity=80),
        "연수구": dict(name_en="Yeonsu-gu", lat=37.4106, lon=126.6784,
                    foot_traffic=68, rent=62, vacancy=6.8, resident_support=82, income=76, daytime_pop=64, commercial_intensity=68),
        "남동구": dict(name_en="Namdong-gu", lat=37.4469, lon=126.7314,
                    foot_traffic=74, rent=58, vacancy=7.5, resident_support=82, income=66, daytime_pop=72, commercial_intensity=76),
    },
    "부산": {
        "부산": dict(name_en="Busan", lat=35.1579, lon=129.0596,
                   foot_traffic=90, rent=72, vacancy=7.4, resident_support=72, income=68, daytime_pop=82, commercial_intensity=90),
        "해운대구": dict(name_en="Haeundae-gu", lat=35.1631, lon=129.1636,
                     foot_traffic=82, rent=74, vacancy=6.9, resident_support=74, income=78, daytime_pop=70, commercial_intensity=82),
        "수영구": dict(name_en="Suyeong-gu", lat=35.1455, lon=129.1132,
                    foot_traffic=76, rent=64, vacancy=7.2, resident_support=74, income=70, daytime_pop=62, commercial_intensity=74),
    },
    "대구": {
        "대구": dict(name_en="Daegu", lat=35.8693, lon=128.5943,
                   foot_traffic=88, rent=64, vacancy=7.8, resident_support=64, income=66, daytime_pop=82, commercial_intensity=88),
        "수성구": dict(name_en="Suseong-gu", lat=35.8583, lon=128.6307,
                    foot_traffic=72, rent=64, vacancy=6.8, resident_support=82, income=80, daytime_pop=64, commercial_intensity=72),
    },
    "울산": {
        "울산": dict(name_en="Ulsan", lat=35.5384, lon=129.3114,
                   foot_traffic=74, rent=60, vacancy=7.4, resident_support=76, income=82, daytime_pop=72, commercial_intensity=74),
    },
    "경북": {
        "포항시": dict(name_en="Pohang", lat=36.0190, lon=129.3435,
                    foot_traffic=62, rent=50, vacancy=8.2, resident_support=76, income=70, daytime_pop=62, commercial_intensity=62),
        "구미시": dict(name_en="Gumi", lat=36.1196, lon=128.3446,
                    foot_traffic=60, rent=48, vacancy=8.6, resident_support=78, income=72, daytime_pop=66, commercial_intensity=60),
        "경주시": dict(name_en="Gyeongju", lat=35.8562, lon=129.2247,
                    foot_traffic=58, rent=46, vacancy=8.4, resident_support=72, income=62, daytime_pop=60, commercial_intensity=58),
    },
    "경남": {
        "창원시": dict(name_en="Changwon", lat=35.2281, lon=128.6811,
                    foot_traffic=72, rent=56, vacancy=7.6, resident_support=80, income=74, daytime_pop=70, commercial_intensity=72),
        "김해시": dict(name_en="Gimhae", lat=35.2285, lon=128.8894,
                    foot_traffic=64, rent=50, vacancy=7.8, resident_support=80, income=68, daytime_pop=62, commercial_intensity=62),
        "진주시": dict(name_en="Jinju", lat=35.1800, lon=128.1076,
                    foot_traffic=60, rent=48, vacancy=8.0, resident_support=76, income=64, daytime_pop=60, commercial_intensity=58),
    },
    "대전": {
        "대전": dict(name_en="Daejeon", lat=36.3510, lon=127.3850,
                   foot_traffic=80, rent=60, vacancy=7.2, resident_support=74, income=74, daytime_pop=74, commercial_intensity=80),
        "유성구": dict(name_en="Yuseong-gu", lat=36.3620, lon=127.3565,
                    foot_traffic=68, rent=58, vacancy=6.9, resident_support=78, income=78, daytime_pop=66, commercial_intensity=68),
    },
    "세종": {
        "세종시": dict(name_en="Sejong", lat=36.4801, lon=127.2890,
                    foot_traffic=58, rent=56, vacancy=7.0, resident_support=80, income=82, daytime_pop=60, commercial_intensity=56),
    },
    "충북": {
        "청주시": dict(name_en="Cheongju", lat=36.6424, lon=127.4890,
                    foot_traffic=66, rent=52, vacancy=7.8, resident_support=80, income=68, daytime_pop=64, commercial_intensity=66),
        "충주시": dict(name_en="Chungju", lat=36.9910, lon=127.9259,
                    foot_traffic=50, rent=42, vacancy=8.8, resident_support=72, income=60, daytime_pop=54, commercial_intensity=48),
    },
    "충남": {
        "천안시": dict(name_en="Cheonan", lat=36.8151, lon=127.1139,
                    foot_traffic=70, rent=54, vacancy=7.9, resident_support=80, income=70, daytime_pop=68, commercial_intensity=70),
        "아산시": dict(name_en="Asan", lat=36.7898, lon=127.0018,
                    foot_traffic=60, rent=50, vacancy=7.7, resident_support=80, income=74, daytime_pop=66, commercial_intensity=58),
    },
    "광주": {
        "광주": dict(name_en="Gwangju", lat=35.1495, lon=126.9199,
                   foot_traffic=84, rent=60, vacancy=7.8, resident_support=70, income=64, daytime_pop=78, commercial_intensity=84),
        "광산구": dict(name_en="Gwangsan-gu", lat=35.1397, lon=126.7938,
                    foot_traffic=68, rent=52, vacancy=7.9, resident_support=80, income=66, daytime_pop=64, commercial_intensity=66),
    },
    "전북": {
        "전주시": dict(name_en="Jeonju", lat=35.8242, lon=127.1480,
                    foot_traffic=68, rent=50, vacancy=8.0, resident_support=78, income=64, daytime_pop=64, commercial_intensity=68),
        "익산시": dict(name_en="Iksan", lat=35.9483, lon=126.9576,
                    foot_traffic=56, rent=44, vacancy=8.6, resident_support=74, income=60, daytime_pop=56, commercial_intensity=54),
        "군산시": dict(name_en="Gunsan", lat=35.9676, lon=126.7369,
                    foot_traffic=54, rent=44, vacancy=8.8, resident_support=74, income=62, daytime_pop=56, commercial_intensity=52),
    },
    "전남": {
        "여수시": dict(name_en="Yeosu", lat=34.7604, lon=127.6622,
                    foot_traffic=60, rent=48, vacancy=8.0, resident_support=72, income=64, daytime_pop=60, commercial_intensity=58),
        "순천시": dict(name_en="Suncheon", lat=34.9506, lon=127.4872,
                    foot_traffic=62, rent=48, vacancy=7.8, resident_support=76, income=64, daytime_pop=60, commercial_intensity=60),
        "목포시": dict(name_en="Mokpo", lat=34.8118, lon=126.3922,
                    foot_traffic=56, rent=44, vacancy=8.6, resident_support=72, income=60, daytime_pop=56, commercial_intensity=54),
    },
    "강원": {
        "춘천시": dict(name_en="Chuncheon", lat=37.8813, lon=127.7300,
                    foot_traffic=62, rent=50, vacancy=7.8, resident_support=74, income=64, daytime_pop=60, commercial_intensity=60),
        "원주시": dict(name_en="Wonju", lat=37.3422, lon=127.9202,
                    foot_traffic=62, rent=50, vacancy=7.9, resident_support=76, income=66, daytime_pop=62, commercial_intensity=60),
        "강릉시": dict(name_en="Gangneung", lat=37.7519, lon=128.8761,
                    foot_traffic=56, rent=46, vacancy=8.2, resident_support=70, income=62, daytime_pop=58, commercial_intensity=54),
    },
    "제주": {
        "제주시": dict(name_en="Jeju", lat=33.4996, lon=126.5312,
                    foot_traffic=70, rent=56, vacancy=7.4, resident_support=76, income=68, daytime_pop=66, commercial_intensity=68),
        "서귀포시": dict(name_en="Seogwipo", lat=33.2541, lon=126.5600,
                     foot_traffic=54, rent=46, vacancy=8.0, resident_support=70, income=62, daytime_pop=56, commercial_intensity=52),
    },
}

# 전국 통합 (예측·오버뷰·지오코딩이 이 딕셔너리를 순회한다)
DISTRICTS: dict[str, dict] = {**SEOUL_DISTRICTS, **GYEONGGI_DISTRICTS}
for _region, _units in NATIONAL_DISTRICTS.items():
    DISTRICTS.update(_units)

# 지역(시·도) 매핑 — 프론트 그룹핑/필터용
REGION_OF: dict[str, str] = {
    **{name: "서울" for name in SEOUL_DISTRICTS},
    **{name: "경기" for name in GYEONGGI_DISTRICTS},
    **{name: _region for _region, _units in NATIONAL_DISTRICTS.items() for name in _units},
}

# 권역(macro) — 스코프 필터용. 시·도를 6개 권역으로 묶는다.
MACRO_OF_REGION: dict[str, str] = {
    "서울": "수도권", "경기": "수도권", "인천": "수도권",
    "대전": "충청", "세종": "충청", "충북": "충청", "충남": "충청",
    "부산": "영남", "대구": "영남", "울산": "영남", "경북": "영남", "경남": "영남",
    "광주": "호남", "전북": "호남", "전남": "호남",
    "강원": "강원", "제주": "제주",
}
MACROS = ["수도권", "충청", "영남", "호남", "강원", "제주"]

# 지역번호 (매물 중개사무소 전화번호 생성용)
AREA_CODE: dict[str, str] = {
    "서울": "02", "경기": "031", "인천": "032", "부산": "051", "대구": "053",
    "광주": "062", "대전": "042", "울산": "052", "세종": "044", "강원": "033",
    "충북": "043", "충남": "041", "전북": "063", "전남": "061", "경북": "054",
    "경남": "055", "제주": "064",
}


def district_region(gu: str) -> str:
    return REGION_OF.get(gu, "서울")


def district_macro(gu: str) -> str:
    return MACRO_OF_REGION.get(district_region(gu), "수도권")


def area_code(gu: str) -> str:
    return AREA_CODE.get(district_region(gu), "02")


def gu_full(gu: str) -> str:
    """표시용 전체 지명. 광역시(키==시도명)일 때 '부산 부산' 이중표기 방지."""
    r = district_region(gu)
    return gu if r in gu else f"{r} {gu}"


# 반경 200m 기준, "평균 상권"에서 관측되는 동종 점포 밀도의 기준값(개).
# 개별 지점 경쟁밀도 = commercial_intensity × industry.prevalence × 지점 지터
BASE_COMPETITION_RADIUS_M = 200

# ---------------------------------------------------------------------------
# 업종 데이터
#   Weibull 기저 생존곡선 S0(t) = exp(-(t/scale)^shape),  t는 개월.
#     - shape < 1 : 초기 폐업위험이 높고 시간이 지날수록 완만 (외식업의 '죽음의 계곡')
#     - scale     : 클수록 오래 생존 (기저 수명 스케일, 개월)
#   base_survival_36 은 참고용(HR=1, 평균입지 가정 3년 생존율 근사).
#   sens_* : 표준화(z)된 상권 변수에 곱해지는 Cox 회귀계수(방향/강도).
#            (+) 계수는 위험 증가, (-) 계수는 위험 감소(=보호).
#   prevalence : 업종의 일반적 포화도(경쟁밀도 기반), 0~1.
#   invest_manwon : 평균 창업 초기투자(만원, 프로토타입 근사).
# ---------------------------------------------------------------------------
INDUSTRIES: dict[str, dict] = {
    "카페": dict(
        shape=0.85, scale=56.0, prevalence=0.95, invest_manwon=9000,
        seasonality="봄·가을 테라스 수요, 여름 아이스 음료 성수기",
        sens_competition=0.42, sens_vacancy=0.20, sens_rent=0.30,
        sens_foot_traffic=-0.34, sens_resident=-0.18, sens_income=-0.10),
    "디저트카페": dict(
        shape=0.80, scale=45.0, prevalence=0.72, invest_manwon=9500,
        seasonality="기념일·SNS 트렌드 민감, 트렌드 소멸 리스크 큼",
        sens_competition=0.40, sens_vacancy=0.18, sens_rent=0.34,
        sens_foot_traffic=-0.40, sens_resident=-0.12, sens_income=-0.22),
    "한식음식점": dict(
        shape=0.88, scale=60.0, prevalence=0.88, invest_manwon=11000,
        seasonality="점심 오피스 수요 견조, 연말 회식 성수기",
        sens_competition=0.30, sens_vacancy=0.22, sens_rent=0.28,
        sens_foot_traffic=-0.24, sens_resident=-0.26, sens_income=-0.08),
    "치킨전문점": dict(
        shape=0.90, scale=52.0, prevalence=0.90, invest_manwon=8000,
        seasonality="스포츠 이벤트·주말 배달 성수기, 배달 의존 높음",
        sens_competition=0.44, sens_vacancy=0.16, sens_rent=0.18,
        sens_foot_traffic=-0.14, sens_resident=-0.34, sens_income=-0.06),
    "편의점": dict(
        shape=1.05, scale=78.0, prevalence=0.85, invest_manwon=7000,
        seasonality="계절 변동 작음, 24시간 상주수요 기반",
        sens_competition=0.36, sens_vacancy=0.12, sens_rent=0.20,
        sens_foot_traffic=-0.30, sens_resident=-0.30, sens_income=-0.04),
    "베이커리": dict(
        shape=0.88, scale=62.0, prevalence=0.66, invest_manwon=13000,
        seasonality="아침·주말 수요, 프랜차이즈 경쟁 심함",
        sens_competition=0.34, sens_vacancy=0.18, sens_rent=0.30,
        sens_foot_traffic=-0.26, sens_resident=-0.24, sens_income=-0.14),
    "호프_주점": dict(
        shape=0.80, scale=38.0, prevalence=0.70, invest_manwon=10000,
        seasonality="야간·주말 상권, 회식·유흥 경기 민감",
        sens_competition=0.38, sens_vacancy=0.26, sens_rent=0.26,
        sens_foot_traffic=-0.36, sens_resident=-0.10, sens_income=-0.16),
    "분식": dict(
        shape=0.85, scale=50.0, prevalence=0.75, invest_manwon=5500,
        seasonality="학교·학원가 수요, 방학 비수기",
        sens_competition=0.32, sens_vacancy=0.18, sens_rent=0.22,
        sens_foot_traffic=-0.32, sens_resident=-0.22, sens_income=-0.04),
    "미용실": dict(
        shape=0.95, scale=66.0, prevalence=0.68, invest_manwon=9000,
        seasonality="계절 변동 작음, 단골·재방문 기반 안정적",
        sens_competition=0.30, sens_vacancy=0.14, sens_rent=0.24,
        sens_foot_traffic=-0.16, sens_resident=-0.34, sens_income=-0.14),
    "패스트푸드": dict(
        shape=0.90, scale=58.0, prevalence=0.62, invest_manwon=12000,
        seasonality="점심·주말 수요, 유동인구 의존 높음",
        sens_competition=0.34, sens_vacancy=0.16, sens_rent=0.26,
        sens_foot_traffic=-0.36, sens_resident=-0.16, sens_income=-0.08),
    # ── 음식 (추가) ──────────────────────────────────────────────
    "일식집": dict(
        shape=0.86, scale=54.0, prevalence=0.55, invest_manwon=14000,
        seasonality="회·초밥 여름 원가관리 중요, 연말 모임 성수기",
        sens_competition=0.32, sens_vacancy=0.20, sens_rent=0.30,
        sens_foot_traffic=-0.26, sens_resident=-0.18, sens_income=-0.20),
    "중식당": dict(
        shape=0.90, scale=62.0, prevalence=0.60, invest_manwon=12000,
        seasonality="배달 수요 견조, 졸업·이사철 성수기",
        sens_competition=0.30, sens_vacancy=0.20, sens_rent=0.24,
        sens_foot_traffic=-0.18, sens_resident=-0.30, sens_income=-0.06),
    "고깃집": dict(
        shape=0.86, scale=55.0, prevalence=0.72, invest_manwon=16000,
        seasonality="저녁·주말 회식 중심, 연말 성수기",
        sens_competition=0.34, sens_vacancy=0.22, sens_rent=0.30,
        sens_foot_traffic=-0.24, sens_resident=-0.20, sens_income=-0.16),
    "피자전문점": dict(
        shape=0.88, scale=52.0, prevalence=0.58, invest_manwon=11000,
        seasonality="주말·배달 성수기, 프랜차이즈 경쟁 심함",
        sens_competition=0.36, sens_vacancy=0.18, sens_rent=0.22,
        sens_foot_traffic=-0.18, sens_resident=-0.30, sens_income=-0.10),
    # ── 소매 ────────────────────────────────────────────────────
    "의류매장": dict(
        shape=0.80, scale=44.0, prevalence=0.70, invest_manwon=10000,
        seasonality="환절기 교체수요, 온라인·SPA 경쟁 심함",
        sens_competition=0.40, sens_vacancy=0.24, sens_rent=0.36,
        sens_foot_traffic=-0.34, sens_resident=-0.10, sens_income=-0.26),
    "화장품매장": dict(
        shape=0.82, scale=48.0, prevalence=0.60, invest_manwon=11000,
        seasonality="유동인구·관광 의존, 온라인 잠식 리스크",
        sens_competition=0.38, sens_vacancy=0.22, sens_rent=0.34,
        sens_foot_traffic=-0.34, sens_resident=-0.12, sens_income=-0.22),
    "꽃집": dict(
        shape=0.90, scale=58.0, prevalence=0.50, invest_manwon=6000,
        seasonality="졸업·기념일·5월 성수기, 계절 편차 큼",
        sens_competition=0.26, sens_vacancy=0.18, sens_rent=0.26,
        sens_foot_traffic=-0.20, sens_resident=-0.26, sens_income=-0.22),
    "정육점": dict(
        shape=0.94, scale=66.0, prevalence=0.52, invest_manwon=7000,
        seasonality="명절·주말 성수기, 배후 주거 의존 높음",
        sens_competition=0.24, sens_vacancy=0.16, sens_rent=0.22,
        sens_foot_traffic=-0.12, sens_resident=-0.40, sens_income=-0.10),
    "반려동물샵": dict(
        shape=0.88, scale=56.0, prevalence=0.44, invest_manwon=9000,
        seasonality="계절 변동 작음, 반려인구 증가로 성장세",
        sens_competition=0.28, sens_vacancy=0.18, sens_rent=0.28,
        sens_foot_traffic=-0.16, sens_resident=-0.30, sens_income=-0.24),
    "휴대폰매장": dict(
        shape=0.86, scale=50.0, prevalence=0.55, invest_manwon=8000,
        seasonality="신제품 출시기 성수기, 유동·집객 의존",
        sens_competition=0.36, sens_vacancy=0.20, sens_rent=0.30,
        sens_foot_traffic=-0.28, sens_resident=-0.16, sens_income=-0.14),
    # ── 서비스 ──────────────────────────────────────────────────
    "네일샵": dict(
        shape=0.90, scale=54.0, prevalence=0.58, invest_manwon=6000,
        seasonality="봄·여름 성수기, 단골 재방문 기반",
        sens_competition=0.32, sens_vacancy=0.16, sens_rent=0.26,
        sens_foot_traffic=-0.18, sens_resident=-0.28, sens_income=-0.24),
    "피부관리실": dict(
        shape=0.88, scale=52.0, prevalence=0.52, invest_manwon=9000,
        seasonality="환절기·연말 성수기, 경기 민감 소비재",
        sens_competition=0.30, sens_vacancy=0.16, sens_rent=0.28,
        sens_foot_traffic=-0.14, sens_resident=-0.26, sens_income=-0.30),
    "세탁소": dict(
        shape=1.00, scale=74.0, prevalence=0.48, invest_manwon=6000,
        seasonality="계절 변동 작음, 동네 밀착·재방문 안정적",
        sens_competition=0.22, sens_vacancy=0.12, sens_rent=0.20,
        sens_foot_traffic=-0.10, sens_resident=-0.44, sens_income=-0.06),
    "학원": dict(
        shape=0.95, scale=60.0, prevalence=0.66, invest_manwon=10000,
        seasonality="신학기·방학특강 성수기, 학령인구 의존",
        sens_competition=0.30, sens_vacancy=0.14, sens_rent=0.24,
        sens_foot_traffic=-0.10, sens_resident=-0.42, sens_income=-0.16),
    "약국": dict(
        shape=1.08, scale=84.0, prevalence=0.50, invest_manwon=12000,
        seasonality="환절기 성수기, 병·의원 인접·상주수요 기반 안정적",
        sens_competition=0.26, sens_vacancy=0.12, sens_rent=0.22,
        sens_foot_traffic=-0.18, sens_resident=-0.34, sens_income=-0.06),
    "자동차정비": dict(
        shape=1.00, scale=70.0, prevalence=0.42, invest_manwon=12000,
        seasonality="계절 점검 수요, 목적성 방문 위주",
        sens_competition=0.24, sens_vacancy=0.14, sens_rent=0.18,
        sens_foot_traffic=-0.08, sens_resident=-0.36, sens_income=-0.10),
    # ── 여가·오락 ───────────────────────────────────────────────
    "PC방": dict(
        shape=0.85, scale=46.0, prevalence=0.55, invest_manwon=15000,
        seasonality="방학·주말 성수기, 신작 게임 영향 큼",
        sens_competition=0.40, sens_vacancy=0.22, sens_rent=0.30,
        sens_foot_traffic=-0.30, sens_resident=-0.20, sens_income=-0.08),
    "노래방": dict(
        shape=0.82, scale=44.0, prevalence=0.58, invest_manwon=13000,
        seasonality="야간·주말·연말 성수기, 회식 경기 민감",
        sens_competition=0.38, sens_vacancy=0.26, sens_rent=0.28,
        sens_foot_traffic=-0.32, sens_resident=-0.12, sens_income=-0.12),
    "스터디카페": dict(
        shape=0.84, scale=46.0, prevalence=0.62, invest_manwon=11000,
        seasonality="시험기간 성수기, 무인운영·학생 배후 의존",
        sens_competition=0.38, sens_vacancy=0.20, sens_rent=0.32,
        sens_foot_traffic=-0.20, sens_resident=-0.32, sens_income=-0.14),
    "헬스장": dict(
        shape=0.86, scale=50.0, prevalence=0.56, invest_manwon=18000,
        seasonality="연초·여름 앞 성수기, 회원 이탈 관리 관건",
        sens_competition=0.34, sens_vacancy=0.18, sens_rent=0.34,
        sens_foot_traffic=-0.14, sens_resident=-0.34, sens_income=-0.18),
}

# 업종 표시명(언더스코어 → 슬래시 등 사람이 읽는 라벨)
INDUSTRY_LABELS = {
    "호프_주점": "호프/주점",
}


def industry_label(key: str) -> str:
    return INDUSTRY_LABELS.get(key, key)


# what-if 질문에서 업종을 감지하기 위한 동의어(자연어 → 업종키)
INDUSTRY_SYNONYMS: dict[str, list[str]] = {
    "카페": ["카페", "커피", "cafe", "커피숍", "커피전문점"],
    "디저트카페": ["디저트", "디져트", "베이글카페", "케이크", "빙수", "젤라또"],
    "한식음식점": ["한식", "백반", "국밥", "김치찌개", "한정식", "식당"],
    "치킨전문점": ["치킨", "닭", "chicken", "호프치킨"],
    "편의점": ["편의점", "cu", "gs25", "세븐일레븐", "이마트24"],
    "베이커리": ["베이커리", "빵집", "제과", "제과점", "bakery", "빵"],
    "호프_주점": ["호프", "주점", "술집", "포차", "이자카야", "펍", "bar", "맥주"],
    "분식": ["분식", "떡볶이", "김밥", "라면", "튀김"],
    "미용실": ["미용실", "헤어", "미용", "살롱", "펌", "커트"],
    "패스트푸드": ["패스트푸드", "버거", "햄버거", "샌드위치", "토스트"],
    "일식집": ["일식", "초밥", "스시", "라멘", "돈카츠", "우동", "sushi"],
    "중식당": ["중식", "중국집", "짜장", "짬뽕", "탕수육", "마라"],
    "고깃집": ["고깃집", "고기집", "삼겹살", "갈비", "곱창", "숯불", "구이집"],
    "피자전문점": ["피자", "pizza", "피자집"],
    "의류매장": ["의류", "옷가게", "옷집", "패션", "부티크", "편집샵", "clothes"],
    "화장품매장": ["화장품", "코스메틱", "뷰티샵", "cosmetic", "올리브영"],
    "꽃집": ["꽃집", "플라워", "화원", "flower", "꽃가게"],
    "정육점": ["정육", "정육점", "축산", "고기가게", "butcher"],
    "반려동물샵": ["반려동물", "펫샵", "펫가게", "애견", "강아지용품", "pet"],
    "휴대폰매장": ["휴대폰", "핸드폰", "폰가게", "통신사", "스마트폰", "대리점"],
    "네일샵": ["네일", "네일샵", "nail", "젤네일"],
    "피부관리실": ["피부관리", "에스테틱", "피부샵", "스킨케어", "왁싱"],
    "세탁소": ["세탁", "세탁소", "빨래방", "크리닝", "드라이클리닝"],
    "학원": ["학원", "교습소", "공부방", "과외", "academy"],
    "약국": ["약국", "약방", "pharmacy"],
    "자동차정비": ["카센터", "정비소", "자동차정비", "공업사", "카센타"],
    "PC방": ["pc방", "피시방", "피씨방", "게임방"],
    "노래방": ["노래방", "코인노래", "노래연습장", "karaoke"],
    "스터디카페": ["스터디카페", "스터디", "독서실", "study"],
    "헬스장": ["헬스장", "헬스", "피트니스", "gym", "휘트니스"],
}


def detect_industry(text: str, exclude: str | None = None) -> str | None:
    """자유 텍스트에서 업종키를 감지. exclude 와 같은 업종은 무시(what-if 비교용)."""
    if not text:
        return None
    t = text.lower()
    hits = []
    for key, words in INDUSTRY_SYNONYMS.items():
        if key == exclude:
            continue
        for w in words:
            if w.lower() in t:
                hits.append((t.index(w.lower()), key))
                break
    if not hits:
        return None
    hits.sort()  # 가장 먼저 등장한 업종
    return hits[0][1]


_GU_STRIP = re.compile(r"(특별자치시|특별자치도|특별시|광역시|시|군|구)$")


def detect_district(text: str) -> str | None:
    """자유 텍스트에서 지원 지역(자치구/시)명을 감지.
    - '고양시', '강남구'는 물론 '고양', '강남' 같은 부분 표기도 인식(길이 2 이상).
    - 특정 지역이 없고 시·도만 언급되면(예: '부산', '경기') 대표 지역으로 매핑."""
    if not text:
        return None
    hits = []
    for name in DISTRICTS:
        forms = [name]
        stripped = _GU_STRIP.sub("", name)
        if len(stripped) >= 2 and stripped != name:
            forms.append(stripped)
        for f in forms:
            idx = text.find(f)
            if idx >= 0:
                hits.append((idx, -len(f), name))
                break
    if hits:
        hits.sort()                       # 가장 먼저·가장 길게 매칭된 지역
        return hits[0][2]
    # 시·도만 언급 → 그 지역의 대표(첫) 자치구/시로
    for region in REGION_OF.values():
        if region in text:
            return next((g for g in DISTRICTS if REGION_OF[g] == region), None)
    return None


# 위험 분해 리포트에서 쓰는 요인 메타(표시명·설명·좋은방향)
# good_direction: 값이 클 때 생존에 '유리'하면 "up", '불리'하면 "down"
RISK_FACTORS = [
    dict(key="competition", label="경쟁 과밀", good_direction="down",
         desc="반경 200m 내 동종 점포 밀도"),
    dict(key="vacancy", label="공실률", good_direction="down",
         desc="상권 내 빈 점포 비율 (상권 침체 신호)"),
    dict(key="rent", label="임대료 부담", good_direction="down",
         desc="점포 임대료 수준"),
    dict(key="foot_traffic", label="유동인구", good_direction="up",
         desc="상권을 지나는 생활·활동 인구"),
    dict(key="resident", label="배후 수요", good_direction="up",
         desc="상권을 받쳐주는 상주 거주·근무 인구"),
    dict(key="income", label="소득·구매력", good_direction="up",
         desc="배후 소비층의 소득 수준"),
]
