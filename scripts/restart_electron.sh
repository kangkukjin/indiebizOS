#!/bin/bash
# restart_electron.sh — 데스크탑(Electron) 재시작
#
# 자체수리 불가 지대 ② 봉합(2026-08-05): frontend 수리가 화면에 닿으려면 Electron
# 재시작이 필요한데 그동안 사람 몫이었다("⏳Electron 재시작"이 작업 로그마다 남던 이유).
# 이 스크립트는 이 저장소의 Electron 개발 트리(vite+electron)만 정확히 죽이고
# 분리(nohup) 재기동한다 — AI 가 run_command 로 부르거나 사람이 직접 실행.
#
# ★kill 은 반드시 $REPO 경로로 스코프한다 — 맨 "electron" 패턴은 이 기계의 다른
#   Electron 앱(Claude 데스크탑 등)까지 오폭한다.
# 로그: data/electron_dev.log

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$REPO/data/electron_dev.log"

echo "[$(date '+%F %T')] Electron 재시작 요청" >> "$LOG"

# 1) 이 저장소의 프론트 개발 트리만 종료 (vite·electron·helpers — 경로 스코프)
pkill -f "$REPO/frontend/node_modules" 2>/dev/null
sleep 2
pkill -9 -f "$REPO/frontend/node_modules" 2>/dev/null

# 2) 재기동 — 개발 트리(node_modules 존재) 우선, 없으면 패키징 앱 폴백
if command -v npm >/dev/null 2>&1 && [ -d "$REPO/frontend/node_modules" ]; then
    cd "$REPO/frontend" || exit 1
    nohup npm run electron:dev >> "$LOG" 2>&1 &
    echo "[$(date '+%F %T')] electron:dev 재기동 (pid=$!)" >> "$LOG"
    echo "Electron 개발 모드 재시작 완료 (로그: data/electron_dev.log)"
elif [ -d "/Applications/IndieBiz OS.app" ]; then
    open -a "IndieBiz OS"
    echo "패키징 앱 재실행 완료"
else
    echo "Error: frontend/node_modules 도 패키징 앱도 없습니다 — 재시작 대상 없음"
    exit 1
fi
