"""
Vercel 서버리스 진입점.
==========================
backend/app.py 의 FastAPI ASGI 앱(`app`)을 그대로 노출한다.
Vercel 의 @vercel/python 런타임이 이 `app` 을 자동으로 서빙한다.

로컬 개발은 그대로 `python3 run.py` 를 쓰면 된다(이 파일은 Vercel 전용).
"""
import os
import sys

# 레포 루트를 import 경로에 추가 (backend 패키지 import 용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app  # noqa: E402,F401  (Vercel 이 이 `app` 을 진입점으로 사용)
