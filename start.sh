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

# 파이썬 선택: 소스 경로의 몸은 .venv 하나로 고정한다 (2026-08-22).
# 예전엔 .venv 가 없으면 조용히 시스템 파이썬으로 떨어졌다. 그건 "다른 몸으로
# 도는데 아무도 모르는" 상태다 — fastapi/dotenv 부재는 그나마 시끄럽게 죽지만,
# playwright 처럼 *버전이 다르게* 깔린 의존은 조용히 반쪽으로 돈다(시스템 파이썬의
# playwright 1.58 은 이 저장소가 받아 둔 크로미움 빌드를 못 찾는다). 조용한 폴백 대신
# 정직하게 거절하고 처방을 준다. bootstrap 이 .venv 를 만든다.
if [ ! -x ".venv/bin/python3" ]; then
    echo "❌ .venv 가 없습니다 — 소스 경로는 저장소 가상환경 하나로 고정입니다."
    echo "   python3 scripts/bootstrap.py   # venv + 의존성 + .env 시드"
    exit 1
fi
PY="$(pwd)/.venv/bin/python3"
echo "✅ 가상환경 파이썬 사용 (.venv)"

# 의도적 종료 표식 제거 — 시스템 재가동 (수리 워치독·keeper 정상 작동 재개)
rm -f data/.intentional_shutdown

# 백엔드 시작
cd backend
"$PY" api.py &
BACKEND_PID=$!
cd ..

sleep 2

echo "✅ 백엔드 PID: $BACKEND_PID"

# 감독 데몬(keeper) 보장 — 백엔드가 죽으면(마스터 사망·유령 워커 포함) 1분 내 재기동.
# 멱등(pid 파일)이라 중복 기동 없음. nohup 분리라 이 터미널을 닫아도 생존.
# launchd 를 안 쓰는 이유는 scripts/backend_keeper.sh 머리말 참조(TCC).
nohup bash scripts/backend_keeper.sh >/dev/null 2>&1 &
echo "✅ 백엔드 감독 데몬(keeper) 보장"

# 프론트엔드 시작 (electron:dev) — 선택 사항: Node/npm과 node_modules가 있을 때만.
# 없으면 백엔드 전용(헤드리스)으로 계속 실행 — 원격 런처/REST로 사용 가능.
FRONTEND_PID=""
if command -v npm >/dev/null 2>&1 && [ -d "frontend/node_modules" ]; then
    cd frontend
    npm run electron:dev &
    FRONTEND_PID=$!
    cd ..
    echo "✅ 프론트엔드 PID: $FRONTEND_PID"
else
    echo "ℹ️  프론트엔드 스킵 (npm 또는 frontend/node_modules 없음) — 백엔드 전용으로 실행"
    echo "   데스크탑 UI가 필요하면 Node ≥ 18 설치 후: cd frontend && npm install && npm run rebuild-trusted"
fi

# 종료 시 정리 - 프로세스 그룹 전체 종료 + 고아 프로세스 정리
cleanup() {
    echo ""
    echo "🛑 IndieBiz OS 종료 중..."

    # 0. 의도적 종료 표식 + keeper 정리 — 표식이 없으면 수리 워치독이 죽은 /health 를
    # 수리 탓으로 오판해 정상 수리를 롤백하고, keeper 를 안 죽이면 1분 내 백엔드를
    # 되살린다("다 정리하고 죽는다" 위반). 다음 시작이 표식을 지운다. (충돌 봉합 08-05)
    touch data/.intentional_shutdown 2>/dev/null
    if [ -f data/backend_keeper.pid ]; then
        kill -9 "$(cat data/backend_keeper.pid)" 2>/dev/null
        rm -f data/backend_keeper.pid
    fi
    pkill -f "scripts/backend_keeper.sh" 2>/dev/null

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

    # 3. 포트 8765 점유 프로세스 강제 정리
    lsof -ti :8765 | xargs kill -9 2>/dev/null

    # 4. 남은 고아 프로세스 정리
    pkill -9 -f "python3 api.py" 2>/dev/null
    pkill -9 -f "Python api.py" 2>/dev/null
    pkill -f "cloudflared tunnel run" 2>/dev/null

    # 5. uvicorn multiprocessing 고아 정리 (Python 3.14 + multiprocessing.spawn)
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
