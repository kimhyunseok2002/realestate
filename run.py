#!/usr/bin/env python3
"""
상권 생존 예측 서비스 실행기.
    python3 run.py            # 기본 http://127.0.0.1:8000
    PORT=8080 python3 run.py  # 포트 변경
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    """프로젝트 루트의 .env(gitignore됨)를 os.environ에 로드 — 로컬 개발용.
    의존성 없이 KEY=VALUE 한 줄씩 파싱하며, 이미 설정된 환경변수는 덮어쓰지 않는다.
    (배포 환경(Vercel 등)은 대시보드 환경변수를 쓰므로 .env가 없어도 된다.)"""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
sys.path.insert(0, os.path.join(ROOT, "backend", "vendor"))  # 로컬 설치 의존성
sys.path.insert(0, ROOT)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  상권 생존 예측 서비스  →  http://{host}:{port}\n")
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)
