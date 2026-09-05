"""
red_apply.py - 지연 적용 수행자 (분리 프로세스, 2026-08-19)

★왜: [self:patch]{op:"apply"} 가 backend/*.py 를 그 자리에서 쓰면 uvicorn 리로드
(reload_delay 2초)가 **그 턴을 실행 중인 워커를 죽인다** — 최종 응답, 주행기록의
로그 버퍼(END 저장 전까지 메모리에만 있다), 증류 데몬 스레드가 전부 그 워커 안에
산다. 검증(격리 워크트리)은 턴 안에서 이미 끝났으므로, 여기는 **쓰기만** 맡는다:

  ①턴이 완전히 닫히기를 기다린다 — 주행기록 ended_at(=응답 전송·버퍼 저장 완료)
    → 증류 재합류(cognitive_distill 의 finally 가 refresh_episode 로 log 를 한 번
    다시 쓴다 — 그 길이 변화가 신호)
  ①′**도는 턴이 0 이 될 때까지** 기다린다 (2026-09-02, wait_quiescent) — 예약한 턴만
    기다리면 그 뒤에 시작한 **다음 턴**을 리로드가 자른다(실측 ep1917, #repair 절단율
    16%). /health 의 live_turns 가 출처. 0 을 본 순간 재기동 관문(reload_gate)을 세우고
    한 번 더 확인한 뒤에야 쓴다 — 관문은 쓰기~새 몸 부팅 사이의 창에 들어온 새 턴을
    정직하게 되돌려보낸다(옛 몸 안에서 기다리게 하면 그 기다림은 옛 몸과 함께 죽는다).
  ②쓰기 직전 재검증한다 — 예약~수행 사이의 라이브 드리프트까지 live_sync 가 맞춘다
  ③라이브에 쓰고 워치독(red_watchdog)에게 헬스 판정·자동 롤백을 넘긴다

"자기 죽음 이후에 실행돼야 하는 단계는 죽음을 넘는 프로세스가 맡는다"(라이브 백엔드
편집 규약, 2026-08-17 개정)의 적용-단계 판이다. 판정 보고는 다음 턴(red_report).

★그랜트: red_grant 는 인메모리 싱글턴이라 이 프로세스에서의 재발급은 이 프로세스에만
존재한다 — 턴에서 검증된 그랜트가 잡 파일로 이월된 것이지 새 권한 발급이 아니다
(워치독이 그랜트 없이 백업을 복원하는 것과 같은 부류: 능력은 파일이 나른다).

사용: python3 red_apply.py <job.json>
잡: {"key","repo","episode_id","task_id","agent_id","reason","scheduled_at","handler_path"}
코드 루트=이 파일의 저장소(sys.path·handler 폴백) / 데이터 루트=job["repo"] — 테스트의
가짜 저장소에서 둘이 갈라진다(배터리 S10).
"""
import importlib.util
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent.parent   # backend/datastore/ → repo

# 대기 상한 — 환경변수는 테스트 심(배터리가 유예 0으로 줄인다)
TURN_CLOSE_CAP_S = float(os.environ.get("RED_APPLY_TURN_CAP_S", 900))
DISTILL_GRACE_S = float(os.environ.get("RED_APPLY_DISTILL_GRACE_S", 120))
NO_EPISODE_GRACE_S = float(os.environ.get("RED_APPLY_NO_EPISODE_GRACE_S", 10))
SETTLE_S = float(os.environ.get("RED_APPLY_SETTLE_S", 2))
# 몸이 "그 턴 안 돈다"고 답하는데 원장 행이 NULL 인 채 이만큼 지나면 = 잘린 턴(cut).
# (2026-09-06 ep2891: 재기동 강행에 잘린 턴의 행을 900초 기다렸다 — 몸은 05:20 부터 답할 수 있었다.)
# 짧은 유예는 막 닫히는 중인 _close_episode UPDATE 가 원장에 내려앉을 시간이다.
BODY_GONE_CONFIRM_S = float(os.environ.get("RED_APPLY_BODY_GONE_CONFIRM_S", 10))
# 판정 불능 유예 — 몸은 살아 있는데 도는 턴을 못 본 경우(옛 몸의 /health 등). 짧은 유예로
# 떨어지기 전에 이만큼 다시 묻는다. '못 봤다'와 '없다'는 다른 사건이다(B28-1).
UNKNOWN_LIVE_GRACE_S = float(os.environ.get("RED_APPLY_UNKNOWN_LIVE_GRACE_S", 60))
# 적용 후 검증 위탁(2026-08-25) — 턴이 자기 죽음 뒤를 못 보므로 재현·회귀 확인도 여기서 돈다.
VERIFY_HEALTH_WAIT_S = float(os.environ.get("RED_APPLY_VERIFY_HEALTH_WAIT_S", 120))
VERIFY_TIMEOUT_S = float(os.environ.get("RED_APPLY_VERIFY_TIMEOUT_S", 180))
VERIFY_OUTPUT_CAP = 4000
# 정적(quiescence) 대기 (2026-09-02) — 도는 턴이 0 이 될 때까지. 상한에 닿으면 강행하되
# 결말(quiesce_outcome="cap")을 다음 턴 보고에 싣는다. 좌초 신고(30분)보다 짧게 —
# 턴 상한 900 + 증류 120 + 정적 600 = 27분.
QUIESCE_CAP_S = float(os.environ.get("RED_APPLY_QUIESCE_CAP_S", 600))
QUIESCE_POLL_S = float(os.environ.get("RED_APPLY_QUIESCE_POLL_S", 2))
# 관문을 세운 뒤 되묻기까지의 정착 — 관문 파일이 보이기 전에 진입한 턴을 잡는 창.
GATE_SETTLE_S = float(os.environ.get("RED_APPLY_GATE_SETTLE_S", 0.5))
# 몸이 안 닿을 때 '몸이 없다'로 확정하기까지 — 리로드 전이(남의 적용·바깥 편집) 중의
# 일시 불통을 '없음'으로 오판해 부팅 위에 또 쓰지 않게 한다.
UNREACHABLE_CONFIRM_S = float(os.environ.get("RED_APPLY_UNREACHABLE_CONFIRM_S", 30))
# 정적 판정에서 원장 폴백(옛 몸)이 '도는 턴'으로 셀 행의 나이 상한 — 고아 행은 제외.
LEDGER_LIVE_WINDOW_S = float(os.environ.get("RED_APPLY_LEDGER_LIVE_WINDOW_S", 3600))
HEALTH_URL = os.environ.get(
    "RED_APPLY_HEALTH_URL",
    f"http://127.0.0.1:{os.environ.get('INDIEBIZ_API_PORT', '8765')}/health")


def _probe_live_turns(url: str = None):
    """살아 있는 몸에게 직접 묻는다 → (도달했나, 라이브 턴 id 목록 | None).

    None = 답은 왔는데 그 칸이 없다(live_turns 를 모르는 옛 몸) = **판정 불능**.
    빈 목록 = 몸이 "지금 도는 턴 없다"고 답한 것 = 판정됨.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(url or HEALTH_URL, timeout=3) as r:
            if r.status != 200:
                return False, None
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return False, None      # 몸이 없다(또는 못 물었다)
    if not isinstance(data, dict) or "live_turns" not in data:
        return True, None
    ids = data.get("live_turns")
    return True, [int(i) for i in ids] if isinstance(ids, list) else None


def _log(msg: str):
    print(f"[red_apply {datetime.now():%H:%M:%S}] {msg}", flush=True)


def _episode_row(db_path: str, eid):
    """(ended_at, log 길이) — 조회 실패는 None(재시도)."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT ended_at, length(COALESCE(log,'')) FROM episode_log WHERE id=?",
            (eid,)).fetchone()
        conn.close()
        return row
    except Exception:
        return None


def _resolve_open_episode(db_path: str, agent_id):
    """잡에 episode_id 가 없을 때 열린(ended_at 없는) 최신 행을 재해소한다.

    ★왜(2026-08-20 ep1265·1267): apply 가 claude_code 의 MCP→HTTP 재진입 스레드로
    들어오면 EpisodeLogger.current() 의 contextvar 가 끊겨 잡에 episode_id=null 이
    실렸고, 짧은 유예 후 라이브 쓰기 → 리로드가 **아직 열려 있는 턴**을 끊어
    최종 보고·주행기록이 유실됐다(고아 회수만 남음). 열린 최신 행 = 예약한 그 턴.

    ★agent 필터는 참고일 뿐 최종이 아니다(2026-08-20 ep1282): 잡의 agent_id 도
    같은 오염원(재진입 스레드 문맥)에서 온다 — 'agent_001' 이 실려 필터가 열린
    system_ai 턴을 놓치고, 10초 유예 뒤 쓰기가 그 턴을 끊었다. 필터 0건이면
    무필터로 한 번 더 — 틀린 대기(최대 상한)가 틀린 즉시 쓰기보다 싸다.
    ★시험 유래 행은 후보가 아니다(2026-08-22 B18-2): 시험 프로세스가 start 만 하고
    끝내지 않은 행(실측 ep1423)은 다음 부팅의 고아 회수 전까지 영원히 ended_at NULL 로
    남는다. 무필터 2차 폴백이 그걸 "열린 턴"으로 집으면 apply 가 죽은 턴이 닫히기를
    상한(900초)까지 기다린다 — 무필터 폴백은 살리되(ep1282 의 이유는 그대로) 시험분만
    후보에서 뺀다.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = None
        if agent_id:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL AND agent=? "
                "AND COALESCE(source, 'usage') <> 'test' "
                "ORDER BY id DESC LIMIT 1", (agent_id,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id FROM episode_log WHERE ended_at IS NULL "
                "AND COALESCE(source, 'usage') <> 'test' "
                "ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _ledger_open_ids(db_path: str, exclude=None) -> list:
    """원장 폴백 — 열린(ended_at NULL) 비시험 행 중 최근 LEDGER_LIVE_WINDOW_S 안에 시작한 것.
    옛 몸(/health 에 live_turns 가 없는)에서만 쓴다. 고아 행(죽은 프로세스가 남긴 NULL)을
    '도는 턴'으로 세면 정적이 영영 안 오므로 나이로 자른다."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            "SELECT id FROM episode_log WHERE ended_at IS NULL "
            "AND COALESCE(source, 'usage') <> 'test' "
            "AND started_at >= datetime('now', 'localtime', ?)",
            (f"-{int(LEDGER_LIVE_WINDOW_S)} seconds",)).fetchall()
        conn.close()
        return [r[0] for r in rows if r[0] != exclude]
    except Exception:
        return []


def _live_turns_now(repo: str, exclude=None):
    """지금 도는 턴 → 목록 / None(몸이 안 닿음). 출처 = 몸(/health) > 원장(옛 몸 폴백)."""
    reached, live = _probe_live_turns()
    if not reached:
        return None
    if live is None:
        db_path = os.path.join(repo, "data", "world_pulse.db")
        live = _ledger_open_ids(db_path, exclude) if os.path.exists(db_path) else []
    return [i for i in live if i != exclude]


def _gate_mod():
    import reload_gate
    return reload_gate


def _close_cut_turns(repo: str, ids, reason: str) -> int:
    """강행 재기동이 자를 턴을 원장에서 닫는다(자르는 쪽이 닫는다, 2026-09-06 ep2891).
    표식·모양은 episode_logger 가 소유 — 여기는 부르기만."""
    if not ids:
        return 0
    try:
        from episode_logger import close_cut_episodes
        n = close_cut_episodes(ids, reason, db_path=os.path.join(repo, "data", "world_pulse.db"))
        if n:
            _log(f"잘리는 턴 {list(ids)} 원장 닫음({n}건, CUT 표식)")
        return n
    except Exception as e:
        _log(f"잘리는 턴 닫기 실패(계속): {e!r}")
        return 0


def wait_quiescent(repo: str, key: str, exclude_episode=None) -> dict:
    """도는 턴이 0 이 될 때까지 기다리고, 그 순간 재기동 관문을 세운다 (2026-09-02).

    반환 {"outcome": "observed" | "cap" | "no_body", "waited_s", "live_turns": [...],
          "gate": bool}.
    - observed: 0 을 봤고, 관문을 세운 뒤 되물어도 0 — 쓸 수 있다.
    - cap: 상한까지 0 이 안 됐다 — 관문을 세우고 강행한다(도는 턴이 잘릴 수 있다).
      ★상한은 안전망이지 시간표가 아니다 — 결말을 followup 에 실어 다음 턴이 본다.
    - no_body: 몸이 UNREACHABLE_CONFIRM_S 동안 안 닿았다 — 자를 턴이 없다.

    ★예약한 턴이 닫힌 뒤 시작한 턴도 턴이다 — 옛 코드는 예약한 턴 하나만 기다렸고 그래서
    **다음 턴**이 잘렸다(ep1917). 남의 관문이 서 있으면(다른 수행자가 쓰는 중) 그것도
    '도는 것'으로 보고 기다린다 — 그 리로드 위에 또 쓰지 않는다.
    """
    gate = _gate_mod()
    t0 = time.time()
    unreachable_since = None
    live = []
    while True:
        other = gate.read_gate(repo)
        if other and other.get("key") != key:
            _log(f"남의 재기동 관문({other.get('key')}, {other.get('phase')}) — 기다림")
            time.sleep(QUIESCE_POLL_S)
            if time.time() - t0 > QUIESCE_CAP_S:
                break
            continue
        live = _live_turns_now(repo, exclude_episode)
        if live is None:
            unreachable_since = unreachable_since or time.time()
            if time.time() - unreachable_since >= UNREACHABLE_CONFIRM_S:
                _log(f"몸이 {UNREACHABLE_CONFIRM_S:.0f}초 동안 안 닿음 — 자를 턴이 없다고 보고 진행")
                return {"outcome": "no_body", "waited_s": int(time.time() - t0),
                        "live_turns": [], "gate": False}
            time.sleep(min(QUIESCE_POLL_S, 1.0))
            continue
        unreachable_since = None
        if not live:
            # 0 을 봤다 — 관문을 세우고, 관문이 보이기 전에 들어온 턴이 없는지 되묻는다.
            gate.raise_gate(repo, key, phase="raised")
            time.sleep(GATE_SETTLE_S)
            again = _live_turns_now(repo, exclude_episode)
            if not again:
                _log(f"도는 턴 0 확인 ({int(time.time() - t0)}초) — 재기동 관문 세움, 쓰기 진행")
                return {"outcome": "observed", "waited_s": int(time.time() - t0),
                        "live_turns": [], "gate": True}
            # 그 사이 턴이 들어왔다 — 관문을 내리고 그 턴을 살린다(적용이 양보한다).
            gate.lower_gate(repo, key)
            _log(f"관문 직후 턴 진입 {again} — 관문 내리고 다시 기다림")
            live = again
        if time.time() - t0 > QUIESCE_CAP_S:
            break
        time.sleep(QUIESCE_POLL_S)
    gate.raise_gate(repo, key, phase="raised")
    _log(f"★정적 대기 상한({QUIESCE_CAP_S:.0f}초) — 도는 턴 {live} 이 남은 채 강행. "
         f"그 턴은 리로드에 잘릴 수 있다. 다음 턴 보고에 싣는다.")
    _close_cut_turns(repo, live, f"red_apply {key}")
    return {"outcome": "cap", "waited_s": int(time.time() - t0),
            "live_turns": list(live or []), "gate": True}


def wait_turn_closed(repo: str, episode_id, agent_id=None) -> str:
    """예약한 턴이 완전히 닫힐 때까지 대기 — ①ended_at ②증류 재합류(log 재기록).

    반환: 대기가 **어떻게 끝났는가** — "observed"(턴이 스스로 닫힘) / "cap"(상한 강행) /
    "no_turn"(도는 턴이 없었음). ★상한은 안전망이지 시간표가 아니다(2026-08-25): 예약한
    턴이 적용을 기다리며 안 닫히면 매번 상한으로 떨어지는데, 그러면 안전망이 하중을 받아
    정작 진짜 좌초를 아무도 못 알아챈다. 그래서 결말을 되돌려 다음 턴 보고에 싣는다.

    상한 초과는 '턴이 죽었다'로 보고 진행한다(좌초보다 적용이 낫고, 주행기록은
    부팅 고아 회수가 닫는다).

    ★출처는 두 벌이다 (2026-08-23, ep1689): ①원장(episode_log.ended_at) ②몸에게 직접
    묻기(/health 의 live_turns). 원장이 침묵할 때 곧바로 짧은 유예로 떨어지면, 표식이
    지워진 경우(살아 있는 행이 고아로 잘못 닫힌 실측) 도는 턴 위에 쓰게 된다.
    원장이 조용하면 몸에게 묻고, 몸이 "도는 턴 없다"고 답할 때만 짧은 유예로 간다."""
    db_path = os.path.join(repo, "data", "world_pulse.db")
    if not episode_id and os.path.exists(db_path):
        episode_id = _resolve_open_episode(db_path, agent_id)
        if episode_id:
            _log(f"에피소드 문맥 없음 → 열린 턴 재해소 (episode {episode_id}"
                 f"{', agent=' + agent_id if agent_id else ''})")
    if not episode_id or not os.path.exists(db_path):
        # ★원장이 '열린 턴 없음'이라고 해서 아무도 안 도는 것은 아니다 (2026-08-23, ep1689):
        #   그 표식은 지워질 수 있다(살아 있는 행이 고아로 잘못 닫힌 실측). 원장이 침묵하면
        #   **몸에게 직접 묻는다** — 두 번째 출처가 없으면 틀린 한 벌이 곧 결론이 된다.
        reached, live = _probe_live_turns()
        if reached and live:
            episode_id = max(live)
            _log(f"원장엔 열린 턴이 없지만 몸이 도는 턴을 신고 — episode {live} → "
                 f"{episode_id} 이 닫히기를 기다린다")
        elif reached and live is None:
            _log(f"판정 불능(몸은 살아 있는데 live_turns 를 모른다) — "
                 f"{UNKNOWN_LIVE_GRACE_S:.0f}초 재확인")
            t_u = time.time()
            while time.time() - t_u < UNKNOWN_LIVE_GRACE_S:
                time.sleep(3)
                again = _resolve_open_episode(db_path, agent_id) if os.path.exists(db_path) else None
                if not again:
                    _, live2 = _probe_live_turns()
                    again = max(live2) if live2 else None
                if again:
                    episode_id = again
                    _log(f"재확인에서 열린 턴 발견 (episode {episode_id})")
                    break
            if not episode_id:
                _log("재확인에도 도는 턴 없음 — 진행")
                return "no_turn"
        else:
            if reached:
                _log(f"몸이 '도는 턴 없음'으로 답함 — {NO_EPISODE_GRACE_S:.0f}초 유예 후 진행")
            else:
                _log(f"몸에 닿지 못함(백엔드 없음) — {NO_EPISODE_GRACE_S:.0f}초 유예 후 진행")
            time.sleep(NO_EPISODE_GRACE_S)
            return "no_turn"
    if not os.path.exists(db_path):
        # 몸은 턴을 신고했는데 원장 파일이 없다 — 닫힘을 볼 창이 없으므로 상한까지 몸에게만 묻는다.
        t_h = time.time()
        while time.time() - t_h < TURN_CLOSE_CAP_S:
            _, live = _probe_live_turns()
            if not live or episode_id not in live:
                _log(f"몸이 턴 종료를 신고 (episode {episode_id})")
                time.sleep(SETTLE_S)
                return "observed"
            time.sleep(2)
        _log(f"턴 종료 대기 상한({TURN_CLOSE_CAP_S:.0f}초) — 진행")
        return "cap"
    t0 = time.time()
    row = None
    gone_since = None
    while time.time() - t0 < TURN_CLOSE_CAP_S:
        row = _episode_row(db_path, episode_id)
        if row is not None and row[0]:
            _log(f"턴 종료 감지 (episode {episode_id}, {int(time.time() - t0)}초)")
            break
        # ★출처 교차(2026-09-06 ep2891): 원장만 믿으면 재기동에 잘린 턴(END 못 씀·부팅 회수도 건너뜀)의
        #   행이 영영 NULL 이라 상한까지 헛기다린다. 몸에게도 묻는다 — 몸이 살아서 "그 턴 없다"고
        #   답하는데 원장이 유예 안에 닫히지 않으면 잘린 턴이다. 몸이 안 닿거나(재기동 중) 모르면(옛 몸)
        #   원장만 본다 — '못 봤다'는 '없다'가 아니다(B28-1).
        reached, live = _probe_live_turns()
        if reached and live is not None and int(episode_id) not in live:
            gone_since = gone_since or time.time()
            if time.time() - gone_since >= BODY_GONE_CONFIRM_S:
                _log(f"몸은 '턴 {episode_id} 안 돈다'고 답하는데 원장은 열린 채 "
                     f"{BODY_GONE_CONFIRM_S:.0f}초 — 재기동에 잘린 턴으로 판정, 진행 "
                     f"({int(time.time() - t0)}초)")
                return "cut"
        else:
            gone_since = None
        time.sleep(2)
    else:
        _log(f"턴 종료 대기 상한({TURN_CLOSE_CAP_S:.0f}초) — 턴이 끊긴 것으로 보고 진행")
        return "cap"
    # 증류 재합류: distill 스레드의 finally 가 refresh_episode 로 log 를 한 번 다시 쓴다.
    # 미감지=증류 생략/무변화/미배선 부류 — 상한 후 진행(적용을 볼모로 잡지 않는다).
    base_len = row[1] or 0
    t1 = time.time()
    while time.time() - t1 < DISTILL_GRACE_S:
        row = _episode_row(db_path, episode_id)
        if row is not None and (row[1] or 0) != base_len:
            _log(f"증류 재합류 감지 ({int(time.time() - t1)}초)")
            time.sleep(SETTLE_S)
            return "observed"
        time.sleep(3)
    _log(f"증류 재합류 미감지({DISTILL_GRACE_S:.0f}초) — 진행")
    return "observed"      # 턴 종료는 봤다 — 증류만 못 봤을 뿐(적용을 볼모로 잡지 않는다)


def _wait_healthy(cap_s: float) -> bool:
    """적용 리로드가 끝나 몸이 다시 200 을 낼 때까지 — 검증 명령이 죽은 몸을 때리지 않게."""
    t = time.time()
    while time.time() - t < cap_s:
        reached, _ = _probe_live_turns()
        if reached:
            return True
        time.sleep(2)
    return False


def _run_post_verify(repo: str, cmd: str) -> dict:
    """적용 후 검증 명령을 **여기서** 돌린다 — 죽음을 넘는 프로세스가 소유한다(2026-08-25).

    ★왜: 턴은 자기 죽음 이후를 볼 수 없는데, backend 수리의 결과는 죽음 뒤에야 관측된다.
    검증을 턴에 남겨두면 AI 는 자기 턴 안에서 '적용됐나' 를 폴링하게 되고, 그 기다림이
    바로 적용을 막는다(자기 자신이 병목). 그래서 확인할 명령을 예약과 함께 위탁받아
    적용 뒤 여기서 돌리고, 결과를 다음 턴 보고에 실어 보낸다.

    권한은 새로 열리지 않는다 — 이 명령은 예약을 낸 그 턴이 이미 셸로 돌릴 수 있던 것이고,
    바뀐 것은 **실행 시점**뿐이다. 대신 시간(타임아웃)·출력량(캡)은 여기서 묶는다."""
    import subprocess
    if not _wait_healthy(VERIFY_HEALTH_WAIT_S):
        _log(f"검증 위탁: 몸이 {VERIFY_HEALTH_WAIT_S:.0f}초 안에 돌아오지 않음 — 그래도 실행")
    _log(f"검증 위탁 실행: {cmd[:160]}")
    try:
        r = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True,
                           text=True, timeout=VERIFY_TIMEOUT_S)
        out = ((r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr else ""))
        return {"ran": True, "cmd": cmd, "exit_code": r.returncode,
                "output": out.strip()[:VERIFY_OUTPUT_CAP],
                "truncated": len(out) > VERIFY_OUTPUT_CAP}
    except subprocess.TimeoutExpired:
        return {"ran": True, "cmd": cmd, "exit_code": None,
                "output": f"검증 명령이 상한({VERIFY_TIMEOUT_S:.0f}초)을 넘겨 중단됐습니다.",
                "timed_out": True}
    except Exception as e:
        return {"ran": True, "cmd": cmd, "exit_code": None, "output": f"실행 실패: {e!r}"}


def _load_handler(job: dict):
    """system_essentials handler 로드 — 안전판(prepare/finalize)을 재사용하기 위해.
    _REPO_ROOT 는 대상 repo 로 맞춘다(가짜 저장소 테스트에서 코드 루트와 갈라진다)."""
    hpath = job.get("handler_path") or str(
        CODE_ROOT / "data" / "packages" / "installed" / "tools"
        / "system_essentials" / "handler.py")
    spec = importlib.util.spec_from_file_location("se_handler_deferred", hpath)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    handler._REPO_ROOT = Path(job["repo"])
    return handler


def main() -> int:
    job_path = sys.argv[1]
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    repo = job["repo"]
    _log(f"기동 — key={job['key']} episode={job.get('episode_id')} repo={repo}")

    wait_outcome = wait_turn_closed(repo, job.get("episode_id"),
                                    agent_id=job.get("agent_id")) or "observed"
    if wait_outcome == "cap":
        _log("★상한 강행 — 예약한 턴이 스스로 닫히지 않았다. 대개 그 턴이 적용을 기다리며 "
             "살아 있던 경우이고, 그러면 이 대기는 통째로 낭비다. 다음 턴 보고에 싣는다.")
    elif wait_outcome == "cut":
        _log("예약한 턴은 재기동에 잘려 원장에 닫힘 기록이 없었다 — 몸의 신고로 판정했다(상한 대기 없음). "
             "다음 턴 보고에 싣는다.")

    # 코드 루트의 backend 를 sys.path 에 — red_grant/thread_context/episode_logger 등
    sys.path.insert(0, str(CODE_ROOT / "backend"))
    import boot_paths  # noqa: F401
    from red_grant import issue_grant
    from thread_context import set_current_task_id, set_current_agent_id

    # ①′ 도는 턴 0 + 재기동 관문 — 예약한 턴 다음에 시작한 턴도 자르지 않는다(2026-09-02)
    quiesce = wait_quiescent(repo, job["key"], exclude_episode=job.get("episode_id"))

    task_id = job.get("task_id") or job["key"]
    agent_id = job.get("agent_id") or "system_ai"
    set_current_task_id(task_id)
    set_current_agent_id(agent_id)
    issue_grant(agent_id=agent_id, task_id=task_id,
                reason=f"지연 적용 수행: {job.get('reason') or job['key']}")

    gate = _gate_mod()
    try:
        handler = _load_handler(job)
        staging = handler._staging_mod()
        out = staging.perform_scheduled_apply(
            repo, job["key"],
            prepare=handler._red_write_prepare, finalize=handler._red_write_finalize)
    except BaseException:
        gate.lower_gate(repo, job["key"])       # 못 썼으면 관문은 거짓말이다 — 즉시 내린다
        raise
    _log(f"결과: {json.dumps(out, ensure_ascii=False)[:500]}")
    if out.get("applied"):
        # 썼다 — 리로드가 온다. 관문을 written 으로 올려 새 몸이 부팅에서 회수하게 한다.
        gate.mark_written(repo, job["key"])
    else:
        gate.lower_gate(repo, job["key"])

    # 적용 후 검증 — 위탁받았을 때만. 적용이 안 일어났으면 돌릴 이유가 없다.
    cmd = (job.get("verify_cmd") or "").strip()
    post = None
    if cmd:
        post = (_run_post_verify(repo, cmd) if out.get("applied") else
                {"ran": False, "cmd": cmd,
                 "output": "적용이 일어나지 않아 검증 명령을 돌리지 않았습니다."})

    # 후속 기록 — result.json 을 워치독이 나중에 통째로 덮으므로 **옆자리 파일**에 남긴다.
    try:
        staging.write_followup(repo, staging.task_key(job["key"]), {
            "wait_outcome": wait_outcome,
            "turn_cap_s": TURN_CLOSE_CAP_S,
            "episode_id": job.get("episode_id"),
            "quiesce_outcome": quiesce.get("outcome"),
            "quiesce_wait_s": quiesce.get("waited_s"),
            "quiesce_cap_s": QUIESCE_CAP_S,
            "live_turns_at_cap": quiesce.get("live_turns") if quiesce.get("outcome") == "cap" else [],
            "post_verify": post,
        })
    except Exception as e:
        _log(f"후속 기록 실패(계속): {e}")

    try:
        job["done_at"] = datetime.now().isoformat()
        job["applied"] = bool(out.get("applied"))
        job["wait_outcome"] = wait_outcome
        job["quiesce_outcome"] = quiesce.get("outcome")
        job["quiesce_wait_s"] = quiesce.get("waited_s")
        if post is not None:
            job["post_verify"] = post
        job["outcome_note"] = (out.get("error") or out.get("message") or out.get("note") or "")[:300]
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"잡 파일 갱신 실패(계속): {e}")
    return 0 if out.get("applied") or out.get("success") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        _log(f"치명 오류: {e!r}")
        raise SystemExit(2)
