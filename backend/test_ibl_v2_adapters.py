"""표 어댑터의 입력 계약은 외부 효과 전에 알려진 오류를 거절한다."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.mark.parametrize("count", ["-4", "-1.0", "+-4"])
def test_negative_take_is_rejected_before_external_reads(tmp_path, count):
    calls = []
    registry = load_registry(str(tmp_path))
    registry["fixture:rows"] = Adapter(
        {"version": 1, "params": {}, "result": "List", "effects": ["read_external"]},
        lambda rt, args: calls.append(1) or [{"n": 1}])
    plan = compile_program('$rows=[fixture:rows]{}\nreturn $rows >> [table:take]{n:' + count + '}',
                           registry, {"count": -4})
    assert any(issue["code"] == "ARGUMENT_CONTRACT" for issue in plan.issues), plan.report()
    assert not Runtime(plan).run()["executed"]
    assert not calls


def test_dynamic_take_uses_same_minimum_contract(tmp_path):
    registry = load_registry(str(tmp_path))
    registry["fixture:count"] = Adapter(
        {"version": 1, "params": {}, "result": "Number", "effects": ["pure"]},
        lambda rt, args: -4)
    plan = compile_program('$count=[fixture:count]{}\nreturn [1,2] >> [table:take]{n:$count}', registry)
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert not out["success"] and out["diagnostic"]["code"] == "ARGUMENT_CONTRACT", out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('tail', [
    '[table:take]{n:1.5}', '[table:take]{n:0-4}', '[table:take]{n:$n}',
    '[table:sort]{by:[]}', '[table:sort]{by:""}',
])
def test_known_invalid_arguments_do_not_collect_first(tmp_path, tail):
    calls = []
    registry = load_registry(str(tmp_path))
    registry['fixture:rows'] = Adapter(
        {'version': 1, 'params': {}, 'result': 'List<Record>', 'effects': ['read_external']},
        lambda rt, args: calls.append(1) or [{'n': 1}])
    plan = compile_program('$n=0-4; $rows=[fixture:rows]{}; return $rows >> ' + tail, registry)
    assert any(i['code'] == 'ARGUMENT_CONTRACT' for i in plan.issues), plan.report()
    assert not Runtime(plan).run()['executed'] and not calls


@pytest.mark.parametrize('prefix', [
    '$n=-4; $n=1;',
    '$n=-4; [if:true]{$n=1}',
    '$n=-4; [repeat:1]{$n=1}',
    '$n=-4; [def:f]($n){return [1] >> [table:take]{n:$n}}; return [fn:f]{n:1};',
])
def test_constant_facts_do_not_survive_assignment_or_shadowing(tmp_path, prefix):
    source = prefix if '[def:' in prefix else prefix + ' return [1] >> [table:take]{n:$n}'
    plan = compile_program(source, load_registry(str(tmp_path)))
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == [1], out


@pytest.mark.parametrize('count', ['1.0', '2/2', '1'])
def test_integral_counts_keep_existing_numeric_semantics(tmp_path, count):
    plan = compile_program('[1,2] >> [table:take]{n:' + count + '}', load_registry(str(tmp_path)))
    assert not plan.issues, plan.report()
    assert Runtime(plan).run()['value'] == [1]


def test_partial_payload_requires_explicit_adapter_contract():
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault, UNIT
    raw = {'success': False, 'items': [{'title': 'kept'}], 'errors': [{'query': 'bad'}]}
    for enabled in (False, True):
        contract = {'protocol': 'legacy-envelope', **({'partial_value_path': ''} if enabled else {})}
        with pytest.raises(Fault) as failure:
            decode_envelope(raw, contract)
        assert failure.value.partial == (raw if enabled else UNIT)
    with pytest.raises(Fault) as denied:
        decode_envelope({**raw, 'denied': True}, {'protocol': 'legacy-envelope', 'partial_value_path': ''})
    assert denied.value.kind == 'permission' and denied.value.partial is UNIT


def test_chunk_current_example_compiles(tmp_path):
    from ibl_access import load_nodes_raw
    from model_result_view import current_action_definition
    registry = load_registry(str(tmp_path))
    spec = load_nodes_raw()['nodes']['table']['actions']['chunk']
    hint = current_action_definition(spec, registry['table:chunk'].contract)['target_description']
    example = hint.split('예: ', 1)[1].split('. 합친', 1)[0]
    plan = compile_program(example, registry, {'본문': '원문'})
    assert not plan.issues, plan.report()
