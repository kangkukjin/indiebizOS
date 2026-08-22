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
# 일시 정지: touch data/backend_keeper_off   (지우면 재개 / 안 지워도 PAUSE_TTL 후 자동 만료)
# 종료:      kill $(cat data/backend_keeper.pid)
# 로그:      data/backend_keeper.log

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAUSE="$REPO/data/backend_keeper_off"
LOG="$REPO/data/backend_keeper.log"
PIDFILE="$REPO/data/backend_keeper.pid"
HEALTH="http://127.0.0.1:8765/health"
BOOT_GRACE=300   # 초 — 리스너가 이보다 젊으면 콜드 스타트로 간주, revive 보류
# ★일시정지 표식의 유효기간(2026-08-17): 표식은 "작업 전 touch, 작업 후 rm" 의 두
#   단계인데 **그 사이에서 편집자가 죽는다** — backend .py 를 고치는 주체가 그 backend
#   안에서 살면(시스템 AI 자기수리) 리로드가 자기 턴을 끊어 rm 이 영원히 실행되지 않는다.
#   실제로 표식이 몇 시간씩 남아 감시가 통째로 멎어 있었다. 그래서 표식에 나이를 주고,
#   회수를 잊어도 시스템이 스스로 깨어나게 한다. 표식의 mtime = 심장박동(연쇄 편집은
#   매 쓰기마다 touch 되어 살아 있고, 편집이 끝나면 늙어서 만료된다).
#   조기 회수는 워치독(red_watchdog)이 하고, 이 만료는 그마저 죽었을 때의 바닥이다.
PAUSE_TTL=900    # 초 — 표식이 이보다 늙으면 만료로 보고 감시 재개


# 멱등 — 이미 도는 keeper 가 있으면 조용히 물러난다
if [ -f "$PIDFILE" ]; then
    OLD=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
        exit 0
    fi
fi
echo $$ > "$PIDFILE"
echo "[$(date '+%F %T')] keeper 시작 (pid=$$)" >> "$LOG"

# ★타임아웃 10초(2026-08-16 사건): 해마 임베딩 모델(442MB) 콜드 로드 중엔 로더
#   스레드의 GIL 점유로 /health 응답이 수 초씩 늘어진다 — 4초는 "느림"을 "죽음"으로
#   오판했다. 진짜 죽음(연결 거부)은 타임아웃과 무관하게 즉시 실패하므로 넉넉해도
#   탐지 지연이 없다.
health_ok() {
    /usr/bin/curl -s -m 10 "$HEALTH" >/dev/null 2>&1
}

# 파일이 마지막으로 수정된 뒤 흐른 초. 파일이 없으면 실패(비어 있음).
file_age() {
    local m
    m=$(stat -f%m "$1" 2>/dev/null || stat -c%Y "$1" 2>/dev/null) || return 1
    [ -z "$m" ] && return 1
    echo $(( $(date +%s) - m ))
}

# 8765 리스너들 중 *가장 젊은* 프로세스의 경과 초를 출력. 리스너 없으면 실패(비어 있음).
# ★min 인 이유: uvicorn --reload 는 마스터+워커 둘 다 리스너로 잡힌다 — backend .py
#   편집 리로드는 워커만 새로 태어나므로(마스터는 늙음), 젊은 쪽이 "지금 부팅 중"의 신호다.
listener_age() {
    local pid etime days s min=""
    for pid in $(/usr/sbin/lsof -ti :8765 -sTCP:LISTEN 2>/dev/null); do
        etime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
        [ -z "$etime" ] && continue
        days=0
        case "$etime" in *-*) days=${etime%%-*}; etime=${etime#*-};; esac
        # etime 꼬리 = [HH:]MM:SS — awk 숫자 강제변환이 선행 0 도 안전하게 처리
        s=$(echo "$etime" | awk -F: '{ if (NF==3) print $1*3600+$2*60+$3; else if (NF==2) print $1*60+$2; else print $1+0 }')
        s=$((days*86400 + s))
        if [ -z "$min" ] || [ "$s" -lt "$min" ]; then min=$s; fi
    done
    [ -z "$min" ] && return 1
    echo "$min"
}

revive() {
    # keeper 가 띄운 백엔드의 stdout 이 이 로그로 흐르므로 비대화 방지(50MB 회전)
    if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 52428800 ]; then
        mv "$LOG" "$LOG.old"
    fi
    {
        echo "[$(date '+%F %T')] /health 3회 무응답 — 백엔드 재기동 (유령 워커 포함 정리)"
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
        # ★소생도 같은 몸으로만 한다 (2026-08-22). 시스템 파이썬으로 되살리면
        # "살아는 있는데 몸이 다른" 상태가 되고, /health 는 초록이라 아무도 모른다.
        # 되살릴 수 없으면 되살리지 않고 신고한다 — 다음 순회에서 다시 시도한다.
        if [ ! -x "$REPO/.venv/bin/python3" ]; then
            echo "[$(date '+%F %T')] ❌ 재기동 보류 — $REPO/.venv 가 없습니다."
            echo "[$(date '+%F %T')]    python3 scripts/bootstrap.py 로 가상환경을 만드세요."
            return 1
        fi
        PY="$REPO/.venv/bin/python3"
        cd backend || return 1
        nohup "$PY" api.py >> "$LOG" 2>&1 &
        echo "[$(date '+%F %T')] 재기동 완료 (pid=$!, .venv)"
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
    # 일시정지 표식 — 단, 나이를 본다(위 PAUSE_TTL 주석: 회수 단계는 자주 실행되지 못한다)
    if [ -f "$PAUSE" ]; then
        PAGE=$(file_age "$PAUSE")
        if [ -z "$PAGE" ] || [ "$PAGE" -lt "$PAUSE_TTL" ]; then
            continue
        fi
        echo "[$(date '+%F %T')] 일시정지 표식이 ${PAGE}초째(>${PAUSE_TTL}) — 만료로 보고 감시 재개" >> "$LOG"
        rm -f "$PAUSE"
    fi
    health_ok && continue
    # 재확인 스트라이크 — start.sh 의 kill→start 순간 틈새·리로드 순간 오발 방지.
    # ★20초 간격(2026-08-06 사건): uvicorn --reload 재기동은 /health 가 11~15초 죽는다
    #   — 재확인 대기는 리로드 소요보다 길어야 한다.
    # ★3회화(2026-08-16 사건): 2회(총 ~24초 창)는 모델 콜드 로드의 긴 기아를 못 넘겼다.
    STRIKE_OUT=1
    for _ in 1 2; do
        sleep 20
        if health_ok; then STRIKE_OUT=0; break; fi
    done
    [ "$STRIKE_OUT" -eq 0 ] && continue
    # ★부팅 유예(2026-08-16 사건, 킬 루프의 구조적 차단): 해마 모델 교체 직후 재기동은
    #   콜드 로드가 2분+ 걸려 /health 가 굶는다 — keeper 의 revive→재확인 주기(~110초)가
    #   그보다 짧아 "kill→콜드 로드→kill" 루프가 실측됨(05:46/05:48/05:50 3연타).
    #   리스너 프로세스가 살아 있고 아직 젊으면(부팅 중) 죽음이 아니라 콜드 스타트다.
    #   진짜 유령 워커(포트 점유+영구 무응답)는 나이를 먹으므로 다음 주기에 revive 된다.
    AGE=$(listener_age)
    if [ -n "$AGE" ] && [ "$AGE" -lt "$BOOT_GRACE" ]; then
        echo "[$(date '+%F %T')] /health 무응답이나 리스너 나이 ${AGE}초(<${BOOT_GRACE}) — 콜드 스타트 유예" >> "$LOG"
        continue
    fi
    revive
    sleep 30   # 부팅 여유 — 연속 재기동 폭주 방지
done
