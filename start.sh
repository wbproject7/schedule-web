#!/bin/bash
# 직원 스케줄 웹 생성기 - 실행 스크립트
# ==========================================

cd "$(dirname "$0")"

MODE="${1:-prod}"

if [ "$MODE" = "dev" ]; then
    echo "=== 개발 모드 ==="
    python3 app.py --dev
else
    echo "=== 프로덕션 모드 (Gunicorn) ==="
    echo "http://localhost:5000 에서 접속하세요"
    gunicorn app:app \
        --bind 0.0.0.0:5000 \
        --workers 2 \
        --threads 4 \
        --timeout 60 \
        --access-logfile - \
        --error-logfile -
fi
