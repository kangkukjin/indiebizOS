#!/bin/bash
# IndieBiz OS 시작 스크립트

cd "$(dirname "$0")"

echo "🚀 IndieBiz OS 시작..."

# 기존 프로세스 정리
pkill -f "python3 api.py" 2>/dev/null
sleep 1

# 백엔드 시작
cd backend
python3 api.py &
BACKEND_PID=$!
cd ..

sleep 2

# 프론트엔드 시작 (electron:dev 사용)
cd frontend
npm run electron:dev &
FRONTEND_PID=$!
cd ..

echo "✅ 백엔드 PID: $BACKEND_PID"
echo "✅ 프론트엔드 PID: $FRONTEND_PID"

# 종료 시 정리
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; pkill -f 'python3 api.py' 2>/dev/null" EXIT

wait
