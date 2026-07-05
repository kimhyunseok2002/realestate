#!/usr/bin/env bash
# 상권 생존 예측 서비스 실행
#   ./run.sh            # http://127.0.0.1:8000
#   PORT=8080 ./run.sh
cd "$(dirname "$0")" || exit 1
exec python3 run.py
