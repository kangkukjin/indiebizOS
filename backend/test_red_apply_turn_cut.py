"""wait_turn_closed 의 출처 교차 — 원장(ended_at) × 몸(/health live_turns) (2026-09-06 ep2891)

실측: 리로드가 정적 대기 상한에 닿아 턴 2891 을 남긴 채 강행 → 그 턴은 END 를 못 씀 → 행이 NULL 로
남음 → 수행자는 원장만 보며 900초(05:19:42→05:34:44)를 기다렸다. 그 사이 몸은 05:20 부터 살아서
"도는 턴 없음"을 답할 수 있었다. 원장이 열린 채 몸이 '그 턴 없다'고 답하면 잘린 턴("cut")이다.

  C1  몸이 "그 턴 안 돈다" + 원장 NULL 이 유예를 넘김 → "cut" (상한을 기다리지 않는다)
  C2  몸이 그 턴을 아직 신고 → 원장이 닫힐 때까지 기다림 → "observed"
  C3  몸이 안 닿음(재기동 중) / 옛 몸(live_turns 없음) → 원장만 → 상한 → "cap" (못 봤다≠없다)
  C4  몸이 '없다'고 답했다가 유예 안에 원장이 닫힘 → "observed" (막 닫히는 중인 턴을 자르지 않는다)

실행: .venv/bin/python -m pytest backend/test_red_apply_turn_cut.py -q
"""
import os
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import boot_paths  # noqa: E402,F401

import red_apply as _ra  # noqa: E402


def _repo(tmp_path, eid=2891, ended=None):
    (tmp_path / "data").mkdir()
    db = str(tmp_path / "data" / "world_pulse.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE episode_log (id INTEGER PRIMARY KEY, started_at TEXT, ended_at TEXT, "
                 "agent TEXT, user_message TEXT, log TEXT, total_ms INTEGER, task_id TEXT, source TEXT, owner TEXT)")
    conn.execute("INSERT INTO episode_log (id, started_at, ended_at, log) VALUES (?, '2026-09-06T05:15:10', ?, '')",
                 (eid, ended))
    conn.commit(); conn.close()
    return str(tmp_path), db


def _close(db, eid):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE episode_log SET ended_at = '2026-09-06T05:20:00', log = 'done' WHERE id = ?", (eid,))
    conn.commit(); conn.close()


class _Fast:
    """상한·유예를 짧게, 프로브를 시퀀스로."""
    def __init__(self, probe, cap=1.5, gone=0.3):
        self.probe, self.cap, self.gone = probe, cap, gone

    def __enter__(self):
        self.saved = (_ra._probe_live_turns, _ra.TURN_CLOSE_CAP_S, _ra.BODY_GONE_CONFIRM_S,
                      _ra.DISTILL_GRACE_S, _ra.SETTLE_S, _ra.time.sleep)
        _ra._probe_live_turns = self.probe
        _ra.TURN_CLOSE_CAP_S, _ra.BODY_GONE_CONFIRM_S = self.cap, self.gone
        _ra.DISTILL_GRACE_S, _ra.SETTLE_S = 0, 0
        _ra.time.sleep = lambda s: self.saved[5](min(s, 0.02))
        return self

    def __exit__(self, *a):
        (_ra._probe_live_turns, _ra.TURN_CLOSE_CAP_S, _ra.BODY_GONE_CONFIRM_S,
         _ra.DISTILL_GRACE_S, _ra.SETTLE_S, _ra.time.sleep) = self.saved


def test_c1_body_says_gone_ledger_open_is_cut(tmp_path):
    repo, _ = _repo(tmp_path)
    import time
    t = time.time()
    with _Fast(lambda url=None: (True, [])):
        assert _ra.wait_turn_closed(repo, 2891) == "cut"
    assert time.time() - t < 1.4, "상한까지 기다렸다 — 교차가 안 붙었다"


def test_c2_body_still_reports_turn_waits_for_ledger(tmp_path):
    repo, db = _repo(tmp_path)
    calls = {"n": 0}

    def probe(url=None):
        calls["n"] += 1
        if calls["n"] == 3:
            _close(db, 2891)          # 세 번째 물음 뒤 턴이 스스로 닫힌다
        return (True, [2891])
    with _Fast(probe):
        assert _ra.wait_turn_closed(repo, 2891) == "observed"


def test_c3_unreachable_or_legacy_body_falls_back_to_ledger_cap(tmp_path):
    repo, _ = _repo(tmp_path)
    with _Fast(lambda url=None: (False, None), cap=0.3):
        assert _ra.wait_turn_closed(repo, 2891) == "cap"
    with _Fast(lambda url=None: (True, None), cap=0.3):
        assert _ra.wait_turn_closed(repo, 2891) == "cap"


def test_c4_gone_then_ledger_closes_inside_grace_is_observed(tmp_path):
    repo, db = _repo(tmp_path)
    calls = {"n": 0}

    def probe(url=None):
        calls["n"] += 1
        if calls["n"] == 2:
            _close(db, 2891)
        return (True, [])
    with _Fast(probe, gone=5):
        assert _ra.wait_turn_closed(repo, 2891) == "observed"


def test_c5_source_has_cross_check_and_cut_is_reported():
    """배선 가드 — 교차 분기와 결말 보고가 코드에 실존한다."""
    import inspect
    src = inspect.getsource(_ra.wait_turn_closed)
    assert "_probe_live_turns()" in src and '"cut"' in src
    import red_report
    assert '"cut"' in inspect.getsource(red_report)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
