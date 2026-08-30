"""고아 회수는 **죽은 프로세스의 행만** 닫는다 + 적용 대기의 두 번째 출처 (2026-08-23, ep1689)

재현하는 사고(31회차 상상훈련 절단):
  12:18 턴 시작 → 12:33:03 그 턴이 격리 사본에서 띄운 프로브가 라이브를 겨눈 채
  boot_common.wire_local_subsystems() → EpisodeLogger.install() → 고아 회수를 돌려
  **살아 있는 자기 행**을 ORPHAN 으로 닫았다 → 12:40 red_apply 가 "열린 턴 없음"으로
  읽고 10초 유예 뒤 라이브 4파일 적용 → 리로드가 그 턴을 끊었다(최종 보고·GoalEval 유실).

세 겹으로 막는다:
  ①회수 판정을 '시간 순서'(추정)에서 '주인의 생사'(실측)로 — episode_log.owner
  ②원장이 침묵할 때 몸에게 직접 묻기 — /health 의 live_turns (못 봤다 ≠ 없다, B28-1)
  ③되돌릴 수 없는 부팅 부작용은 부팅 주체만 — boot_common._another_body_is_live 게이트

실행: .venv/bin/python -m pytest backend/test_episode_owner_sweep.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _tmp_db(tmp_path):
    """episode 스키마만 있는 빈 DB — 라이브 원장을 건드리지 않는다."""
    import episode_logger as EL
    path = str(tmp_path / "world_pulse.db")

    def _get_db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    orig = EL._get_db
    EL._get_db = _get_db
    try:
        EL._ensure_episode_tables()
    except Exception:
        EL._get_db = orig
        raise
    return path, orig


def _open_row(path, owner, ended=None):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO episode_log (started_at, ended_at, agent, user_message, log, total_ms,"
        " task_id, source, owner) VALUES ('2026-08-23T12:18:00', ?, 'system_ai', 'm', '',"
        " NULL, '', 'usage', ?)", (ended, owner))
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return eid


def _row(path, eid):
    conn = sqlite3.connect(path)
    r = conn.execute("SELECT ended_at, COALESCE(log,'') FROM episode_log WHERE id=?",
                     (eid,)).fetchone()
    conn.close()
    return r


def _dead_pid():
    """확실히 죽은 pid — 자식을 띄워 거둔 뒤 그 번호를 쓴다.

    fork() 를 쓰지 않는다: pytest 는 스레드가 도는 프로세스라 fork 가 교착을 부를 수 있다.
    """
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# ─── O1~O3: 회수 판정 ────────────────────────────────────────────────────────

def test_o1_live_owner_row_is_not_swept(tmp_path):
    """★사고의 심장: 살아 있는 주인의 행은 누가 회수를 돌려도 닫히지 않는다."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, EL._process_identity())   # 주인 = 지금 이 프로세스
        EL._sweep_orphan_episodes()                     # 프로브가 부른 회수 흉내
        ended, log = _row(path, eid)
        assert ended is None, "살아 있는 턴이 고아로 닫혔다 — ep1689 재발"
        assert EL.ORPHAN_MARK not in log
    finally:
        EL._get_db = orig


def test_o2_dead_owner_row_is_swept(tmp_path):
    """죽은 주인의 행은 여전히 회수된다 — 보존이 회수를 삼키면 안 된다(무기력 방지)."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, f"{_dead_pid()}:1")
        EL._sweep_orphan_episodes()
        ended, log = _row(path, eid)
        assert ended, "죽은 주인의 행이 영원히 열린 채 남는다 — apply 가 상한까지 헛기다린다"
        assert EL.ORPHAN_MARK in log
    finally:
        EL._get_db = orig


def test_o3_legacy_row_without_owner_is_swept(tmp_path):
    """칸이 생기기 전의 옛 행(owner NULL)은 종전대로 회수 — 없는 사실을 지어내지 않는다."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, None)
        EL._sweep_orphan_episodes()
        ended, _ = _row(path, eid)
        assert ended
    finally:
        EL._get_db = orig


def test_o4_pid_reuse_and_unknown_stamp(tmp_path):
    """도장은 pid 재사용을 가르고, 도장을 못 읽으면 **살아 있다고** 본다(판정 불능≠없음)."""
    import episode_logger as EL
    me = os.getpid()
    assert EL._owner_is_alive(EL._process_identity()) is True
    assert EL._owner_is_alive(f"{me}:1") is False, "pid 재사용을 못 가른다"
    assert EL._owner_is_alive(f"{me}:") is True, "도장 없는 옛 몸의 행을 죽었다고 단정했다"
    assert EL._owner_is_alive(f"{_dead_pid()}:") is False
    assert EL._owner_is_alive("") is False and EL._owner_is_alive("x:1") is False


# ─── O5: 주인 기록 · 라이브 등기 ──────────────────────────────────────────────

def test_o5_open_records_owner_and_registers_live(tmp_path):
    """행을 열 때 주인을 적고, 이 프로세스의 '지금 도는 턴'에 등기한다(=/health 의 출처)."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = EL._open_episode(None, "system_ai", "m", "task_x")
        assert eid in EL.live_episode_ids()
        conn = sqlite3.connect(path)
        owner = conn.execute("SELECT owner FROM episode_log WHERE id=?", (eid,)).fetchone()[0]
        conn.close()
        assert owner == EL._process_identity()
        EL._close_episode(eid, None, "system_ai", "m", "log", 1)
        assert eid not in EL.live_episode_ids(), "닫힌 턴이 '도는 턴'으로 남으면 apply 가 헛기다린다"
    finally:
        EL._get_db = orig


# ─── O6~O8: 적용 대기의 두 번째 출처 ─────────────────────────────────────────

def _red_apply():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "datastore"))
    import red_apply
    return red_apply


def _repo(tmp_path):
    """가짜 저장소 — data/world_pulse.db 가 **있는** 상태(원장 창은 열려 있다)."""
    (tmp_path / "data").mkdir()
    sqlite3.connect(str(tmp_path / "data" / "world_pulse.db")).close()
    return str(tmp_path)


def test_o6_health_reported_turn_blocks_apply(tmp_path):
    """★원장이 침묵해도 몸이 턴을 신고하면 기다린다 — 이 한 겹이 ep1689 를 막는다."""
    ra = _red_apply()
    repo = _repo(tmp_path)
    orig_probe, orig_row, orig_distill = ra._probe_live_turns, ra._episode_row, ra.DISTILL_GRACE_S
    seen = {"polls": 0}

    def _probe(url=None):
        return True, [4242]

    def _episode_row(db_path, eid):
        seen["polls"] += 1
        assert eid == 4242, "몸이 신고한 턴이 아니라 다른 걸 기다린다"
        return ("2026-08-23T12:41:00", 10) if seen["polls"] > 1 else (None, 10)

    ra._probe_live_turns, ra._episode_row = _probe, _episode_row
    ra.DISTILL_GRACE_S = 0
    try:
        ra.wait_turn_closed(repo, None, "system_ai")
        assert seen["polls"] >= 2, "기다리지 않고 즉시 진행했다 — 도는 턴 위에 쓴다"
    finally:
        ra._probe_live_turns, ra._episode_row, ra.DISTILL_GRACE_S = (
            orig_probe, orig_row, orig_distill)


def test_o7_body_says_no_turn_short_grace(tmp_path):
    """몸이 '도는 턴 없음'으로 **판정**했으면 짧은 유예로 진행 — 게이트가 볼모가 되면 안 된다."""
    ra = _red_apply()
    repo = _repo(tmp_path)
    orig_probe, orig_grace = ra._probe_live_turns, ra.NO_EPISODE_GRACE_S
    ra._probe_live_turns = lambda url=None: (True, [])
    ra.NO_EPISODE_GRACE_S = 0
    try:
        import time
        t0 = time.time()
        ra.wait_turn_closed(repo, None, "system_ai")
        assert time.time() - t0 < 5
    finally:
        ra._probe_live_turns, ra.NO_EPISODE_GRACE_S = orig_probe, orig_grace


def test_o8_unknown_is_not_zero(tmp_path):
    """몸은 살아 있는데 live_turns 를 모르면 '없다'가 아니라 '판정 불능' — 다시 묻는다(B28-1)."""
    ra = _red_apply()
    repo = _repo(tmp_path)
    orig_probe, orig_unknown, orig_row = ra._probe_live_turns, ra.UNKNOWN_LIVE_GRACE_S, ra._episode_row
    orig_distill = ra.DISTILL_GRACE_S
    calls = {"n": 0}

    def _probe(url=None):
        calls["n"] += 1
        return (True, None) if calls["n"] == 1 else (True, [77])

    ra._probe_live_turns = _probe
    ra.UNKNOWN_LIVE_GRACE_S = 10
    ra.DISTILL_GRACE_S = 0
    ra._episode_row = lambda db_path, eid: ("2026-08-23T12:41:00", 10)
    try:
        ra.wait_turn_closed(repo, None, "system_ai")
        assert calls["n"] >= 2, "판정 불능을 '턴 없음'으로 뭉갰다"
    finally:
        ra._probe_live_turns, ra.UNKNOWN_LIVE_GRACE_S, ra._episode_row = (
            orig_probe, orig_unknown, orig_row)
        ra.DISTILL_GRACE_S = orig_distill


# ─── O9: 부팅 부작용 게이트 ──────────────────────────────────────────────────

def test_o9_live_body_probe_discriminates():
    """살아 있는 몸이 있으면 True, 아무도 없으면 False — 삭제성 부팅 부작용의 게이트."""
    import http.server
    import threading
    import boot_common

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","live_turns":[]}')

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prev = os.environ.get("INDIEBIZ_API_PORT")
    try:
        os.environ["INDIEBIZ_API_PORT"] = str(port)
        assert boot_common._another_body_is_live() is True
        srv.shutdown()
        srv.server_close()
        assert boot_common._another_body_is_live() is False, "죽은 뒤에도 게이트가 닫혀 있으면 부팅이 정리를 영영 못 한다"
    finally:
        if prev is None:
            os.environ.pop("INDIEBIZ_API_PORT", None)
        else:
            os.environ["INDIEBIZ_API_PORT"] = prev


def test_o10_cleanup_is_gated_at_the_call_site():
    """게이트가 *호출부*에 서 있는지 — 헬퍼만 있고 안 쓰면 아무것도 막지 못한다."""
    import ast
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "boot_common.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "wire_local_subsystems")
    gated = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_cleanup_completed_tasks"
                     for c in ast.walk(n))]
    assert gated, "완료 task 정리가 게이트 밖에 있다 — 프로브가 라이브를 정리한다"


# ─── O11~O13: 자식 run 은 주인보다 오래 산다 (2026-08-30, ep2393) ────────────────
# 재현하는 사고: 19:13:29 턴 시작(주인 pid 11816) → 19:13:56 백엔드가 죽고 새 백엔드가
# 부팅하며 그 행을 고아로 회수 → 그런데 **자식 run 은 살아서** 19:56:06 까지 IBL 을 쐈다.
# 원장에서 사라진 턴이 계속 일하는 동안 19:37 에 같은 메시지의 재시도가 떠 19분 겹쳤다.

def _traj(path, episode_id, ts, kind="ibl.started", actions=("self:read",)):
    """궤적 한 줄 — 자식 run 이 남기는 흔적(비밀 없는 구조 정보)."""
    import json
    conn = sqlite3.connect(path)          # 스키마는 _ensure_episode_tables 가 이미 세웠다
    seq = (conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM trajectory_event"
                        " WHERE run_id = 'run_child'").fetchone()[0])
    conn.execute("INSERT INTO trajectory_event (run_id, event_seq, episode_id, task_id,"
                 " parent_run_id, ts, kind, data, source)"
                 " VALUES ('run_child', ?, ?, '', 'run_parent', ?, ?, ?, 'usage')",
                 (seq, episode_id, ts, kind, json.dumps({"actions": list(actions)})))
    conn.commit()
    conn.close()


def test_o11_row_with_breathing_child_is_not_swept(tmp_path):
    """★사고의 심장: 주인은 죽었어도 **자식이 도는 중**이면 회수하지 않는다."""
    import episode_logger as EL
    from datetime import datetime
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, f"{_dead_pid()}:1")       # 주인은 확실히 죽음
        _traj(path, eid, datetime.now().isoformat())     # 그러나 자식은 방금 흔적을 남김
        EL._sweep_orphan_episodes()
        ended, log = _row(path, eid)
        assert ended is None, "자식이 도는 턴을 회수했다 — ep2393 재발(중복 실행·학습 유실)"
        assert EL.ORPHAN_MARK not in log
    finally:
        EL._get_db = orig


def test_o12_stale_child_closes_at_last_trace_not_boot_time(tmp_path):
    """자식도 조용해지면 닫되, **끝난 시각은 자식의 마지막 흔적**이다.

    부팅 시각으로 닫으면 원장이 거짓말을 한다(ep2393 은 19:13:56 로 닫혔지만 19:56 까지 일했다).
    """
    import episode_logger as EL
    from datetime import datetime, timedelta
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, f"{_dead_pid()}:1")
        last = (datetime.now() - timedelta(hours=3)).isoformat()
        _traj(path, eid, last, actions=("engines:web_site",))
        EL._sweep_orphan_episodes()
        ended, log = _row(path, eid)
        assert ended == last, f"끝난 시각이 자식의 마지막 흔적이 아니다: {ended}"
        assert EL.ORPHAN_MARK in log
    finally:
        EL._get_db = orig


def test_o13_orphan_keeps_structural_trace_for_distillation(tmp_path):
    """고아로 닫히더라도 **구조 흔적**(액션명·횟수)은 남아야 증류가 끊기지 않는다.

    로그 버퍼는 죽은 프로세스와 함께 사라지지만 궤적은 살아 있다 — 그걸 되돌려 적는다.
    값·결과는 넣지 않는다(비밀이 섞일 자리를 만들지 않는다).
    """
    import episode_logger as EL
    from datetime import datetime, timedelta
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, f"{_dead_pid()}:1")
        old = (datetime.now() - timedelta(hours=3)).isoformat()
        _traj(path, eid, old, actions=("limbs:browser", "engines:image_gemini"))
        _traj(path, eid, old, actions=("limbs:browser",))
        EL._sweep_orphan_episodes()
        _, log = _row(path, eid)
        assert "IBL 2회" in log, f"호출 수가 남지 않았다: {log!r}"
        assert "limbs:browser×2" in log, f"액션 흔적이 남지 않았다: {log!r}"
        assert "engines:image_gemini" in log
    finally:
        EL._get_db = orig


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import pytest
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
