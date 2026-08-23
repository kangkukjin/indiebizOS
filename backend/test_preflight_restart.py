"""재기동 선행 점검 — 도는 턴을 모르고 죽이지 않는다 (2026-08-23)

2026-08-23 하루에 라이브 턴이 두 번 끊겼다. 원인이 다르다:
  ① `backend/test_*.py` 신규 생성 → WatchFiles 리로드 → 30회차 턴 절단.
     서버가 막을 수 있는 부류라 `api.py` 의 `reload_excludes` 로 봉했다(test_reload_scope).
  ② **해마 모델 교체 절차 자체** — 재색인 후 백엔드를 명시적으로 kill/재기동해야 하는데
     그 절차에 "지금 도는 턴이 있나"를 묻는 단계가 없었다(episode 1673 절단·좌초).
②는 죽이는 쪽이 사람이라 서버가 못 막는다. 방어는 **죽이기 전에 묻는 단계**로 선다.

★결말이 죽는 자리에 따라 갈린다(둘 다 실측): apply 를 예약한 뒤 죽으면 죽음을 넘는
수행자가 완주시키지만, 예약 전에 죽으면 격리 사본에 **좌초**한다. 그리고 좌초한 *task*
세션을 되살릴 동사가 없다 — apply 는 RED 그랜트 + 현재 세션 키로만 동작한다.

실행: .venv/bin/python -m pytest backend/test_preflight_restart.py
"""
import importlib.util
import json
import os
import sqlite3
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "preflight_restart.py")


@pytest.fixture(scope="module")
def pf():
    if not os.path.exists(_SCRIPT):
        pytest.fail("scripts/preflight_restart.py 가 없다 — 선행 점검이 사라졌다")
    spec = importlib.util.spec_from_file_location("_preflight", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_preflight"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_pulse(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE episode_log (id INTEGER PRIMARY KEY, started_at TEXT, "
                 "ended_at TEXT, agent TEXT, user_message TEXT)")
    conn.executemany("INSERT INTO episode_log VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_P1_도는_턴이_있으면_막는다(pf, tmp_path, monkeypatch):
    db = tmp_path / "world_pulse.db"
    _make_pulse(db, [(1, "10:40", None, "system_ai", "#repair 뭔가 고쳐")])
    monkeypatch.setattr(pf, "PULSE_DB", db)
    monkeypatch.setattr(pf, "SESSIONS", tmp_path / "none")
    assert pf.check(verbose=False) == 1


def test_P2_끝난_턴만_있으면_통과(pf, tmp_path, monkeypatch):
    db = tmp_path / "world_pulse.db"
    _make_pulse(db, [(1, "10:40", "10:48", "system_ai", "끝난 턴")])
    monkeypatch.setattr(pf, "PULSE_DB", db)
    monkeypatch.setattr(pf, "SESSIONS", tmp_path / "none")
    assert pf.check(verbose=False) == 0


def test_P3_예약_전_스테이징이_있으면_막는다(pf, tmp_path, monkeypatch):
    """이게 좌초가 생기는 정확한 자리 — apply 예약 전에 죽으면 되살릴 동사가 없다."""
    db = tmp_path / "world_pulse.db"
    _make_pulse(db, [(1, "10:40", "10:48", "system_ai", "끝난 턴")])
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "task_x.json").write_text(json.dumps(
        {"status": "staging", "files": {"/a/backend/x.py": {}}}), encoding="utf-8")
    monkeypatch.setattr(pf, "PULSE_DB", db)
    monkeypatch.setattr(pf, "SESSIONS", sess)
    assert pf.check(verbose=False) == 1


def test_P4_이미_적용된_세션은_안_막는다(pf, tmp_path, monkeypatch):
    db = tmp_path / "world_pulse.db"
    _make_pulse(db, [(1, "10:40", "10:48", "system_ai", "끝")])
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "task_x.json").write_text(json.dumps(
        {"status": "applied", "files": {"/a/backend/x.py": {}}}), encoding="utf-8")
    # 예약까지 간 세션도 안 막는다 — 죽음을 넘는 수행자가 완주시킨다(실측)
    (sess / "task_y.json").write_text(json.dumps(
        {"status": "apply_scheduled", "files": {"/a/backend/y.py": {}}}), encoding="utf-8")
    monkeypatch.setattr(pf, "PULSE_DB", db)
    monkeypatch.setattr(pf, "SESSIONS", sess)
    assert pf.check(verbose=False) == 0


def test_P5_판정_불능은_통과가_아니다(pf, tmp_path, monkeypatch):
    """★'못 봤다'와 '없다'는 다른 사건이다(B28-1). 원장을 못 읽으면 2 — 0 으로 뭉개지 않는다."""
    monkeypatch.setattr(pf, "PULSE_DB", tmp_path / "없는파일.db")
    monkeypatch.setattr(pf, "SESSIONS", tmp_path / "none")
    assert pf.check(verbose=False) == 2


def test_P6_apply_세션_파일은_스테이징으로_안_센다(pf, tmp_path, monkeypatch):
    """`*.apply.json` 은 수행자의 작업 기록이지 스테이징이 아니다."""
    db = tmp_path / "world_pulse.db"
    _make_pulse(db, [(1, "10:40", "10:48", "system_ai", "끝")])
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "task_x.apply.json").write_text(json.dumps(
        {"status": "staging", "files": {"/a/backend/x.py": {}}}), encoding="utf-8")
    monkeypatch.setattr(pf, "PULSE_DB", db)
    monkeypatch.setattr(pf, "SESSIONS", sess)
    assert pf.check(verbose=False) == 0


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차).
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
