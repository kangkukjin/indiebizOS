"""
episode_orphans.py - 끝을 못 본 턴의 회수 (episode_logger 형제 모듈, 2026-09-06 분할)

원장 행의 ended_at NULL 은 "이 턴은 끝을 못 봤다"는 정직한 신호다. 여기는 그 행을 **누가, 언제**
닫아도 되는지의 규칙 한 벌:
  - 부팅 회수(_sweep_orphan_episodes): 주인 프로세스가 죽었고 자식 궤적도 식은 행만(ep1689·ep2393).
    '숨 쉬는' 행을 남기면 신선 창 뒤 재회수를 예약한다(_arm_resweep, ep2891).
  - 자르는 쪽이 닫기(close_cut_episodes): 정적 대기 상한에 닿아 강행하는 재기동(리로더·수행자)이
    자기가 자를 턴을 CUT 표식으로 닫는다 — 죽는 쪽도, 다음 부팅도 못 하는 일(ep2891).

원장 접속(_get_db)·stdout 은 episode_logger 의 것을 **호출 시점에** 빌린다 — 시험이 EL._get_db 를
갈아 끼우는 표면을 보존하고, 순환 import 를 피한다. 이름은 episode_logger 가 재수출한다.
"""
import os
import sqlite3
import threading
from datetime import datetime


def _EL():
    import episode_logger
    return episode_logger


ORPHAN_MARK = "[Episode ORPHAN] 종료 기록 없이 끊긴 턴 — 다음 부팅이 회수함"
# 재기동 강행에 잘리는 턴 — 자르는 쪽(리로더·수행자)이 자르기 *전에* 닫는다(2026-09-06 ep2891).
# ★왜: 정적 대기 상한에 닿아 강행한 재기동은 도는 턴을 죽인다. 죽는 턴은 END 를 못 쓰고,
#   부팅 회수는 그 턴의 궤적이 '신선'해서(자식 run 보존 규칙) 건너뛴다 — 행은 영영 NULL 로 남고
#   red_apply 는 그 행이 닫히길 900초 기다렸다(실측 05:19→05:34). 죽음 뒤를 죽는 쪽에 맡기지
#   말 것: 죽음을 *일으키는* 프로세스가 자기가 자르는 턴을 안다 — 그 손이 닫는다.
CUT_MARK = "[Episode CUT] 재기동 강행에 잘린 턴 — 자른 쪽이 닫음"

# ─── 자식 run 은 주인보다 오래 산다 (2026-08-30, ep2393 실측) ──────────────────
# ★무엇이 틀렸었나: 행의 '주인'은 턴을 연 **백엔드 프로세스**인데, 정작 일을 하는 것은
#   그 프로세스가 띄운 **자식 run**(Claude Code 하위 프로세스)이다. 자식은 부모의 죽음을
#   넘어 살아남아 새 백엔드에 MCP 로 계속 붙는다. 실측: ep2393 은 19:13:56 에 고아로
#   회수됐지만 자식 run_cfe1362740d6aab22c53 은 **19:56:06까지** IBL 을 쐈고, 그 사이
#   19:37 에 같은 메시지의 재시도(ep2406)가 떠 19분간 두 실행이 겹쳤다.
# ★그래서 생사의 출처를 두 벌로 둔다: ①주인 프로세스 ②이 에피소드에 달린 궤적의 최신성.
#   둘 중 하나라도 살아 있으면 보존한다 — 위 _owner_is_alive 의 원칙("틀린 보존이 틀린
#   회수보다 싸다")을 자식 쪽으로 그대로 연장한 것이다.
_CHILD_TRACE_FRESH_SEC = 900     # 궤적이 이만큼 안에 찍혔으면 그 run 은 아직 도는 중

# ★왜 여기서 궤적을 되읽나: 고아 행의 로그는 죽은 프로세스의 **메모리 버퍼**에 있어서
#   함께 사라진다. 하지만 자식이 남긴 trajectory_event 에는 액션명·성공·소요가 이미
#   있다(비밀 없는 구조 흔적). 회수할 때 그걸 로그로 되돌려 적어야 증류가 끊기지 않는다.
def _episode_trajectory_trace(conn, episode_id):
    """이 에피소드 궤적의 (마지막 시각, 호출 수, 액션명 목록). 없으면 None."""
    try:
        rows = conn.execute(
            "SELECT ts, kind, data FROM trajectory_event WHERE episode_id = ? ORDER BY ts",
            (episode_id,)).fetchall()
    except Exception:
        return None            # 궤적 테이블이 없는 몸 — 판정 불능은 '없음'으로 두고 주인만 본다
    if not rows:
        return None
    import json as _json
    actions, calls = [], 0
    for _ts, kind, data in rows:
        if kind != "ibl.started":
            continue
        calls += 1
        try:
            actions.extend(_json.loads(data or "{}").get("actions") or [])
        except Exception:
            pass
    return rows[-1][0], calls, actions


def _trace_is_fresh(last_ts) -> bool:
    """마지막 흔적이 아직 따끈한가 — 판정 불능은 '살아 있다'로 둔다(보존 우선)."""
    try:
        return (datetime.now() - datetime.fromisoformat(last_ts)).total_seconds() \
            < _CHILD_TRACE_FRESH_SEC
    except Exception:
        return True


def _orphan_trace_line(calls, actions):
    """회수 행에 붙일 구조 흔적 한 줄 — 액션명·횟수만(값·결과는 넣지 않는다)."""
    if not calls:
        return ""
    from collections import Counter
    top = ", ".join(f"{a}×{n}" if n > 1 else a
                    for a, n in Counter(actions).most_common(12))
    more = "" if len(set(actions)) <= 12 else f" 외 {len(set(actions)) - 12}종"
    return (f"[Episode ORPHAN 궤적] 이 턴은 로그 버퍼를 잃었지만 자식 run 의 흔적이 "
            f"남아 있다 — IBL {calls}회: {top}{more}\n")

# ─── 행의 주인 — 회수는 **죽은 프로세스의 행만** 닫는다 (2026-08-23, ep1689) ────────
# ★왜: 옛 회수는 "지금 막 뜬 프로세스보다 먼저 시작된 미종료 행은 정의상 죽은 턴"을
#   전제했다. 그 전제는 **서버 진입점에서만** 참이다. 실측(31회차): 살아 있는 백엔드가
#   도는 중에 그 턴이 격리 사본에서 프로브를 띄우며 INDIEBIZ_BASE_PATH 를 라이브로
#   겨눴고, 그 프로브가 boot_common.wire_local_subsystems() → install() → 회수를 돌려
#   **자기 자신의 살아 있는 행**을 12:33:03 에 ORPHAN 으로 닫았다. 7분 뒤 red_apply 는
#   "열린 턴 없음"으로 읽고(그 표식이 유일한 근거였다) 10초 유예 뒤 라이브에 썼다 —
#   리로드가 그 턴을 끊었다. 자기를 지켜줄 표식을 자기가 지운 것이다.
# ⇒ 판정 근거를 '시간 순서'(추정)에서 '주인의 생사'(실측)로 옮긴다. 표식은 기계가 소유한다.
def _process_stamp(pid: int):
    """프로세스 시작시각 도장 — pid 재사용을 가른다. 못 구하면 None(판정 불능)."""
    try:
        import psutil
        return str(int(psutil.Process(pid).create_time()))
    except Exception:
        return None            # psutil 없는 몸(폰 번들 등) — pid 만으로 판정한다


def _process_identity(pid: int = None) -> str:
    """`pid:시작시각` — 행에 적는 주인 표식."""
    pid = pid or os.getpid()
    return f"{pid}:{_process_stamp(pid) or ''}"


def _owner_is_alive(owner) -> bool:
    """이 행의 주인이 아직 살아 있는가.

    ★판정 불능은 '없다'로 뭉개지 않는다(B28-1) — 도장을 대조 못 하면 **살아 있다고**
    본다. 틀린 보존(행이 열린 채 남아 red_apply 가 상한까지 기다림)이 틀린 회수(도는
    턴을 죽었다고 선언 → 그 턴이 절단됨)보다 언제나 싸다.
    """
    if not owner:
        return False           # 칸이 생기기 전의 옛 행 — 종전대로 회수한다
    pid_s, _, stamp = str(owner).partition(":")
    try:
        pid = int(pid_s)
    except ValueError:
        return False
    if pid <= 0:
        return False
    try:
        from common.platform_utils import pid_alive  # 생사 판정 단일 소스(전 OS)
    except Exception:
        return True            # 판정 불능 → 보존
    if not pid_alive(pid):
        return False           # 주인은 죽었다 — 회수 대상
    if not stamp:
        return True            # 도장 없는 행(psutil 없는 몸) — pid 생존만으로 보존
    now = _process_stamp(pid)
    return True if now is None else now == stamp


_resweep_timer = None      # 신선 창 뒤 재회수 예약(부팅 회수가 '자식 숨 쉬는 중'으로 건너뛴 행)


def _arm_resweep(delay_s: float):
    """'주인은 죽었지만 궤적이 신선' 행이 있으면 신선 창이 지난 뒤 한 번 더 회수한다.

    ★왜(2026-09-06 ep2891): 회수는 부팅 때만 돌았다. 재기동에 잘린 턴은 마지막 궤적이 몇 초 전이라
    부팅 회수가 보존하고, 그 뒤 아무도 다시 묻지 않아 행이 영영 NULL 로 남았다. 신선 규칙은 맞다
    (ep2393) — 빠진 것은 신선이 *끝난 뒤*의 두 번째 물음이다."""
    global _resweep_timer
    if _resweep_timer is not None and _resweep_timer.is_alive():
        return
    t = threading.Timer(delay_s, _sweep_orphan_episodes)
    t.daemon = True
    t.name = "episode-resweep"
    _resweep_timer = t
    t.start()


def _sweep_orphan_episodes():
    """남아 있는 미종료 행 중 **주인이 죽은 것만** 닫는다.

    ★ended_at NULL 은 '이 턴은 끝을 못 봤다'는 정직한 신호지만, 죽은 뒤에는 그걸 닫을
    주체가 없다. 그래서 뜬 프로세스가 대신 닫되, **누구의 행인지 물어보고** 닫는다.
    리로드·크래시·kill 로 죽은 주인의 행은 같은 그물에 걸리고, 살아 있는 백엔드의
    도는 턴은 어떤 프로세스가 이 함수를 불러도 건드려지지 않는다.

    total_ms 는 NULL 로 남긴다 — 정상 종료(측정값 있음)와 회수(측정 불가)를 구별하는 표식.
    """
    try:
        conn = _EL()._get_db()
        now = datetime.now().isoformat()
        rows = conn.execute(
            "SELECT id, owner FROM episode_log WHERE ended_at IS NULL").fetchall()
        # 생사의 출처 두 벌: ①주인 프로세스 ②이 에피소드 궤적의 최신성(자식 run).
        # 자식이 아직 돌고 있으면 주인이 죽었어도 회수하지 않는다 — 회수해 버리면
        # 그 턴은 원장에서 사라진 채 계속 일하고, 사용자의 재시도와 겹친다(ep2393).
        dead, alive, breathing = [], 0, 0
        for _id, _owner in rows:
            if _owner_is_alive(_owner):
                alive += 1
                continue
            trace = _episode_trajectory_trace(conn, _id)
            if trace and _trace_is_fresh(trace[0]):
                breathing += 1
                continue
            dead.append((_id, trace))
        n = 0
        for _id, trace in dead:
            # 끝난 시각은 **자식의 마지막 흔적**이 있으면 그것 — 회수를 돌린 부팅 시각으로
            # 적으면 원장이 거짓말을 한다(ep2393: 19:13:56 로 닫혔지만 일은 19:56 까지).
            ended = trace[0] if trace else now
            tail = "\n" + ORPHAN_MARK + "\n"
            if trace:
                tail += _orphan_trace_line(trace[1], trace[2])
            cur = conn.execute(
                "UPDATE episode_log SET ended_at = ?, log = COALESCE(log, '') || ? "
                "WHERE id = ?", (ended, tail, _id))
            n += cur.rowcount or 0
        conn.commit()
        conn.close()
        if breathing:
            _arm_resweep(_CHILD_TRACE_FRESH_SEC + 5)
        if n or alive:
            try:
                if _EL().EpisodeLogger._original_stdout:
                    _EL().EpisodeLogger._original_stdout.write(
                        f"[EpisodeLogger] 미종료 에피소드 {n}건 회수 — 이전 프로세스가 "
                        f"끊긴 자리(리로드·크래시). 기록은 보존됩니다."
                        + (f" (주인이 살아 있어 건드리지 않음: {alive}건)" if alive else "")
                        + (f" (주인은 죽었지만 자식 run 이 도는 중: {breathing}건)"
                           if breathing else "") + "\n")
            except Exception:
                pass
    except Exception:
        pass


def close_cut_episodes(ids, reason: str, db_path: str = None) -> int:
    """재기동 강행이 자를 턴들을 원장에서 닫는다(ended_at=지금, CUT 표식 + 궤적 한 줄).

    다른 프로세스(uvicorn 리로더·red_apply 수행자)가 부른다 — 이 프로세스의 _live 집합은 건드릴 것이
    없다. 이미 닫힌 행은 건너뛴다(WHERE ended_at IS NULL). 그 턴이 죽기 전에 스스로 END 를 쓰면
    _close_episode 의 UPDATE 가 본 로그로 덮는다 — 두 손이 같은 행에 써도 진실이 이긴다.
    반환: 닫은 행 수."""
    ids = [int(i) for i in (ids or []) if str(i).strip().lstrip("-").isdigit()]
    if not ids:
        return 0
    try:
        conn = sqlite3.connect(db_path, timeout=5) if db_path else _EL()._get_db()
        now = datetime.now().isoformat()
        n = 0
        for eid in ids:
            trace = _episode_trajectory_trace(conn, eid)
            tail = "\n" + CUT_MARK + (f" ({reason})" if reason else "") + "\n"
            if trace:
                tail += _orphan_trace_line(trace[1], trace[2])
            cur = conn.execute(
                "UPDATE episode_log SET ended_at = ?, log = COALESCE(log, '') || ? "
                "WHERE id = ? AND ended_at IS NULL", (now, tail, eid))
            n += cur.rowcount or 0
        conn.commit()
        conn.close()
        return n
    except Exception:
        return 0
