"""Calls in constructed values retain ordinary execution and recovery contracts."""
import json
from pathlib import Path
import threading

import boot_paths  # noqa: F401
import pytest

from ibl_run_journal import Journal
from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Budget, Runtime
from test_ibl_v2_assets import memory  # noqa: F401 — isolated DB/FTS/vector fixture


def adapter(run, params=None, result="Number", effects=None, **contract):
    return Adapter({"version": 1, "params": params or {}, "result": result,
                    "effects": effects or ["read_external"], **contract}, run)


def checked(source, registry=None, **kwargs):
    plan = compile_program(source, registry, **kwargs)
    assert not plan.issues, plan.report()
    return plan


def test_nested_fields_elements_and_arguments_run_in_source_order():
    seen = []
    reg = {
        "test:leaf": adapter(lambda rt, a: seen.append(a["n"]) or a["n"], {"n": "Number"}),
        "test:outer": adapter(lambda rt, a: seen.append("outer") or a, {"x": "Number", "rows": "List"}, "Record"),
    }
    source = '''return {z:[test:leaf]{n:1}, a:[
      [test:outer]{x:[test:leaf]{n:2},rows:[{n:[test:leaf]{n:3}}]},
      [test:leaf]{n:4}]}'''
    plan = checked(source, reg)
    assert seen == []
    out = Runtime(plan).run()
    assert out["success"], out
    assert out["value"] == {"z": 1, "a": [{"x": 2, "rows": [{"n": 3}]}, 4]}
    assert seen == [1, 2, 3, "outer", 4]


def test_local_and_library_functions_return_into_the_container_only():
    defs = {"twice": '[def:twice]($n){return $n*2}'}
    source = '''[def:wrap]($n){return {n:[fn:twice]{n:$n}};return 999}
    return {first:[fn:wrap]{n:3}, second:[[fn:twice]{n:4}], last:9}'''
    plan = checked(source, definitions=defs)
    out = Runtime(plan).run()
    assert out["value"] == {"first": {"n": 6}, "second": [8], "last": 9}
    assert all(row["result"] != "Unknown" for row in plan.function_contracts.values())
    assert len([e for e in out["evidence"] if e["kind"] == "function_result"]) == 3


def test_dynamic_function_failure_stops_later_fields_and_reports_original_location():
    seen = []
    reg = {"test:write": adapter(lambda rt, a: seen.append(a["n"]) or a["n"],
                                 {"n": "Number"}, effects=["write_external"])}
    defs = {"broken": '[def:broken]($n){return 1/$n}'}
    source = '''return {first:[test:write]{n:1}, broken:[fn:broken]{n:0},
                        skipped:[test:write]{n:2}}'''
    out = Runtime(checked(source, reg, definitions=defs)).run()
    assert not out["success"] and seen == [1]
    assert "value" not in out  # A partially built record is not a completed value.
    assert out["diagnostic"]["frames"][0]["function"] == "broken"
    assert any(e["kind"] == "invoke" and e["action"] == "test:write" for e in out["evidence"])


def test_nested_argument_failure_does_not_invoke_the_outer_action_or_tail():
    seen = []
    def fail(rt, args):
        seen.append("bad")
        raise Fault("OFFLINE", "fixture failure")
    reg = {
        "test:bad": adapter(fail),
        "test:outer": adapter(lambda rt, a: seen.append("outer") or 1, {"n": "Number"}),
        "test:tail": adapter(lambda rt, a: seen.append("tail") or 2),
    }
    source = 'return {x:[test:outer]{n:[test:bad]{}},y:[test:tail]{}}'
    out = Runtime(checked(source, reg)).run()
    assert not out["success"] and seen == ["bad"] and not out["source_complete"]
    start = out["diagnostic"]["source_span"]["start"]
    assert source[start:].startswith("[test:bad]")


@pytest.mark.parametrize("bad", ["$missing", '[test:leaf]{n:"bad"}', "[fn:unknown]{}"])
def test_static_error_in_later_field_prevents_all_effects(bad):
    seen = []
    reg = {"test:leaf": adapter(lambda rt, a: seen.append(1) or 1, {"n": "Number"})}
    plan = compile_program('return {first:[test:leaf]{n:1},bad:' + bad + '}', reg)
    out = Runtime(plan).run()
    assert plan.issues and not out["executed"] and not seen


def test_unselected_branch_and_zero_iteration_never_execute_nested_calls():
    reg = {"test:bad": adapter(lambda rt, a: pytest.fail("unselected effect"))}
    source = '''[if:false]{return {x:[test:bad]{}}}
    [repeat:0]{return [[test:bad]{}]}
    return {x:[] ?? [test:bad]{}, rows:[table:each]{items:[]}{return {x:[test:bad]{}}}}'''
    out = Runtime(checked(source, reg)).run()
    assert out["value"] == {"x": [], "rows": []}


def test_each_and_explicit_parallel_keep_shape_and_function_return_frames():
    source = '''[def:pair]($n){return {n:$n}}
    return {rows:[table:each]{items:[1,2],parallel:2}{return {v:[fn:pair]{n:$it}}},
            parallel:([fn:pair]{n:3} & [fn:pair]{n:4})}'''
    out = Runtime(checked(source)).run()
    assert out["value"] == {"rows": [{"v": {"n": 1}}, {"v": {"n": 2}}],
                            "parallel": [{"n": 3}, {"n": 4}]}


def test_recovered_failure_and_tool_evidence_survive_nested_projection():
    def fail(rt, args):
        raise Fault("OFFLINE", "fixture failure")
    reg = {
        "test:bad": adapter(fail),
        "test:good": adapter(lambda rt, a: Adapted(7, {"source": "fixture"})),
    }
    source = '''$x={nested:[{a:([test:bad]{} ?? [test:good]{})}]}
    return evidence($x.nested[0].a)'''
    out = Runtime(checked(source, reg)).run()
    assert out["success"] and not out["source_complete"]
    assert {"tool_failure", "recovered", "tool_evidence"} <= {
        e["kind"] for e in out["value"]["events"]}


@pytest.mark.parametrize("kind", ["permission", "cancelled", "budget"])
def test_nested_fallback_cannot_swallow_fatal_failure(kind):
    def fail(rt, args):
        raise Fault("DENIED", "fixture", kind=kind)
    reg = {"test:bad": adapter(fail)}
    out = Runtime(checked('return {x:([test:bad]{} ?? 1)}', reg)).run()
    assert not out["success"] and out["diagnostic"]["kind"] == kind


def test_shared_budget_covers_nested_each_and_skips_the_tail():
    reg = {"test:bad": adapter(lambda rt, a: pytest.fail("budget exceeded before tail"))}
    code = 'return {rows:[table:each]{items:[1,2,3]}{return {n:$it}},tail:[test:bad]{}}'
    out = Runtime(checked(code, reg), budget=Budget(rows=1)).run()
    assert out["diagnostic"]["kind"] == "budget"


def test_cancel_and_resume_preserve_identical_call_occurrences_in_functions(tmp_path):
    seen, stop = [], threading.Event()
    def write(rt, args):
        seen.append(args["n"])
        stop.set()
        return args["n"]
    reg = {"test:write": adapter(write, {"n": "Number"}, effects=["write_external"])}
    code = '''[def:save]($n){return {receipt:[test:write]{n:$n}}}
    return {a:[fn:save]{n:1},b:[[fn:save]{n:1},[fn:save]{n:2}]}'''
    plan = checked(code, reg)
    with Journal(tmp_path, plan.fingerprint) as journal:
        first = Runtime(plan, journal=journal, cancel_check=stop.is_set).run()
    assert first["diagnostic"]["kind"] == "cancelled" and seen == [1]
    for _ in range(2):
        with Journal(tmp_path, plan.fingerprint, first["resume"]) as journal:
            out = Runtime(plan, journal=journal).run()
        assert out["success"] and seen == [1, 1, 2]
        assert out["value"] == {"a": {"receipt": 1}, "b": [{"receipt": 1}, {"receipt": 2}]}
    assert sum(e["kind"] == "receipt_reused" for e in out["evidence"]) == 3


def test_uncertain_nested_write_is_not_repeated_or_skipped_on_resume(tmp_path):
    seen = []
    def crash(rt, args):
        seen.append("write")
        raise KeyboardInterrupt()
    reg = {"test:write": adapter(crash, effects=["write_external"]),
           "test:tail": adapter(lambda rt, a: pytest.fail("uncertain write before tail"))}
    plan = checked('return {x:[[test:write]{}],tail:[test:tail]{}}', reg)
    with Journal(tmp_path, plan.fingerprint) as journal:
        resume = {"run_id": journal.run_id}
        with pytest.raises(KeyboardInterrupt):
            Runtime(plan, journal=journal).run()
    with Journal(tmp_path, plan.fingerprint, resume) as journal:
        out = Runtime(plan, journal=journal).run()
    assert out["diagnostic"]["code"] == "EFFECT_UNCERTAIN" and seen == ["write"]


@pytest.mark.parametrize("wrapper", [
    '{x:[test:write]{path:"same"}}',
    '[test:outer]{x:[test:write]{path:"same"}}',
    '[fn:identity]{x:[test:write]{path:"same"}}',
])
def test_parallel_conflicts_include_nested_call_arguments(wrapper):
    reg = {
        "test:write": adapter(lambda rt, a: pytest.fail("static conflict"), {"path": "Text"},
                              effects=["write_external"], write_resources={"file": "path"}),
        "test:outer": adapter(lambda rt, a: a["x"], {"x": "Number"}, effects=["pure"]),
    }
    code = '[def:identity]($x){return $x}\n' + wrapper + ' & [test:write]{path:"same"}'
    plan = compile_program(code, reg)
    assert "PARALLEL_WRITE_CONFLICT" in {issue["code"] for issue in plan.issues}
    assert not Runtime(plan).run()["executed"]


def test_model_cost_and_effects_include_nested_function_arguments():
    reg = {"test:ai": adapter(lambda rt, a: pytest.fail("check must not execute"), effects=["model"])}
    code = '''[def:identity]($x){return $x}
    return {rows:[table:each]{items:[1,2,3]}{return {n:[fn:identity]{x:[test:ai]{}}}}}'''
    plan = checked(code, reg)
    assert "model" in plan.effects
    assert plan.preflight["declared_ai_visits_upper_bound"] == 3


def test_local_function_shadows_registered_write_resources_but_keeps_argument_writes():
    reg = {
        "test:write": adapter(lambda rt, a: 1, {"path": "Text"}, effects=["write_external"],
                              write_resources={"file": "path"}),
        "fn:local": adapter(lambda rt, a: pytest.fail("shadowed adapter"),
                            {"path": "Text", "n": "Number"}, effects=["write_external"],
                            write_resources={"file": "path"}),
    }
    prefix = '[def:local]($path,$n){return $n}\n'
    tail = ' & [test:write]{path:"same"}'
    source = prefix + '[fn:local]{path:"same",n:1}' + tail
    out = Runtime(checked(source, reg)).run()
    assert out["success"] and out["value"] == [1, 1]
    nested = prefix + '[fn:local]{path:"same",n:[test:write]{path:"same"}}' + tail
    plan = compile_program(nested, reg)
    assert "PARALLEL_WRITE_CONFLICT" in {issue["code"] for issue in plan.issues}


@pytest.mark.parametrize("source", [
    '[if:{x:[test:leaf]{}}.x]{return 1}',
    '[def:f]($x={n:[test:leaf]{}}){return $x};[fn:f]{}',
    'return ($r)=>{n:[test:leaf]{}}',
    'return f"${{n:[test:leaf]{}}.n}"',
    'return len([[test:leaf]{}])',
    'return {n:([test:leaf]{} + 1)}',
])
def test_pure_slots_remain_pure_even_through_a_container(source):
    reg = {"test:leaf": adapter(lambda rt, a: pytest.fail("pure slot must not execute"))}
    plan = compile_program(source, reg)
    assert "PURE_EXPRESSION" in {issue["code"] for issue in plan.issues}
    assert not Runtime(plan).run()["executed"]


@pytest.mark.parametrize("body", [
    '[if:true]{return 1}', '[try]{return 1}[catch]{return 2}',
    '[repeat:1]{return 1}', '[def:f](){return 1}',
])
def test_container_does_not_introduce_control_blocks_or_return_scopes(body):
    plan = compile_program('return {x:' + body + '}')
    assert "VALUE_EXPRESSION" in {issue["code"] for issue in plan.issues}
    assert not Runtime(plan).run()["executed"]


def test_real_file_adapter_nested_arguments_and_public_resume(tmp_path, monkeypatch):
    import ibl_run_journal
    from ibl_v2_entry import handle_request
    monkeypatch.setattr(ibl_run_journal, "journal_root", lambda _: tmp_path / "runs")
    source = tmp_path / "source.txt"
    source.write_text("원문 $literal")
    request = {"edition": 2, "code": '''return {copy:[self:write]{
      path:"outputs/copy.txt",content:[self:read]{path:"source.txt"}.text}}'''}
    first = handle_request(request, str(tmp_path))
    assert first["success"], first
    target = tmp_path / "outputs/copy.txt"
    assert target.read_text() == source.read_text()
    target.write_text("external change")
    second = handle_request({**request, "resume": first["resume"]}, str(tmp_path))
    assert second["success"] and target.read_text() == "external change"


def test_episode4071_original_shape_runs_real_legacy_idiom_without_retry(memory, tmp_path, monkeypatch):
    import ibl_engine
    import ibl_run_journal
    from ibl_v2_entry import handle_request
    root = Path(__file__).resolve().parents[1]
    entries = json.loads((root / "data/idioms/curated.json").read_text())["idioms"]
    body = next(e["body"] for e in entries if e["name"] == "본문에서찾기")
    memory.add_examples_batch([{"intent": "원문 문단의 가격과 사양 확인", "ibl_code": body,
                               "alias": "본문에서찾기", "category": "phrase"}])
    monkeypatch.setattr(ibl_run_journal, "journal_root", lambda _: tmp_path / "runs")
    original, calls = ibl_engine.execute_ibl, []
    def leaf(ti, *args, **kwargs):
        if (ti.get("_node"), ti.get("action")) != ("sense", "crawl"):
            return original(ti, *args, **kwargs)
        url = ti["params"]["url"]
        calls.append(url)
        rows = [{"text": text, "url": url, "paragraph_index": i}
                for i, text in enumerate(["제품 안내", "RTX 3060 12GB / 16GB", "최저가", "1,277,800원", "2,068,000원"])]
        return {"success": True, "items": rows, "url": url,
                "title": "고정 상품 자료", "text": "\n".join(row["text"] for row in rows)}
    monkeypatch.setattr(ibl_engine, "execute_ibl", leaf)
    prefix = ('$a=[sense:crawl]{url:"https://example.org/budget",max_length:15000};'
              '$b=[sense:crawl]{url:"https://example.org/gpu16",max_length:12000};')
    a = '[fn:본문에서찾기]{목록:$a.items,패턴:"판매|최저|1,277|3060|품절|단종",문맥:1,개수:12}'
    b = '[fn:본문에서찾기]{목록:$b.items,패턴:"최저|2,068|16GB|품절|단종",문맥:1,개수:8}'
    inline = prefix + 'return {budget:' + a + ',gpu16:' + b + '}'
    hoisted = prefix + '$x=' + a + ';$y=' + b + ';return {budget:$x,gpu16:$y}'
    outputs = [handle_request({"edition": 2, "code": code}, str(tmp_path)) for code in (inline, hoisted)]
    for out in outputs:
        assert out["success"] and out["source_complete"], out
        assert "1,277,800원" in [row["text"] for row in out["value"]["budget"]["items"]]
        assert "2,068,000원" in [row["text"] for row in out["value"]["gpu16"]["items"]]
    assert {k: v["items"] for k, v in outputs[0]["value"].items()} == {
        k: v["items"] for k, v in outputs[1]["value"].items()}
    assert len(calls) == 4  # Two fetches per program, no corrective resubmission.


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
