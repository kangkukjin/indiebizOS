"""
test_quiescent_reload.py - 리로더가 도는 턴 0 을 기다리는지 (2026-09-02)

★왜: backend/*.py 를 바꾸는 손의 절반은 수리 경로 밖(Claude Code 세션·[self:script]·
run_command·git)이었다. 편집자마다 협조를 구하는 대신 **리로드 한 자리**에 그물을 쳤다 —
그 그물이 실제로 묻는지, 이음매가 설치된 uvicorn 에 살아 있는지, 순서가 맞는지를 지킨다.

  Q1 도는 턴이 있으면 기다리고 0 이 되면 진행 / 끝내 안 되면 상한 강행(잘릴 턴 이름) /
     몸이 없으면 자를 턴 없음 / 옛 몸(live_turns 없음)은 판정 불능=진행
  Q2 재기동 의례 — 0 을 본 순간 관문(written)을 세우고 되묻는다. 직후 들어온 턴엔 양보
     (관문 내림·재대기). 상한 강행이어도 관문은 선다. 몸이 없으면 관문도 없다.
  Q3 이음매 실측 — 설치된 uvicorn 의 run() 이 `ChangeReload` 이름으로 리로더를 고른다
     (install 이 갈아 끼우는 바로 그 이름). 버전이 바뀌어 이름이 사라지면 여기서 빨강.
  Q4 실제 서브클래스의 restart() 가 의례 **뒤에** 부모 restart 를 부른다 (순서)
  Q5 api.py __main__ 이 uvicorn.run 보다 **앞에서** install 을 부른다 (배선)
  Q6 관문은 새 몸의 부팅이 회수한다 (reload_gate.clear_at_boot 와 written 의 계약)

실행: python3 -m pytest backend/test_quiescent_reload.py -q
"""
import ast
import inspect
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
try:
    import boot_paths  # noqa: F401
except ImportError:
    pass

import quiescent_reload as qr   # noqa: E402
import reload_gate as rg        # noqa: E402


def _seq(seq):
    """probe 모형 — 순서대로 답하고 마지막 답을 반복한다. calls 에 호출 수를 센다."""
    it = iter(seq)
    last = [seq[-1]]
    calls = [0]

    def _probe():
        calls[0] += 1
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]
    _probe.calls = calls
    return _probe


def test_Q1_wait_for_quiet_outcomes():
    p = _seq([(True, [7]), (True, [7]), (True, [])])
    q = qr.wait_for_quiet("http://x", probe=p, cap_s=5, poll_s=0.01)
    assert q["outcome"] == "observed" and p.calls[0] == 3

    p = _seq([(True, [5])])
    q = qr.wait_for_quiet("http://x", probe=p, cap_s=0.05, poll_s=0.01)
    assert q["outcome"] == "cap" and q["live"] == [5], q

    q = qr.wait_for_quiet("http://x", probe=_seq([(False, None)]), cap_s=5, poll_s=0.01)
    assert q["outcome"] == "no_body"

    q = qr.wait_for_quiet("http://x", probe=_seq([(True, None)]), cap_s=5, poll_s=0.01)
    assert q["outcome"] == "unknown", "옛 몸(칸 없음)은 판정 불능 — 기다릴 근거가 없으니 진행"


def test_Q2_prepare_restart_gate_and_yield():
    tmp = tempfile.mkdtemp(prefix="qr_")
    # 0 을 본 순간 관문 → 되묻기 0 → 진행, 관문은 written
    p = _seq([(True, [3]), (True, []), (True, [])])
    q = qr.prepare_restart(tmp, "http://x", "r1", probe=p, cap_s=5, poll_s=0.01, settle_s=0)
    g = rg.read_gate(tmp)
    assert q["outcome"] == "observed" and q["gate"] is True
    assert g and g["key"] == "r1" and g["phase"] == "written", g
    rg.lower_gate(tmp, "r1")

    # 관문 직후 턴(9)이 들어오면 관문을 내리고 양보 — 그 턴이 끝난 뒤 다시 세운다
    p = _seq([(True, []), (True, [9]), (True, [9]), (True, []), (True, [])])
    q = qr.prepare_restart(tmp, "http://x", "r2", probe=p, cap_s=5, poll_s=0.01, settle_s=0)
    assert q["outcome"] == "observed" and p.calls[0] == 5, (q, p.calls)
    assert (rg.read_gate(tmp) or {}).get("key") == "r2"
    rg.lower_gate(tmp, "r2")

    # 상한 강행 — 잘릴 턴을 이름으로, 관문은 그래도 선다(새 턴은 되돌린다)
    q = qr.prepare_restart(tmp, "http://x", "r3", probe=_seq([(True, [5])]),
                           cap_s=0.05, poll_s=0.01, settle_s=0)
    assert q["outcome"] == "cap" and q["live"] == [5] and q["gate"] is True, q
    assert (rg.read_gate(tmp) or {}).get("key") == "r3"
    rg.lower_gate(tmp, "r3")

    # 몸이 없으면 자를 턴도, 관문도 없다
    q = qr.prepare_restart(tmp, "http://x", "r4", probe=_seq([(False, None)]),
                           cap_s=5, poll_s=0.01, settle_s=0)
    assert q["outcome"] == "no_body" and q["gate"] is False and rg.read_gate(tmp) is None


def test_Q3_installed_uvicorn_has_the_seam():
    import importlib
    um = importlib.import_module("uvicorn.main")      # `import uvicorn.main as um` 은 click Command 를 준다
    assert hasattr(um, "ChangeReload"), "uvicorn.main.ChangeReload 가 없다 — install 이 갈아 끼울 이름이 사라졌다"
    src = inspect.getsource(um.run)
    assert "ChangeReload(" in src, "uvicorn.run 이 ChangeReload 이름으로 리로더를 고르지 않는다 — 이음매 소실"
    # install 은 실제로 그 이름을 바꾼다(그리고 복원한다 — 다른 시험을 오염시키지 않게)
    orig = um.ChangeReload
    try:
        assert qr.install(tempfile.mkdtemp(prefix="qr_i_"), "http://127.0.0.1:1/health") is True
        assert um.ChangeReload is not orig and um.ChangeReload.__name__ == "QuiescentReload"
    finally:
        um.ChangeReload = orig


def test_Q4_subclass_restart_runs_rite_before_parent():
    from uvicorn.supervisors.watchfilesreload import WatchFilesReload
    tmp = tempfile.mkdtemp(prefix="qr_r_")
    cls = qr.make_reloader(tmp, "http://127.0.0.1:1/health")
    order = []
    orig_prepare, orig_restart = qr.prepare_restart, WatchFilesReload.restart

    def _prep(base, url, key, **kw):
        order.append("rite")
        rg.raise_gate(base, key, phase="written")
        return {"outcome": "observed", "live": [], "waited_s": 0, "gate": True}
    try:
        qr.prepare_restart = _prep
        WatchFilesReload.restart = lambda self: order.append("parent_restart")
        obj = object.__new__(cls)          # 감시자·소켓 없이 restart 만 — 순서를 본다
        obj.restart()
    finally:
        qr.prepare_restart, WatchFilesReload.restart = orig_prepare, orig_restart
    assert order == ["rite", "parent_restart"], order
    assert (rg.read_gate(tmp) or {}).get("phase") == "written"


def test_Q5_api_main_installs_before_uvicorn_run():
    src = (REPO / "backend" / "api.py").read_text(encoding="utf-8")
    main_src = src.split('if __name__ == "__main__":', 1)[1]
    assert "quiescent_reload" in main_src, "api.py __main__ 이 리로더를 설치하지 않는다"
    assert main_src.index("_install_quiescent_reload(") < main_src.index("uvicorn.run("), \
        "install 이 uvicorn.run 뒤에 있으면 이미 옛 리로더가 골라졌다"
    # 가드 test_reload_scope 가 읽는 uvicorn.run(...) 호출은 그대로 있어야 한다
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run" and isinstance(n.func.value, ast.Name) and n.func.value.id == "uvicorn"]
    assert len(calls) == 1


def test_Q6_boot_recovers_written_gate():
    tmp = tempfile.mkdtemp(prefix="qr_b_")
    qr.prepare_restart(tmp, "http://x", "boot1", probe=_seq([(True, [])]),
                       cap_s=5, poll_s=0.01, settle_s=0)
    assert (rg.read_gate(tmp) or {}).get("phase") == "written"
    assert rg.clear_at_boot(tmp) is True and rg.read_gate(tmp) is None
    # EpisodeLogger.install 이 실제로 그 회수를 부르는가 (배선)
    el = (REPO / "backend" / "base" / "episode_logger.py").read_text(encoding="utf-8")
    inst = el.split("def install(cls):", 1)[1].split("@classmethod", 1)[0]
    assert "clear_at_boot" in inst


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_Q7_cap_closes_the_turns_it_will_cut(tmp_path):
    """상한 강행(cap)은 도는 턴을 죽인다 — 죽기 전에 리로더가 그 행을 CUT 표식으로 닫는다(2026-09-06 ep2891).
    옛 판은 로그에 이름만 남겼고, 그 행은 부팅 회수도 건너뛰어(궤적 신선) red_apply 가 900초 기다렸다."""
    import sqlite3
    import episode_logger as EL
    base = tmp_path
    (base / "data").mkdir()
    db = qr.ledger_path(str(base))
    orig = EL._get_db

    def _get_db():
        conn = sqlite3.connect(db, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    EL._get_db = _get_db
    try:
        EL._ensure_episode_tables()
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO episode_log (started_at, agent, user_message, log, owner) "
                     "VALUES ('2026-09-06T05:15:10', 'a', 'm', '', '1:1')")
        conn.execute("INSERT INTO episode_log (started_at, ended_at, agent, user_message, log, owner) "
                     "VALUES ('2026-09-06T05:00:00', '2026-09-06T05:01:00', 'a', 'm', 'ok', '1:1')")
        conn.commit(); conn.close()
        q = qr.prepare_restart(str(base), "http://x", "r7", probe=lambda: (True, [1, 2]),
                               cap_s=0.05, poll_s=0.01, settle_s=0)
        assert q["outcome"] == "cap" and q.get("cut") == 1
        conn = sqlite3.connect(db)
        r1 = conn.execute("SELECT ended_at, log FROM episode_log WHERE id=1").fetchone()
        r2 = conn.execute("SELECT ended_at, log FROM episode_log WHERE id=2").fetchone()
        conn.close()
        assert r1[0] and EL.CUT_MARK in r1[1] and "r7" in r1[1]
        assert r2 == ("2026-09-06T05:01:00", "ok")          # 이미 닫힌 행은 그대로
        # observed 는 닫을 것이 없다
        q2 = qr.prepare_restart(str(base), "http://x", "r8", probe=lambda: (True, []),
                                cap_s=1, poll_s=0.01, settle_s=0)
        assert q2["outcome"] == "observed" and "cut" not in q2
    finally:
        EL._get_db = orig
        rg.lower_gate(str(base), "r7"); rg.lower_gate(str(base), "r8")
