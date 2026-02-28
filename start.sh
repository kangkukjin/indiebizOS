#!/bin/bash
# IndieBiz OS 시작 스크립트

cd "$(dirname "$0")"

# .env 파일 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ 환경변수 로드 완료"
else
    echo "⚠️  .env 파일이 없습니다. .env.example을 참고하여 생성하세요."
fi

echo "🚀 IndieBiz OS 시작..."

# 기존 프로세스 정리 (포트 8765 사용 중인 프로세스 종료)
# Python 3.14 (Homebrew)는 바이너리명이 "Python"이므로 python3 패턴뿐 아니라 모두 포함
lsof -ti :8765 | xargs kill -9 2>/dev/null
pkill -9 -f "python3 api.py" 2>/dev/null
pkill -9 -f "Python api.py" 2>/dev/null
sleep 1
# 포트가 아직 사용 중이면 한 번 더 정리
if lsof -ti :8765 > /dev/null 2>&1; then
    lsof -ti :8765 | xargs kill -9 2>/dev/null
    sleep 1
fi

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

# 종료 시 정리 - 프로세스 그룹 전체 종료 + 고아 프로세스 정리
cleanup() {
    echo ""
    echo "🛑 IndieBiz OS 종료 중..."

    # 1. 백엔드 프로세스 트리 전체 종료 (uvicorn reload worker 포함)
    if [ -n "$BACKEND_PID" ]; then
        # 백엔드 PID의 모든 자식 프로세스도 함께 종료
        pkill -TERM -P $BACKEND_PID 2>/dev/null
        kill -TERM $BACKEND_PID 2>/dev/null
        sleep 1
        # 아직 살아있으면 강제 종료
        pkill -9 -P $BACKEND_PID 2>/dev/null
        kill -9 $BACKEND_PID 2>/dev/null
    fi

    # 2. 프론트엔드 종료
    if [ -n "$FRONTEND_PID" ]; then
        pkill -TERM -P $FRONTEND_PID 2>/dev/null
        kill -TERM $FRONTEND_PID 2>/dev/null
    fi

    # 3. 남은 고아 프로세스 정리
    pkill -9 -f "python3 api.py" 2>/dev/null
    pkill -f "cloudflared tunnel run" 2>/dev/null

    # 4. uvicorn multiprocessing 고아 정리 (Python 3.14 + multiprocessing.spawn)
    pgrep -f "multiprocessing.spawn" | while read pid; do
        # 터미널에 붙어있는 것만 (MCP 서버 등은 건드리지 않음)
        if ps -p $pid -o tty= 2>/dev/null | grep -q "s0"; then
            kill -9 $pid 2>/dev/null
        fi
    done
    pgrep -f "multiprocessing.resource_tracker" | while read pid; do
        if ps -p $pid -o tty= 2>/dev/null | grep -q "s0"; then
            kill -9 $pid 2>/dev/null
        fi
    done

    echo "👋 IndieBiz OS 종료 완료"
}

trap cleanup EXIT INT TERM

wait
