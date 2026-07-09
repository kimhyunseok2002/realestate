"""
전국 자치구 배후 인구·종사자 실데이터 스냅샷 생성기 (통계청 SGIS)
=========================================================
통계청 SGIS OpenAPI(stats/population)에서 시군구별
  - 인구  (tot_ppltn)     → 배후 거주수요(resident_support)
  - 종사자수(employee_cnt) → 주간 활동인구(daytime_pop)
를 받아, 우리 자치구(81개)에 이름으로 매칭해 backend/realdata/sgis_pop.json 으로 저장한다.

SGIS 특성:
  · 도메인 이전: sgisapi.mods.go.kr (구 sgisapi.kostat.go.kr)
  · 2단계 인증: consumer_key+consumer_secret → accessToken → stats 호출
  · SGIS 자체 행정코드(표준코드와 다름) + 특례시는 구 단위 분할(예: '수원시 장안구')
    → 코드가 아니라 '시·도 범위 안에서 이름 매칭'으로 자치구를 집계한다.

실행:  SGIS_CONSUMER_KEY=... SGIS_CONSUMER_SECRET=... python3 -m backend.realdata.build_sgis
서비스 구동에는 필요 없다 — 생성된 sgis_pop.json(공개 통계, 커밋 대상)만 있으면 된다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "sgis_pop.json")
BASE = "https://sgisapi.mods.go.kr/OpenAPI3"
YEAR = os.environ.get("SGIS_YEAR", "2023")

# 우리 시·도명 → SGIS 시·도 코드(2자리, SGIS 자체 코드)
SGIS_SIDO_CODE = {
    "서울": "11", "부산": "21", "대구": "22", "인천": "23", "광주": "24",
    "대전": "25", "울산": "26", "세종": "29", "경기": "31", "강원": "32",
    "충북": "33", "충남": "34", "전북": "35", "전남": "36", "경북": "37",
    "경남": "38", "제주": "39",
}
# 광역시 '전체'를 가리키는 우리 자치구 키 → 그 시·도 전체 합계를 대표값으로 사용
WHOLE_METRO_KEYS = {"부산", "대구", "인천", "대전", "광주", "울산", "세종시"}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _auth() -> str:
    ck = (os.environ.get("SGIS_CONSUMER_KEY") or "").strip()
    cs = (os.environ.get("SGIS_CONSUMER_SECRET") or "").strip()
    if not ck or not cs:
        raise SystemExit("SGIS_CONSUMER_KEY / SGIS_CONSUMER_SECRET 환경변수가 필요합니다.")
    body = _get(f"{BASE}/auth/authentication.json?consumer_key={ck}&consumer_secret={cs}")
    if body.get("errCd") != 0:
        raise SystemExit(f"SGIS 인증 실패: {body.get('errMsg')}")
    return body["result"]["accessToken"]


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _sigungu(token: str, sido_code: str) -> list[dict]:
    """한 시·도의 시군구 목록(인구·종사자 포함). 하위가 없으면(세종 등) 자기 자신."""
    url = (f"{BASE}/stats/population.json?accessToken={token}"
           f"&year={YEAR}&adm_cd={sido_code}&low_search=1")
    body = _get(url)
    rows = body.get("result") or []
    if not rows:  # 하위 시군구가 없는 시·도(세종 등) → 시·도 자기 자신
        body = _get(f"{BASE}/stats/population.json?accessToken={token}"
                    f"&year={YEAR}&adm_cd={sido_code}&low_search=0")
        rows = body.get("result") or []
    return rows


def build() -> dict:
    from backend import data
    token = _auth()

    # 시·도별 시군구 행 캐시
    by_sido: dict[str, list[dict]] = {}
    for sido, code in SGIS_SIDO_CODE.items():
        by_sido[sido] = _sigungu(token, code)
        print(f"  [{sido}] {code}: 시군구 {len(by_sido[sido])}개")

    def norm(s: str) -> str:
        return (s or "").replace(" ", "")

    districts: dict[str, dict] = {}
    unmatched: list[str] = []
    for gu in data.DISTRICTS:
        sido = data.REGION_OF.get(gu)
        rows = by_sido.get(sido, [])
        if gu in WHOLE_METRO_KEYS:            # 광역시/세종 전체 = 시·도 합계
            matched = rows
        else:                                  # 시·도 안에서 이름 접두 매칭(특례시 구 합산)
            g = norm(gu)
            matched = [r for r in rows if norm(r.get("adm_nm")).startswith(g)]
        if not matched:
            unmatched.append(f"{gu}({sido})")
            continue
        pop = sum(_int(r.get("tot_ppltn")) for r in matched)
        emp = sum(_int(r.get("employee_cnt")) for r in matched)
        districts[gu] = {
            "population": pop,
            "employees": emp,
            "n_match": len(matched),
            "matched": [r.get("adm_nm") for r in matched],
        }
    if unmatched:
        print(f"⚠️  SGIS 매칭 실패(합성 유지): {', '.join(unmatched)}", file=sys.stderr)

    return {
        "meta": {
            "source": "통계청 SGIS 통계지리정보 — 인구·사업체(종사자)",
            "org": "통계청 SGIS OpenAPI (sgisapi.mods.go.kr)",
            "service": "stats/population.json",
            "year": YEAR,
            "unit": "인구(명)·종사자(명)",
            "fields": {"resident": "tot_ppltn", "daytime": "employee_cnt"},
            "note": "자치구 대표값 = SGIS 시군구(특례시는 구 합산) 인구·종사자. "
                    "SGIS 자체 행정코드/특례시 구분할 때문에 시·도 범위 내 이름 매칭으로 집계.",
        },
        "districts": dict(sorted(districts.items())),
    }


def main() -> int:
    snap = build()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f"✔ {OUT_PATH}  ({snap['meta']['year']}년 · 자치구 {len(snap['districts'])}개)")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, "..", "vendor"))
    sys.path.insert(0, os.path.join(HERE, "..", ".."))
    raise SystemExit(main())
