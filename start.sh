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

# 단일 제어자 시작. 커널 잠금으로 기존 현역을 채택하며 포트의 다른 앱을 죽이지 않는다.
"$PY" backend/api.py start &
BACKEND_PID=$!
echo "✅ 재기동 제어자 PID: $BACKEND_PID"

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

# 의도적 종료는 같은 제어자에게 전달한다. 실제 자식의 정리는 제어자가 끝낸다.
CLEANED=0
cleanup() {
    [ "$CLEANED" -eq 1 ] && return
    CLEANED=1
    echo "🛑 IndieBiz OS 종료 중..."
    "$PY" backend/api.py shutdown --wait
    if [ -n "$FRONTEND_PID" ]; then
        kill -TERM "$FRONTEND_PID" 2>/dev/null
    fi
    echo "👋 IndieBiz OS 종료 완료"
}
trap cleanup EXIT INT TERM
# 중복 시작의 요청 프로세스는 즉시 끝난다. 그 종료를 시스템 종료로 읽지 않는다.
"$PY" backend/api.py wait
