"""관용구 반환 관측(2026-09-26): 실행이 돌려준 필드 → 정의 행 병합 → 회상 줄·병기 줄·describe 의 `→ Record⟨관측: …⟩`.

4018 실측: 회상 줄이 `[fn:AI팁보고서쓰기]{} → Record` 만 말해 모델이 describe 를 한 번 더 불렀다. 그 호출을 없애는 기계.
정본: docs/IBL_INCREMENTAL_EXECUTION_2026_09_26.md §5
"""
import json
import sqlite3
import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, returned_shape
from ibl_returns_observed import merge_observed_returns, returns_display


def test_function_result_event_carries_returned_shape_not_value():
    out = Runtime(compile_program("[def:f](){return {a:1, b:{c:2}}}\nreturn [fn:f]{}")).run()
    ev = next(e for e in out["evidence"] if e["kind"] == "function_result")
    assert ev["success"] and ev["returns_kind"] == "record" and ev["returns_keys"] == ["a", "b"]
    assert "value" not in ev and "returns_value" not in ev  # 값이 아니라 모양만
    rows = Runtime(compile_program("[def:g](){return [{x:1},{x:2}]}\nreturn [fn:g]{}")).run()
    ev = next(e for e in rows["evidence"] if e["kind"] == "function_result")
    assert ev["returns_kind"] == "list" and ev["returns_keys"] == ["x"]
    scalar = Runtime(compile_program("[def:h](){return 3}\nreturn [fn:h]{}")).run()
    ev = next(e for e in scalar["evidence"] if e["kind"] == "function_result")
    assert "returns_keys" not in ev
    assert returned_shape([]) == {} and returned_shape(None) == {}


def test_merge_keeps_first_seen_order_counts_runs_and_caps():
    first = merge_observed_returns("", ["status", "report"], "record", "run")
    second = merge_observed_returns(first, ["report", "shared_report", "status"], "record", "run")
    obs = json.loads(second)
    assert obs["keys"] == ["status", "report", "shared_report"] and obs["runs"] == 2 and obs["kind"] == "record"
    assert obs["observed"] and obs["source"] == "run" and obs["more"] == 0
    big = json.loads(merge_observed_returns("", [f"k{i}" for i in range(45)]))
    assert len(big["keys"]) == 40 and big["more"] == 5
    assert json.loads(merge_observed_returns("not json", ["a"]))["keys"] == ["a"]


def test_returns_display_appends_observation_but_never_overrides_declared_fields():
    obs = json.dumps({"kind": "record", "keys": ["status", "report", "shared_report"]})
    assert returns_display("Record", obs) == "Record⟨관측: status·report·shared_report⟩"
    assert returns_display("", obs) == "Record⟨관측: status·report·shared_report⟩"
    assert returns_display("{status: Text}", obs) == "{status: Text}"      # 선언이 필드를 말하면 그대로
    assert returns_display("items⟨title·url⟩", obs) == "items⟨title·url⟩"
    assert returns_display("Record", "") == "Record" and returns_display("prose", "{}") == "prose"
    many = json.dumps({"kind": "record", "keys": [f"k{i}" for i in range(20)]})
    assert returns_display("Record", many).endswith("k15…⟩")
    rows = json.dumps({"kind": "list", "keys": ["x", "y"]})
    assert returns_display("", rows) == "List<Record⟨관측: x·y⟩>"


def test_record_functions_feeds_observed_returns_only_on_success():
    from function_library import register, definitions
    from capability_history import function_statistics
    from ibl_v2_learning import record_functions
    ref = register('보고', '#!ibl edition=2\n[def:보고](){return {status:"completed",report:"p"}}')
    plan = compile_program('[fn:보고]{}', definitions=definitions())
    out = Runtime(plan).run()
    out['resume'] = {'run_id': 'observed-return-test'}
    record_functions(plan, out)
    record_functions(plan, out)  # 재수집은 같은 호출의 실적을 늘리지 않는다.
    stats = function_statistics(ref)
    assert stats['success_count'] == 1
    assert json.loads(stats['returns_observed'])['keys'] == ['status', 'report']
    assert 'completed' not in stats['returns_observed']


def test_idiom_rows_carry_observation_in_returns_column(tmp_path):
    from ibl_access import _current_idiom_rows
    conn = sqlite3.connect(tmp_path / "u.db")
    conn.execute("CREATE TABLE ibl_examples(intent TEXT, ibl_code TEXT, success_count INT, fail_count INT, topic TEXT, alias TEXT, "
                 "returns TEXT, signature TEXT, returns_observed TEXT, updated_at TEXT, always_on INT)")
    code = "#!ibl edition=2\n[def:보고]($설정={}){return {a:1}}"
    obs = json.dumps({"kind": "record", "keys": ["status", "report"]})
    conn.execute("INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 ("보고서를 쓴다", code, 1, 0, "", "보고", "Record", "설정", obs, "2026-09-26", 1))
    conn.execute("INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 ("옛 정의", "[self:time]", 1, 0, "", "옛것", "prose", "", "", "2026-09-01", 1))
    from test_function_support import import_memory
    from function_store import resolve, reference
    from capability_history import record_function_call
    import_memory(conn)
    record_function_call(reference(resolve('보고')), 'observation-fixture', 'call', success=True,
                         dependency_revision='fixture', source_complete=True,
                         observed={'kind':'record', 'keys':['status','report']})
    rows = conn.execute("SELECT intent,ibl_code,success_count,fail_count,COALESCE(topic,''),alias,COALESCE(returns,''),signature "
                        "FROM ibl_examples").fetchall()
    out = _current_idiom_rows(conn, rows, "COALESCE(returns,'')", "signature")
    by = {r[5]: r for r in out}
    assert len(by["보고"]) == 8 and by["보고"][6] == "Record⟨관측: status·report⟩"
    assert "옛것" not in by  # 구판은 역사로 보존하며 현재 호출 교재에서 제외한다.


def test_call_line_shows_observation_to_the_model():
    from hippo_tree import phrase_call_line
    line = phrase_call_line("보고", "#!ibl edition=2\n[def:보고]($설정={}){return {a:1}}", "Record⟨관측: status·report⟩", "설정")
    assert line.endswith("→ Record⟨관측: status·report⟩") and "[fn:보고]{" in line


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
