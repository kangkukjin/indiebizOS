"""weekly_audits 관문 — 주간 감사 넷의 공통 정형 (2026-09-07 신설).

★한 감사의 실패가 나머지를 삼키면 유지보수는 조용히 반만 돈다 — 그 격리를 시험한다.
"""
import boot_paths  # noqa: F401
import weekly_audits as WA
import json
from datetime import datetime, timedelta
import pytest


def test_감사_넷이_전부_배선돼_있다():
    keys = [k for k, _, _ in WA.AUDITS]
    assert keys == ["data_ownership", "doc_drift", "store_waste", "vocab_overlap"], keys
    for _, module, func in WA.AUDITS:
        mod = __import__(module, fromlist=[func])
        assert callable(getattr(mod, func)), f"{module}.{func} 없음"


def test_한_감사가_터져도_나머지는_돈다(monkeypatch):
    saved = []
    calls = []

    def fake(key):
        def _run():
            calls.append(key)
            if key == "doc_drift":
                raise RuntimeError("일부러 터뜨림")
            return {"node": "__static__", "action": key, "success": True}
        return _run

    monkeypatch.setattr(WA, "AUDITS", [(k, "weekly_audits", f"_fake_{k}") for k in
                                       ("data_ownership", "doc_drift", "store_waste")])
    for k in ("data_ownership", "doc_drift", "store_waste"):
        monkeypatch.setattr(WA, f"_fake_{k}", fake(k), raising=False)
    r = WA.run_weekly_audits(saved.append)
    assert calls == ["data_ownership", "doc_drift", "store_waste"], calls
    assert r["doc_drift"]["audit_status"] == "failed" and "store_waste" in r, r
    assert not r["doc_drift"]["success"]
    assert [s["action"] for s in saved] == ["data_ownership", "doc_drift", "store_waste"]


def test_카덴스_스킵은_원장에_남기지_않는다(monkeypatch):
    saved = []
    monkeypatch.setattr(WA, "AUDITS", [("store_waste", "weekly_audits", "_fake_skip")])
    monkeypatch.setattr(WA, "_fake_skip", lambda: {"skipped": "cadence"}, raising=False)
    r = WA.run_weekly_audits(saved.append)
    assert r["store_waste"] == {"skipped": "cadence", "audit_status": "skipped"}
    assert saved == [], "안 돈 감사를 원장에 남겼다"


def test_경고_문구는_감사가_소유한다(monkeypatch, caplog):
    monkeypatch.setattr(WA, "AUDITS", [("store_waste", "weekly_audits", "_fake_msg")])
    monkeypatch.setattr(WA, "_fake_msg", lambda: {
        "node": "__static__", "action": "store_waste", "success": False,
        "error_message": "저장소 낭비 2건 / 회수 가능 133.0MB — store_waste_flags.json"}, raising=False)
    with caplog.at_level("WARNING"):
        WA.run_weekly_audits(lambda _: None)
    assert "회수 가능 133.0MB" in caplog.text, caplog.text


@pytest.mark.parametrize("raw,status", [
    ({"success": True, "flags": []}, "clean"),
    ({"success": True, "unchecked": ["missing"]}, "insufficient"),
    ({"skipped": "cadence", "flags": []}, "skipped"),
    ({"error": "failed to read", "flags": []}, "failed"),
    ({"success": False, "flags": ["stale"]}, "findings"),
    ({"flags": []}, "insufficient"),
])
def test_audit_outcomes_do_not_confuse_zero_with_clean(raw, status):
    from audit_lifecycle import normalize_result
    assert normalize_result(raw)["audit_status"] == status


@pytest.mark.parametrize("module_name,function,measure,empty", [
    ("doc_drift", "run_doc_drift_check", "measure", {"flags": [], "unchecked": []}),
    ("store_waste_audit", "run_store_waste_check", "measure",
     {"flags": [], "structural": [], "unchecked": []}),
    ("data_ownership", "run_data_ownership_check", "_walk_flags", {}),
])
def test_report_write_failure_is_not_clean_or_a_completed_cadence(
        tmp_path, monkeypatch, module_name, function, measure, empty):
    import importlib
    from audit_lifecycle import normalize_result, due
    module = importlib.import_module(module_name)
    state = tmp_path / "state.json"
    monkeypatch.setattr(module, "_STATE_PATH", state)
    monkeypatch.setattr(module, "_FLAGS_PATH", tmp_path / "absent" / "flags.json")
    monkeypatch.setattr(module, measure, lambda: empty)
    result = normalize_result(getattr(module, function)(force=True))
    assert result["audit_status"] == "failed"
    assert not result["success"]
    assert not state.exists() and due(state)


def test_cadence_requires_complete_repeated_same_input_and_resets_on_change(tmp_path):
    from audit_lifecycle import next_cadence, due, CADENCE_HOURS, MAX_CADENCE_HOURS
    state = {"fingerprint": "one"}
    for _ in range(3):
        state.update(next_cadence(state, fingerprint="one", clean=True, complete=True))
    assert state["cadence_hours"] == 2 * CADENCE_HOURS
    for _ in range(20):
        state.update(next_cadence(state, fingerprint="one", clean=True, complete=True))
    assert state["cadence_hours"] == MAX_CADENCE_HOURS
    assert next_cadence(state, fingerprint="changed", clean=True, complete=True)["cadence_hours"] == CADENCE_HOURS
    assert next_cadence(state, fingerprint="one", clean=True, complete=False)["clean_streak"] == 0
    assert next_cadence(state, fingerprint="one", clean=False, complete=True)["cadence_hours"] == CADENCE_HOURS
    now = datetime(2026, 9, 11)
    state.update(last_run=(now - timedelta(hours=CADENCE_HOURS + 1)).isoformat(),
                 outcome="clean", coverage="complete")
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    assert not due(path, fingerprint="one", now=now)
    assert due(path, fingerprint="changed", now=now)
    state.update(last_run=now.isoformat(), error="measurement failed")
    path.write_text(json.dumps(state))
    assert due(path, fingerprint="one", now=now)


def test_overlap_finds_cross_action_neighbor_hidden_by_closer_same_action():
    import numpy as np
    from vocab_overlap_audit import _measure_overlaps
    def row(i, action, values):
        return (i, str(i), f"[{action}]{{}}", np.array(values, dtype=np.float32).tobytes())
    # 각 행의 가장 가까운 이웃은 같은 액션이다. 교차 액션들도 0.95 이상이다.
    rows = [row(1, "sense:search", [1, 0]), row(2, "sense:search", [1, 0]),
            row(3, "sense:find", [.99, .1]), row(4, "sense:find", [.99, .1])]
    flags = _measure_overlaps(rows)
    assert len(flags) == 1 and set(flags[0]["actions"]) == {"sense:search", "sense:find"}
    assert flags[0]["count"] == 4
    with pytest.raises(ValueError):
        _measure_overlaps([row(1, "sense:search", [0, 0])])


def test_overlap_cadence_uses_actual_corpus_and_failure_resets_it(tmp_path, monkeypatch):
    import numpy as np
    import vocab_overlap_audit as audit
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(audit, "_STATE_PATH", state_path)
    monkeypatch.setattr(audit, "_FLAGS_PATH", tmp_path / "flags.json")
    rows = [(1, "one", "[sense:search]{}", np.array([1, 0], dtype=np.float32).tobytes()),
            (2, "two", "[sense:find]{}", np.array([0, 1], dtype=np.float32).tobytes())]
    monkeypatch.setattr(audit, "_load_corpus", lambda: rows)
    for _ in range(3):
        assert audit.run_vocab_overlap_check(force=True)["success"]
    state = json.loads(state_path.read_text())
    assert state["clean_streak"] == 3 and state["cadence_hours"] == 336
    assert audit.run_vocab_overlap_check()["skipped"] == "cadence"
    rows[1] = (2, "changed intent", rows[1][2], rows[1][3])
    assert audit.run_vocab_overlap_check()["success"]
    assert json.loads(state_path.read_text())["clean_streak"] == 1
    def broken():
        raise RuntimeError("corpus unavailable")
    monkeypatch.setattr(audit, "_load_corpus", broken)
    failed = audit.run_vocab_overlap_check()
    assert not failed["success"] and failed["error"]
    state = json.loads(state_path.read_text())
    assert state["clean_streak"] == 0 and state["cadence_hours"] == 168


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
