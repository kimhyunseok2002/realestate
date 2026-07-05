#!/usr/bin/env python3
"""
상권 생존 예측 서비스 실행기.
    python3 run.py            # 기본 http://127.0.0.1:8000
    PORT=8080 python3 run.py  # 포트 변경
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend", "vendor"))  # 로컬 설치 의존성
sys.path.insert(0, ROOT)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  상권 생존 예측 서비스  →  http://{host}:{port}\n")
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)
