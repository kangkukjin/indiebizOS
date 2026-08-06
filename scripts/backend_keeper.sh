#!/bin/bash
# backend_keeper.sh — 백엔드 감독 데몬 (상주 루프, nohup 분리 실행)
#
# 자체수리 불가 지대 ① 봉합(2026-08-05): red_watchdog 은 "수정 직후 죽음"만 덮는다 —
# uvicorn 리로더 마스터까지 죽는 부류(OOM·크래시)와 유령 워커(health 무응답인데 포트
# 점유 — [uvicorn-reload-ghost-worker] 부류)는 재기동해 줄 손이 없었다. 이 keeper 가
# 60초마다 /health 를 확인하고, 죽어 있으면 기록된 처방(유령 포함 전체 kill → 재기동)을
# 수행한다.
#
# ★launchd(LaunchAgent)가 아니라 상주 루프인 이유(2026-08-05 실측): 저장소가
#   ~/Desktop 아래라 macOS TCC 보호에 걸려 launchd 컨텍스트의 bash 는 스크립트를
#   읽지도 못한다("Operation not permitted"). 사용자 세션(터미널)에서 nohup 분리
#   기동하면 Desktop 접근 권한을 승계하고, 터미널을 닫아도·백엔드가 죽어도 생존한다.
#   한계: 재부팅은 못 넘는다 — 재부팅 후엔 start.sh(keeper 자동 보장 포함)를 한 번
#   실행해야 한다. launchd 로 재부팅까지 넘기려면 bash 에 전체 디스크 접근 권한을
#   줘야 해서(보안 하향) 채택하지 않았다.
#
# 기동(멱등 — start.sh 가 자동 보장):  nohup bash scripts/backend_keeper.sh >/dev/null 2>&1 &
# 일시 정지: touch data/backend_keeper_off   (지우면 재개)
# 종료:      kill $(cat data/backend_keeper.pid)
# 로그:      data/backend_keeper.log

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAUSE="$REPO/data/backend_keeper_off"
LOG="$REPO/data/backend_keeper.log"
PIDFILE="$REPO/data/backend_keeper.pid"
HEALTH="http://127.0.0.1:8765/health"

# 멱등 — 이미 도는 keeper 가 있으면 조용히 물러난다
if [ -f "$PIDFILE" ]; then
    OLD=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
        exit 0
    fi
fi
echo $$ > "$PIDFILE"
echo "[$(date '+%F %T')] keeper 시작 (pid=$$)" >> "$LOG"

revive() {
    # keeper 가 띄운 백엔드의 stdout 이 이 로그로 흐르므로 비대화 방지(50MB 회전)
    if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 52428800 ]; then
        mv "$LOG" "$LOG.old"
    fi
    {
        echo "[$(date '+%F %T')] /health 2회 무응답 — 백엔드 재기동 (유령 워커 포함 정리)"
        # 기록된 처방: 유령만 죽이면 복구 안 됨 — 마스터까지 전부 정리 후 재기동
        # ★-sTCP:LISTEN 필수(2026-08-06 사건): 무스코프 lsof -i 는 원격 포트가 8765인
        #   클라이언트 소켓(Electron WS·cloudflared 터널·에이전트 MCP)까지 매칭해
        #   kill -9 가 앱을 통째로 죽였다. 리스너만 겨냥한다.
        /usr/sbin/lsof -ti :8765 -sTCP:LISTEN | xargs kill -9 2>/dev/null
        pkill -9 -f "python3 api.py" 2>/dev/null
        pkill -9 -f "Python api.py" 2>/dev/null
        sleep 1

        cd "$REPO" || return 1
        if [ -f .env ]; then
            export $(cat .env | grep -v '^#' | xargs)
        fi
        PY="python3"
        [ -x "$REPO/.venv/bin/python3" ] && PY="$REPO/.venv/bin/python3"
        cd backend || return 1
        nohup "$PY" api.py >> "$LOG" 2>&1 &
        echo "[$(date '+%F %T')] 재기동 완료 (pid=$!)"
    } >> "$LOG" 2>&1
}

while true; do
    sleep 60
    # 의도적 종료 표식(창 닫기·start.sh 종료) — 시스템이 일부러 꺼졌으니 keeper 도 퇴근
    # (되살리면 "다 정리하고 죽는다" 위반). 다음 시작이 표식을 지우고 keeper 를 다시 띄운다.
    if [ -f "$REPO/data/.intentional_shutdown" ]; then
        echo "[$(date '+%F %T')] 의도적 종료 표식 감지 — keeper 퇴근" >> "$LOG"
        rm -f "$PIDFILE"
        exit 0
    fi
    [ -f "$PAUSE" ] && continue
    /usr/bin/curl -s -m 4 "$HEALTH" >/dev/null 2>&1 && continue
    sleep 20
    # 이중 확인 — start.sh 의 kill→start 순간 틈새·리로드 순간 오발 방지.
    # ★20초(2026-08-06 사건): uvicorn --reload 재기동은 /health 가 11~15초 죽는다
    #   (임베딩 모델 등 무거운 콜드 스타트) — 5초 재확인은 정상 리로드를 죽음으로
    #   오판해 revive 를 오발했다. 재확인 대기는 리로드 소요보다 길어야 한다.
    /usr/bin/curl -s -m 4 "$HEALTH" >/dev/null 2>&1 && continue
    revive
    sleep 30   # 부팅 여유 — 연속 재기동 폭주 방지
done
