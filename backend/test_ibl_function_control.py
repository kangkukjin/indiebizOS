"""Live pure function body steering uses the original task, evidence and budget."""
import boot_paths  # noqa: F401
import pytest
from ibl_run_control import steer, status
from ibl_v2_entry import handle_request
from ibl_v2_ir import digest
from test_ibl_run_control import explicit_actor, launch, scoped_run, change, writer  # noqa: F401


CODE = '[def:twice]($n){return $n*2};[t:gate]{};$v=[fn:twice]{n:3};return $v'


def definition_change(ref, action='fn:twice', expected=None, source='return $n*3', scope=None):
    progress = status(ref)['progress']
    target = next(t for t in progress['boundaries'] if t['action'] == action
                  and (scope is None or t.get('scope') == scope))
    assert target['controls'] == ['definition']
    payload = {'root_task': progress['root_task'], 'plan_hash': progress['plan_hash'],
               'node_id': target['node_id'], 'revision': target['revision'], 'ordinal': target['next_ordinal'],
               'expected_args_hash': digest({'n': 3} if expected is None else expected), 'definition': source}
    if 'scope' in target:
        payload['scope'] = target['scope']
    return payload


def test_definition_change_preserves_effect_receipts_and_survives_repair(launch, tmp_path):
    effects = []
    code = CODE.replace('return $v', '[t:write]{path:$path,content:f"${$v}"};return $v')
    inputs = {'path': str(tmp_path / 'result')}
    with launch(code, {'t:write': writer(lambda rt, a: effects.append(a) or a['content'])}, inputs) as state:
        ref, out, release, worker, request, _ = state
        payload = definition_change(ref)
        assert steer(ref, payload, 'body')['delivery'] == 'accepted'
        assert steer(ref, payload, 'body')['delivery'] == 'accepted'
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == 9, out
        assert effects == [{'path': inputs['path'], 'content': '9'}]
        assert steer(ref, payload, 'body')['delivery'] == 'applied'
        for offset in (0, 1, 2):
            updated = {**request, 'code': '\n' * offset + code.replace('return $v', f'return $v+{offset}')}
            repair = {'run_id': ref['task_id']}
            checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
            assert checked['ok'], checked
            assert checked['repair']['inherited_controls'][0]['mode'] == 'recompute_pure'
            result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
            assert result['success'] and result['value'] == 9 + offset, result
            resumed = handle_request({**updated, 'resume': repair}, str(tmp_path))
            assert resumed['success'] and resumed['value'] == result['value'], resumed
            assert len(effects) == 1


def test_scoped_definition_changes_only_one_parallel_invocation(scoped_run, tmp_path):
    code = ('[def:twice]($n){return $n*2};'
            '[table:each]{items:[10,20],parallel:2}{[t:gate]{n:$it};[fn:twice]{n:$it}}')
    with scoped_run(code) as (handles, _, release, _, out, worker, request):
        ref, scope = handles[10]
        payload = definition_change(ref, expected={'n': 10}, scope=scope)
        steer(ref, payload, 'ten')
        for event in release.values():
            event.set()
        worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [30, 40], out
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == [30, 40], resumed


@pytest.mark.parametrize('source', ['[t:gate]{}', '[self:script]{code:"x"}', 'return ($x)=>$x',
                                  '[def:other]($x){return $x};return 1', 'return [fn:twice]',
                                  'return $unknown', 'return {', '', 'x' * 65537])
def test_replacement_cannot_capture_code_or_effects(launch, source):
    with launch(CODE) as (ref, out, release, worker, *_):
        with pytest.raises(ValueError):
            steer(ref, definition_change(ref, source=source), 'bad')
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == 6, out
        assert not status(ref)['progress']['requests']


def test_definition_changes_cas_and_result_contract(launch):
    with launch(CODE) as (ref, out, release, worker, *_):
        payload = definition_change(ref, source='return "wrong type"')
        steer(ref, payload, 'first')
        steer(ref, definition_change(ref), 'second')
        with pytest.raises(ValueError, match='같은 request_id'):
            steer(ref, definition_change(ref), 'first')
        release.set(); worker.join(10)
        assert not out[0]['success'], out
        rows = status(ref)['progress']['requests']
        assert rows[0]['state'] == 'applied'
        assert rows[1]['state'] == 'not_applied'
        assert rows[1]['reason'] == 'definition_revision_mismatch'


def test_stale_function_arguments_do_not_replace_body(launch):
    with launch(CODE) as (ref, out, release, worker, *_):
        steer(ref, definition_change(ref, expected={'n': 4}), 'stale')
        release.set(); worker.join(10)
        assert out[0]['value'] == 6
        assert status(ref)['progress']['requests'][0]['reason'] == 'input_revision_mismatch'


@pytest.mark.parametrize('edit', ['return $n*4', 'return $n*2+1', 'return $n * 2'])
def test_repair_cannot_change_original_definition_after_override(launch, tmp_path, edit):
    with launch(CODE) as (ref, out, release, worker, request, _):
        steer(ref, definition_change(ref), 'body')
        release.set(); worker.join(10)
        assert out[0]['success'], out
        checked = handle_request({**request, 'code': CODE.replace('return $n*2', edit),
                                  'check': True, 'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert not checked['ok'] and checked['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', checked


def test_repair_checks_changed_inferred_return_contract_before_activation(launch, tmp_path):
    code = ('[def:inner](){return 2};[def:outer](){return [fn:inner]{}};'
            '[t:gate]{};[fn:outer]{}')
    with launch(code) as (ref, out, release, worker, request, _):
        steer(ref, definition_change(ref, action='fn:outer', expected={}, source='return 3'), 'body')
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == 3, out
        checked = handle_request({**request, 'code': code.replace('return 2', 'return "text"'),
                                  'check': True, 'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert not checked['ok'] and checked['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', checked


def test_effectful_function_and_adapter_definition_are_not_exposed(launch):
    code = '[def:read](){return [t:gate]{}};[fn:read]{}'
    with launch(code) as (ref, *_):
        targets = status(ref)['progress']['boundaries']
        assert not any(t['action'] == 'fn:read' for t in targets)
        payload = change(ref, 't:gate', {}, {})
        payload.pop('changes'); payload['definition'] = 'return 3'
        with pytest.raises(ValueError, match='정의 변경을 지원하지'):
            steer(ref, payload, 'bad')


def test_override_uses_parent_budget_cancellation_and_field_evidence():
    from common.expression_eval import Binding
    from ibl_function_control import evaluate
    from ibl_v2_compile import compile_program
    from ibl_v2_ir import Fault
    from ibl_v2_runtime import Budget, Runtime
    parent = Runtime(compile_program('return 0', {}), budget=Budget(steps=100))
    node = parent.plan.root
    keep = parent.event(node, 'input_keep')
    drop = parent.event(node, 'input_drop')
    edit = parent.event(node, 'steer_applied')
    row = Binding.record({'keep': Binding(7, frozenset({keep})), 'drop': Binding(8, frozenset({drop}))})
    args = Binding.record({'row': row}).controlled({edit})
    result = evaluate(parent, node, 'return {selected:$row.keep}', {'params': {'row': 'Unknown'}, 'result': 'Record'}, args)
    assert result.value == {'selected': 7}
    evidence = parent.evidence(result.select('selected').evidence)
    from ibl_v2_completion import selected_events
    kinds = {e['kind'] for e in selected_events(parent.trace, result.select('selected').evidence)}
    assert 'input_keep' in kinds and 'input_drop' not in kinds and 'steer_applied' in kinds
    assert any(v.get('definition_revision') for v in evidence['source_map'].values())
    assert parent.budget.used_steps > 0
    parent.budget.steps = parent.budget.used_steps
    with pytest.raises(Fault) as exhausted:
        evaluate(parent, node, 'return 1', {'params': {}, 'result': 'Number'}, Binding.record({}))
    assert exhausted.value.kind == 'budget'
    parent.cancel_check = lambda: True
    with pytest.raises(Fault) as cancelled:
        evaluate(parent, node, 'return 1', {'params': {}, 'result': 'Number'}, Binding.record({}))
    assert cancelled.value.code == 'CANCELLED'


def test_identical_override_source_keeps_distinct_call_source_coordinates():
    from common.expression_eval import Binding
    from ibl_function_control import evaluate
    from ibl_v2_compile import compile_program
    from ibl_v2_ir import Node
    from ibl_v2_runtime import Runtime
    parent = Runtime(compile_program('return 0', {}))
    calls = [Node('call', 1, 2), Node('call', 3, 4)]
    results = [evaluate(parent, call, 'return 1+2', {'params': {}, 'result': 'Number'}, Binding.record({}))
               for call in calls]
    assert results[0].value == results[1].value == 3
    assert results[0].evidence != results[1].evidence
    for call, result in zip(calls, results):
        locations = parent.evidence(result.evidence)['source_map'].values()
        assert {entry['controlled_call'] for entry in locations} == {call.id}


def test_pipe_and_default_arguments_are_bound_before_body_change(launch):
    code = '[def:twice]($n,$factor=2){return $n*$factor};[t:gate]{};3 >> [fn:twice]{}'
    with launch(code) as (ref, out, release, worker, *_):
        steer(ref, definition_change(ref, expected={'n': 3, 'factor': 2}, source='return $n*$factor+1'), 'body')
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == 7, out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
