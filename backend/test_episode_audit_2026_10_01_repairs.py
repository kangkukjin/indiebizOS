"""10-01 에피소드 감사(ep4211~4214) 수리의 회귀 시험.

결과 봉투 다이어트·검사 통과분 참조 실행·평가 원장의 실행 증거·첨부 상한·진단 문구·옛 용례 투영."""
import json

import sys

import boot_paths  # noqa: F401
import pytest


# ---------------------------------------------------------------- 결과 봉투
def test_model_usage_keeps_totals_and_drops_node_spans_for_cheap_runs():
    from model_result_view import model_usage
    usage = {"steps": 5, "rows": 0, "elapsed_ms": 290, "limits": {"steps": 100000, "rows": 10000},
             "steps_by_span": [{"node_id": "call:0:9", "steps": 1, "location": {"line": 1}}] * 5,
             "steps_other": 0, "steps_by_line": [{"line": 1, "steps": 5, "source_hash": "a" * 64}]}
    shown = model_usage(usage)
    assert shown == {"steps": 5, "rows": 0, "elapsed_ms": 290}
    assert len(json.dumps(shown)) < 80


def test_model_usage_shows_expensive_lines_when_budget_is_used():
    from model_result_view import model_usage
    lines = [{"line": n, "steps": 9000 - n, "source_hash": "a" * 64} for n in range(1, 8)]
    shown = model_usage({"steps": 30000, "rows": 10, "elapsed_ms": 9000,
                         "limits": {"steps": 100000, "rows": 10000},
                         "steps_by_span": [{}] * 20, "steps_by_line": lines})
    assert [row["line"] for row in shown["steps_by_line"]] == [1, 2, 3]
    assert all("source_hash" not in row for row in shown["steps_by_line"])
    assert "steps_by_span" not in shown and shown["limits"]["steps"] == 100000


def test_twin_fields_are_shown_once_without_naming_vocabulary():
    from model_result_view import _fold_twin_fields
    rows = [{"start": i, "text": "가나다라마바사" * 4} for i in range(30)]
    notes = []
    shown = _fold_twin_fields([{"title": "x"}, {"transcript": "t", "segments": rows, "items": rows}],
                              ["value"], notes)
    assert shown[1]["segments"] == rows
    assert shown[1]["items"] == {"$model_same_as": "segments"}
    assert notes == [{"path": ["value", 1, "items"], "same_as": ["value", 1, "segments"]}]
    # 작은 값·서로 다른 값은 건드리지 않는다.
    assert _fold_twin_fields({"a": [1], "b": [1], "c": rows, "d": rows[:-1]}, [], []) == \
        {"a": [1], "b": [1], "c": rows, "d": rows[:-1]}


def test_read_result_json_is_one_row_per_line_and_round_trips():
    from model_result_view import page_json, _selection_chars
    rows = [{"start": 0.08, "duration": 6.6, "text": "아무래도"}, {"start": 3.24, "duration": 5.72, "text": "없습니다"}]
    text = page_json(rows)
    assert json.loads(text) == rows and text.count("\n") == len(rows) + 1
    assert len(text) < len(json.dumps(rows, ensure_ascii=False, indent=2))
    assert _selection_chars(rows, typed=True) == len(text)
    record = {"a": [1, 2], "b": {"c": "d"}}
    assert json.loads(page_json(record)) == record
    assert page_json([]) == "[]" and page_json({}) == "{}" and page_json(3) == "3"


# ---------------------------------------------------------------- 검사 통과분 참조
class _Store:
    def __init__(self):
        self.rows = {}

    def evidence(self, value):
        import hashlib
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        key = hashlib.sha256(text.encode()).hexdigest()
        self.rows[key] = text
        return {"id": key, "chars": len(text)}

    def read_evidence_across_turns(self, key, offset=0, limit=None):
        if key not in self.rows:
            raise ValueError("증거 없음")
        return {"id": key, "text": self.rows[key], "chars": len(self.rows[key])}


def test_checked_program_runs_by_reference_without_retyping(monkeypatch):
    import model_result_view
    import system_tools_ibl as tools
    store = _Store()
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    code = "$a = 1\nreturn $a + 1"
    checked = {"edition": 2, "mode": "check", "executed": False, "ok": True, "status": "valid"}
    tools._offer_checked_code(checked, code)
    handle = checked["execute_args"]["code"]
    assert handle.startswith("$checked:") and "다시 적지" in checked["next_action"]
    resolved, error = tools._resolve_checked_code({"code": handle, "inputs": {"x": 1}})
    assert error is None and resolved == {"code": code, "inputs": {"x": 1}}


def test_checked_reference_refuses_other_evidence_and_failed_checks(monkeypatch):
    import model_result_view
    import system_tools_ibl as tools
    store = _Store()
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    failed = {"edition": 2, "mode": "check", "executed": False, "ok": False, "status": "invalid"}
    tools._offer_checked_code(failed, "return $없는값")
    assert "execute_args" not in failed
    other = store.evidence(json.dumps({"success": True, "value": "크롤 결과"}, ensure_ascii=False))
    _, error = tools._resolve_checked_code({"code": f"$checked:{other['id']}"})
    assert error and "검사를 통과한 프로그램이 아닙니다" in error
    _, error = tools._resolve_checked_code({"code": "$checked:" + "0" * 64})
    assert error and "다시 보내세요" in error
    # 참조가 아닌 보통 코드는 그대로 지나간다.
    plain = {"code": "return 1"}
    assert tools._resolve_checked_code(plain) == (plain, None)


# ---------------------------------------------------------------- 평가 원장
def test_ledger_uses_runtime_targets_for_computed_paths():
    from cognitive_trace import build_action_ledger
    calls = [{"name": "mcp__indiebizos__execute_ibl",
              "input": {"code": '$r=[self:read]{path:$out+"/report.md"} & [self:read]{path:$out+"/anomalies.json"}'},
              "result": "{}", "runtime_calls": [
                  {"action": "self:read", "targets": {"path": "/out/before_ledger/report.md"}},
                  {"action": "self:read", "targets": {"path": "/out/before_ledger/anomalies.json"}}]}]
    ledger = build_action_ledger(calls)
    assert "self:read (×2)" in ledger
    assert "/out/before_ledger/report.md" in ledger and "/out/before_ledger/anomalies.json" in ledger


def test_ledger_does_not_count_check_only_calls_as_executed_actions():
    from cognitive_trace import build_action_ledger
    code = '[self:write]{path:"/out/a.md",content:"x"}'
    ledger = build_action_ledger([
        {"name": "execute_ibl", "input": {"code": code, "check": True}, "result": "{}"},
        {"name": "execute_ibl", "input": {"code": code}, "result": "{}", "runtime_calls": []},
        {"name": "execute_ibl", "input": {"code": code}, "result": "{}",
         "runtime_calls": [{"action": "self:write", "targets": {"path": "/out/a.md"}}]}])
    assert "self:write (×1)" in ledger and "(×2)" in ledger.split("self:write")[0]


def test_ledger_keeps_last_targets_when_many():
    from cognitive_trace import build_action_ledger
    runtime = [{"action": "self:read", "targets": {"path": f"/in/tx_{n:02d}.csv"}} for n in range(1, 21)]
    runtime.append({"action": "self:read", "targets": {"path": "/out/report.md"}})
    ledger = build_action_ledger([{"name": "execute_ibl", "input": {"code": "x"}, "result": "{}",
                                   "runtime_calls": runtime}])
    assert "/in/tx_01.csv" in ledger and "/out/report.md" in ledger and "가운데 9개 생략" in ledger


def test_ledger_falls_back_to_code_text_without_runtime_evidence():
    from cognitive_trace import build_action_ledger
    ledger = build_action_ledger([{"name": "execute_ibl", "result": "{}",
                                   "input": {"code": '[self:read]{path: "/in/a.csv"}'}}])
    assert "self:read (×1)" in ledger and "/in/a.csv" in ledger


def test_runtime_calls_reads_invoke_events_from_stored_evidence():
    from final_evaluator import runtime_calls

    class Store:
        def read_evidence(self, key, offset, limit):
            return {"text": json.dumps({"evidence": [
                {"kind": "literal"},
                {"kind": "invoke", "action": "self:read", "targets": {"path": "/out/report.md"}},
                {"kind": "invoke", "action": "table:filter"}]})}

    shown = json.dumps({"edition": 2, "executed": True, "result_ref": {"id": "a" * 64}})
    assert runtime_calls(Store(), shown) == [
        {"action": "self:read", "targets": {"path": "/out/report.md"}},
        {"action": "table:filter", "targets": {}}]
    assert runtime_calls(Store(), json.dumps({"edition": 2, "executed": False})) == []
    assert runtime_calls(Store(), json.dumps({"success": True})) is None
    assert runtime_calls(Store(), "평문") is None


def test_runtime_records_short_text_arguments_of_external_calls(tmp_path):
    from ibl_v2_entry import handle_request
    target = tmp_path / "note.md"
    code = '$out = $dir\n[self:write]{path:$out+"/note.md",content:$body}\nreturn [self:read]{path:$out+"/note.md"}'
    result = handle_request({"code": code, "edition": 2,
                             "inputs": {"dir": str(tmp_path), "body": "본문 " * 200}},
                            str(tmp_path), "audit_test")
    assert result["success"], result.get("error")
    invokes = [e for e in result["evidence"] if e.get("kind") == "invoke"]
    by_action = {e["action"]: e.get("targets") for e in invokes}
    assert by_action["self:read"] == {"path": str(target)}
    # 긴 본문은 대상이 아니다.
    assert by_action["self:write"] == {"path": str(target)}


# ---------------------------------------------------------------- 평가 첨부
def test_large_json_attachment_is_bounded_with_harness_outline():
    from cognitive_eval import bounded_attachment, EVALUATION_FILE_CHARS
    data = {"totals": {"issues": 930}, "transactions": [{"id": n, "merchant": "가게" * 20} for n in range(5000)]}
    content = json.dumps(data, ensure_ascii=False)
    shown = bounded_attachment("/out/anomalies.json", content)
    assert len(shown) < EVALUATION_FILE_CHARS + 2000 < len(content)
    assert "JSON 파싱 성공" in shown and "transactions: list(5000행" in shown and "totals: {issues: int}" in shown
    assert "부재를 단정하지 말 것" in shown
    small = '{"a": 1}'
    assert bounded_attachment("/out/a.json", small) == small
    assert "JSON 파싱 실패" in bounded_attachment("/out/b.json", "{" + "x" * 70000)


# ---------------------------------------------------------------- 진단 문구
def test_partial_source_message_prefers_the_warning_over_file_body():
    from ibl_v2_adapters import _partial_message
    raw = {"message": '{"records": {"orders": [' + "1," * 3000, "truncated": True,
           "warning": "처음 1MB만 표시했습니다. offset/limit으로 부분 읽기를 사용하세요."}
    message = _partial_message(raw, {"truncations": [{"scope": "unknown"}]})
    assert "처음 1MB만 표시했습니다" in message and '"records"' not in message
    bare = _partial_message({"message": "본문 " * 500}, {"truncations": [{"scope": "unknown"}]})
    assert "절단 사유를 밝히지 않았습니다" in bare and "본문 본문" not in bare


def _run(tmp_path, code):
    from ibl_v2_entry import handle_request
    return handle_request({"code": code, "edition": 2}, str(tmp_path), "audit_test")


@pytest.mark.parametrize("code, expected", [
    ("return json({a: 54/934*100})", '{"a": 5.781584582441114}'),          # 이전: 정밀도 오류
    ("return json({a: 50/976*100})", '{"a": 5.122950819672131}'),          # 이전에도 통과 — 값에 따라 갈렸다
    ("return json({a: (54/934)+(50/976)})", '{"a": 0.10904535402113244}'),
    ("return json({a: sum([1/3, 1/3, 1/3])})", '{"a": 1.0}'),
    ("return json({a: 12.345*100/7})", '{"a": 176.35714285714286}'),
])
def test_quotients_are_floats_and_always_cross_the_json_boundary(tmp_path, code, expected):
    out = _run(tmp_path, code)
    assert out["success"], out.get("error")
    assert out["value"] == expected


def test_group_sums_divided_then_scaled_no_longer_fail_by_value(tmp_path):
    code = ('$t = [{k:"a", n:54, d:934}, {k:"b", n:50, d:976}] >> '
            '[table:groupby]{by:"k", agg:{n:["sum","n"], d:["sum","d"]}}\n'
            'return json(map($t.items, ($r)=>{rate: $r.n / $r.d * 100}))')
    out = _run(tmp_path, code)
    assert out["success"], out.get("error")
    assert json.loads(out["value"]) == [{"rate": 5.781584582441114}, {"rate": 5.122950819672131}]


@pytest.mark.parametrize("code, wire", [
    ("return 0.1+0.2", ["decimal", "0.3"]),            # 적힌 소수는 십진 계산 그대로
    ("return 19.9*3", ["decimal", "59.7"]),
    ("return 0.3/0.1", ["decimal", "3"]),              # 정확히 떨어지는 몫은 십진수
    ("return round(2.675, 2)", ["decimal", "2.68"]),
    ("return 1/4", ["scalar", 0.25]),
    ("return 1/3", ["scalar", 0.3333333333333333]),
    ("return 1.1/3", ["scalar", 0.36666666666666664]),  # 떨어지지 않는 십진 몫 = 근사 실수
    ("return round(54/934*100, 2)", ["scalar", 5.78]),
])
def test_written_decimals_stay_exact_and_only_inexact_results_become_floats(tmp_path, code, wire):
    out = _run(tmp_path, code)
    assert out["success"], out.get("error")
    assert out["value_wire"]["data"] == wire


def test_long_exact_decimal_still_refuses_json_number_with_a_round_hint(tmp_path):
    failed = _run(tmp_path, "return json({a: 123456789.123456789*2})")
    assert failed["success"] is False and failed["diagnostic"]["code"] == "NON_JSON_RESULT"
    assert "round(" in failed["diagnostic"]["hint"]
    assert _run(tmp_path, "return json({a: round(123456789.123456789*2, 3)})")["success"]


def test_negative_base_fractional_power_is_an_error_not_a_complex_number(tmp_path):
    out = _run(tmp_path, "return (0-8)**(1/3)")
    assert out["success"] is False and out["diagnostic"]["code"] == "NUMBER_REQUIRED"


def test_declared_mirror_rows_are_folded_in_the_model_copy():
    from model_result_view import _fold_twin_fields
    page = {"url": "https://example.com", "text": "본문 " * 40,
            "items": [{"type": "paragraph", "text": "본문", "url": "https://example.com", "paragraph_index": i}
                      for i in range(40)],
            "_display": {"max_chars": 5000, "mirror_fields": ["text"], "limit_rows": False}}
    notes = []
    shown = _fold_twin_fields([page, dict(page)], ["value"], notes)
    assert shown[0]["text"] == page["text"]
    assert shown[0]["items"] == {"$model_mirror_of": "text", "rows": 40}
    assert notes[0] == {"path": ["value", 0, "items"], "mirror_of": ["value", 0, "text"]}
    # 선언이 없거나 본문이 없으면 목록을 그대로 둔다.
    plain = {"items": page["items"], "text": page["text"]}
    assert _fold_twin_fields(plain, ["value"], [])["items"] == page["items"]
    no_text = {"items": page["items"], "_display": page["_display"]}
    assert _fold_twin_fields(no_text, ["value"], [])["items"] == page["items"]


def test_resume_card_is_attached_once_after_compaction():
    import threading
    from conscious_supervisor import Supervisor

    class Store:
        def tool_index(self, limit=40):
            return [{"seq": 7, "name": "mcp__indiebizos__execute_ibl",
                     "input": {"id": "a" * 64, "excerpt": '{"code": "[self:write]{path:\\"/out/a.py\\"…'},
                     "result": {"id": "b" * 64, "chars": 300}, "is_error": False}]

    supervisor = object.__new__(Supervisor)
    supervisor.lock, supervisor.store, logged = threading.RLock(), Store(), []
    supervisor.log = lambda kind, **fields: logged.append(kind)
    assert supervisor._take_resume_card() is None
    supervisor.note_compaction()
    card = supervisor._take_resume_card()
    assert logged == ["context.compacted"]
    assert card["calls"] == [{"seq": 7, "name": "execute_ibl", "input": '{"code": "[self:write]{path:\\"/out/a.py\\"…',
                              "input_id": "a" * 64, "result_id": "b" * 64}]
    assert "calls" in card["recover"] and "압축" in card["note"]
    assert supervisor._take_resume_card() is None      # 한 번만


def test_fstring_bare_dollar_name_warns():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()

    def codes(source):
        plan = compile_program(source, registry, {"x": 1}, {})
        assert not plan.issues
        return [w["code"] for w in plan.preflight.get("warnings", [])]

    assert "FORMAT_UNINTERPOLATED" in codes('return f"() => {json($x)} and ${$x}"')
    assert "FORMAT_UNINTERPOLATED" not in codes('return f"cost $5 and $(a) ${$x}"')


# ---------------------------------------------------------------- 옛 용례 투영
def test_legacy_single_call_is_projected_only_when_current_checker_accepts():
    from ibl_usage_rag import current_form_of_legacy_call
    shown = current_form_of_legacy_call('[sense:video]{op: "summarize", url: "https://www.youtube.com/watch?v=example"}')
    assert shown == '#!ibl edition=2\nreturn [sense:video]{op: "summarize", url: "https://www.youtube.com/watch?v=example"}'
    # 여러 문장·파이프·변수·없는 낱말은 투영하지 않는다.
    assert current_form_of_legacy_call('[sense:search]{query: "a"} >> [table:take]{n: 3}') is None
    assert current_form_of_legacy_call('[sense:search]{query: $q}') is None
    assert current_form_of_legacy_call('[sense:없는낱말]{query: "a"}') is None


# ---------------------------------------------------------------- Codex 누출 차단
def test_codex_command_disables_plugin_skills_and_overlapping_native_tools():
    from providers.codex import CodexProvider
    assert "plugins" in CodexProvider.CODEX_DISABLED_FEATURES
    import inspect
    source = inspect.getsource(CodexProvider._build_command)
    assert 'features.{feature}=false' in source and "CODEX_DISABLED_FEATURES" in source


# ---------------------------------------------------------------- 실행기 속도
def test_cancel_check_is_polled_by_interval_not_by_step(tmp_path):
    """ep4211: MCP 경로의 취소 확인(파일·프로세스 조회)을 걸음마다 불러 30만 걸음에 35초가 걸렸다."""
    import time
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    rows = [{"n": i} for i in range(3000)]
    plan = compile_program("return len(filter($rows, ($r)=>$r.n % 2 == 0))", load_registry(str(tmp_path), "audit_test"),
                           {"rows": rows}, {})
    calls = [0]

    def never():
        calls[0] += 1
        return False

    result = Runtime(plan, {"rows": rows}, cancel_check=never, budget=Budget(steps=200000, rows=10000)).run()
    assert result["success"] and result["value"] == 1500
    assert 1 <= calls[0] < result["usage"]["steps"] / 20

    started = time.monotonic()
    cancelled = Runtime(plan, {"rows": rows}, cancel_check=lambda: True, budget=Budget(steps=200000, rows=10000)).run()
    assert cancelled["success"] is False and cancelled["diagnostic"]["code"] == "CANCELLED"
    assert time.monotonic() - started < 1


def test_distillation_recovers_checked_program_source_from_the_check_call():
    from legacy_example_projection import checked_program_sources
    handle = "$checked:" + "ab" * 32
    calls = [
        {"tool_name": "execute_ibl", "input": {"code": "return 1 + 1", "check": True},
         "result": json.dumps({"ok": True, "executed": False, "execute_args": {"code": handle}})},
        {"tool_name": "execute_ibl", "input": {"code": handle}, "result": '{"success": true, "value": 2}'},
        {"tool_name": "execute_ibl", "input": {"code": "return 3", "check": True}, "result": '{"ok": false}'},
    ]
    assert checked_program_sources(calls) == {handle: "return 1 + 1"}
    assert checked_program_sources(None) == {}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
