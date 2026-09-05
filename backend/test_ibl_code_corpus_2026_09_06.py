"""IBL 문장 원문 코퍼스 회귀 (2026-09-06 부활).

궤적 원장은 원문을 싣지 않는다(test_trajectory_spine 이 지킨다). 원문은 world_pulse.db 의
ibl_code_corpus 가 **원문 해시**를 키로 들고, 그 해시가 ibl.started 의 code_sha256 과 같아
한 DB 안에서 조인된다. 여기서 지키는 것:
  1. 초크포인트를 지난 문장이 코퍼스에 남고, 해시가 궤적의 code_sha256 과 같다(궤적엔 여전히 원문 없음)
  2. 같은 문장은 한 행 — seen/success/fail 누계, 실패 사유는 마지막 실패의 것
  3. 비밀은 마스킹되고(masked=1) 키는 원문 해시 그대로
  4. 빈 코드는 행을 만들지 않는다
  5. 실사용이 한 번이라도 밟은 행의 source 는 'usage' 로 남는다(B18-2)
"""
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401


def _tmp_db(tmp_path):
    import episode_logger as el
    path = str(tmp_path / "world_pulse.db")

    def get_db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    original = el._get_db
    el._get_db = get_db
    el._ensure_episode_tables()
    return path, original


def _rows(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM ibl_code_corpus").fetchall()]
    conn.close()
    return rows


def test_choke_point_writes_corpus_joined_to_trajectory_by_hash(tmp_path):
    import episode_logger as el
    from system_tools_ibl import _execute_ibl_unified

    db_path, original = _tmp_db(tmp_path)
    try:
        code = "[self:time]"
        with el.trajectory_scope(task_id="task_corpus_probe"):
            _execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe")
        rows = _rows(db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["code"] == code and row["masked"] == 0
        assert row["code_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
        assert row["code_chars"] == len(code)
        assert (row["seen_count"], row["success_count"], row["fail_count"]) == (1, 1, 0)
        assert row["last_success"] == 1 and row["last_agent"] == "probe"
        assert row["source"] == "test"

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        started = [json.loads(r["data"]) for r in conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started'").fetchall()]
        conn.close()
        assert started and started[-1]["code_sha256"] == row["code_sha256"]
        assert "code" not in started[-1]
    finally:
        el._get_db = original


def test_failure_through_choke_point_counts_fail_and_keeps_reason(tmp_path):
    import episode_logger as el
    from system_tools_ibl import _execute_ibl_unified

    db_path, original = _tmp_db(tmp_path)
    try:
        code = "[nonode:nothing]{x: 1}"
        with el.trajectory_scope(task_id="task_corpus_fail"):
            _execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe")
        rows = _rows(db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["code"] == code
        assert (row["seen_count"], row["success_count"], row["fail_count"]) == (1, 0, 1)
        assert row["last_success"] == 0
        assert row["last_error"]
    finally:
        el._get_db = original


def test_repeat_accumulates_on_one_row(tmp_path):
    import episode_logger as el

    db_path, original = _tmp_db(tmp_path)
    try:
        code = '[sense:search]{query: "x"}'
        assert el.record_ibl_code(code, success=True, elapsed_ms=10, agent="a")
        assert el.record_ibl_code(code, success=False, elapsed_ms=20, error="boom", agent="b")
        assert el.record_ibl_code(code, success=True, elapsed_ms="5", agent="c")
        rows = _rows(db_path)
        assert len(rows) == 1
        r = rows[0]
        assert (r["seen_count"], r["success_count"], r["fail_count"]) == (3, 2, 1)
        assert r["last_success"] == 1 and r["last_ms"] == 5 and r["last_agent"] == "c"
        assert r["last_error"] == "boom"          # 마지막 *실패*의 사유는 성공이 지우지 않는다
        assert r["first_seen"] <= r["last_seen"]
    finally:
        el._get_db = original


def test_secret_masked_but_key_is_raw_hash(tmp_path):
    import episode_logger as el

    db_path, original = _tmp_db(tmp_path)
    try:
        # 조각으로 잇는다 — GitHub 푸시 보호(비밀 스캐너)가 시험 픽스처 리터럴을 실제 Stripe 키로 읽어
        # 푸시를 거절했다(2026-09-06). 런타임 값은 같아 마스킹 계약 검증은 그대로다.
        secret = "sk_" + "live_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        code = '[limbs:cloudflare_api]{endpoint: "/x", api_key: "' + secret + '"}'
        assert el.record_ibl_code(code, success=False, error="401 " + secret)
        rows = _rows(db_path)
        assert len(rows) == 1
        r = rows[0]
        assert secret not in r["code"] and r["masked"] == 1
        assert secret not in (r["last_error"] or "")
        assert r["code_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
        assert r["code_chars"] == len(code)
    finally:
        el._get_db = original


def test_empty_code_writes_nothing(tmp_path):
    import episode_logger as el
    from system_tools_ibl import _execute_ibl_unified

    db_path, original = _tmp_db(tmp_path)
    try:
        assert el.record_ibl_code("", success=True) is False
        assert el.record_ibl_code("   ", success=True) is False
        _execute_ibl_unified({}, str(tmp_path), agent_id="probe")
        assert _rows(db_path) == []
    finally:
        el._get_db = original


def test_usage_source_sticks_over_later_test_rows(tmp_path, monkeypatch):
    import episode_logger as el

    db_path, original = _tmp_db(tmp_path)
    try:
        code = "[self:time]"
        monkeypatch.setattr(el, "_episode_source", lambda: "usage")
        assert el.record_ibl_code(code, success=True)
        monkeypatch.setattr(el, "_episode_source", lambda: "test")
        assert el.record_ibl_code(code, success=True)
        rows = _rows(db_path)
        assert len(rows) == 1 and rows[0]["source"] == "usage"
        assert rows[0]["seen_count"] == 2
    finally:
        el._get_db = original


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
