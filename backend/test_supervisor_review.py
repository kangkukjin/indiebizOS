"""Projection recovery retires only the corresponding stale intervention."""
import json

import boot_paths  # noqa: F401
import pytest
from supervisor_review import ibl_shape_repair_key, ibl_error_render_repair_key
from test_conscious_supervisor import supervisor, verdict, trigger_verdict  # noqa: F401

BAD = '''$a=$s1 & $s2 >> [table:union]{};
$p=[t:read]{query:"same"} >> [table:select]{columns:["title"]};
return {search:$a,paper:$p}'''
GOOD = '''$a=$s1.items & $s2.items >> [table:union]{};
$p=[t:read]{query:"same"};
return {search:$a,paper:$p.items >> [table:select]{columns:["title"]}}'''


def payloads(supervisor):
    args = []
    for origin in ('first', 'recovered'):
        inputs = {}
        for name in ('s1', 's2'):
            ref = supervisor.store.evidence({'edition': 2, 'success': True,
                'value': {'items': [{'title': name}]}, 'origin': origin})
            inputs[name] = {'$ref': ref['id']}
        args.append(inputs)
    return {'code': BAD, 'inputs': args[0]}, {'code': GOOD, 'inputs': args[1]}


@pytest.mark.parametrize('recovery', ['during_review', 'before_delivery'])
def test_rebinding_and_rewrapped_input_recovery_retires_stale_instruction(supervisor, monkeypatch, recovery):
    monkeypatch.setattr('model_result_view.evidence_store', lambda: supervisor.store)
    bad, good = payloads(supervisor)
    def finish(payload, failed=False):
        key = supervisor._start('execute_ibl', payload)
        supervisor._finish(key, {'success': not failed, 'executed': True}, failed)
    finish({'code': '[t:read]{query:"unresolved"}'}, True)
    finish(bad, True)
    def review(c, *a, **kw):
        if recovery == 'during_review':
            finish(good)
        return trigger_verdict(c, 'retry old projection')
    monkeypatch.setattr('supervisor_runtime.invoke', review)
    supervisor.review('repeated_failure')
    if recovery == 'before_delivery':
        assert supervisor.pending
        finish(good)
    assert supervisor.boundary() is None
    assert any(issue['open'] for issue in supervisor.issues.values())


@pytest.mark.parametrize('change', [
    GOOD.replace('query:"same"', 'query:"other"'),
    GOOD.replace('$s1.items', '$s1.other'),
    GOOD.replace('[t:read]', '[t:write]'),
    '[if:false]{' + GOOD + '}',
    '[t:write]{}; ' + GOOD,
    GOOD.replace('[t:read]{query:"same"}', '[t:read]{query:$s1.other}'),
])
def test_changed_inputs_effects_or_control_flow_cannot_retire_issue(change):
    inputs = {'s1': {'items': []}, 's2': {'items': []}}
    key = ibl_shape_repair_key('execute_ibl', {'code': BAD, 'inputs': inputs})
    assert key
    assert ibl_shape_repair_key('execute_ibl', {'code': change, 'inputs': inputs}) != key


def test_missing_reference_is_not_equivalent_to_recovery():
    assert ibl_shape_repair_key('execute_ibl', {'code': BAD,
        'inputs': {'s1': {'$ref': 'missing'}}}) is None


def test_unused_pipe_still_retains_its_input():
    a = '$a=$left >> [t:write]{}; return 1'
    b = a.replace('$left', '$right')
    args = {'left': [{'v': 1}], 'right': [{'v': 2}]}
    assert ibl_shape_repair_key('execute_ibl', {'code': a, 'inputs': args}) != ibl_shape_repair_key(
        'execute_ibl', {'code': b, 'inputs': args})


RENDER_BAD = '''$r=$sources >> [table:each]{parallel:6,on_error:"collect"}{
  return [sense:crawl]{url:$it.url}
}
return $r >> [table:each]{return is_ok($it) ? unwrap($it) : {err:text(error_of($it))[0:200]}}'''
RENDER_GOOD = RENDER_BAD.replace('text(error_of($it))[0:200]', 'json(error_of($it))[0:300]')


@pytest.mark.parametrize('recovery', ['during_review', 'before_delivery'])
def test_error_render_recovery_retires_only_its_stale_instruction(supervisor, monkeypatch, recovery):
    args = {'sources': [{'url': 'https://example.test/source'}]}

    def finish(code, failed=False):
        key = supervisor._start('execute_ibl', {'code': code, 'inputs': args})
        supervisor._finish(key, {'success': not failed, 'executed': True,
                                'source_complete': False}, failed)

    finish('[sense:crawl]{url:"https://example.test/blocked"}', True)
    finish(RENDER_BAD, True)

    def review(c, *a, **kw):
        if recovery == 'during_review':
            finish(RENDER_GOOD)
        return trigger_verdict(c, 'format error with json')

    monkeypatch.setattr('supervisor_runtime.invoke', review)
    supervisor.review('repeated_failure')
    if recovery == 'before_delivery':
        assert supervisor.pending
        finish(RENDER_GOOD)
    assert supervisor.boundary() is None
    assert sum(issue['open'] for issue in supervisor.issues.values()) == 1


@pytest.mark.parametrize('change', [
    RENDER_GOOD.replace('url:$it.url', 'url:$it.other'),
    RENDER_GOOD.replace('sense:crawl', 'self:write'),
    RENDER_GOOD.replace('is_ok($it)', 'true'),
    RENDER_GOOD.replace('unwrap($it)', 'null'),
    RENDER_GOOD.replace('parallel:6', 'parallel:1'),
    RENDER_GOOD.replace('error_of($it)', 'error_of($other)'),
    RENDER_GOOD.replace('return $r >>', 'return [] >>'),
])
def test_error_render_key_keeps_inputs_control_and_operations_exact(change):
    key = ibl_error_render_repair_key('execute_ibl', {'code': RENDER_BAD})
    assert key
    assert ibl_error_render_repair_key('execute_ibl', {'code': change}) != key


def test_formatting_in_operation_argument_cannot_retire_failure():
    code = 'return [sense:crawl]{url:text(error_of($r))}'
    assert ibl_error_render_repair_key('execute_ibl', {'code': code}) is None
    assert ibl_error_render_repair_key('execute_ibl', {'code': code.replace('text(', 'json(')}) is None
    assert ibl_error_render_repair_key('execute_ibl', {
        'code': RENDER_GOOD, 'inputs': {'sources': {'$ref': 'missing'}}}) is None


def findings(c):
    evidence = c.store.evidence({'target': 'version-a', 'observed': 'version-b'})['id']
    return [
        {'id': 'wait', 'scope': 'trigger', 'reason': '호출 정체',
         'instruction': '기존 호출을 확인하라', 'resolved_when': '기존 호출 종료',
         'evidence_ids': [evidence]},
        {'id': 'version', 'scope': 'goal', 'reason': '목표 판본 미반영',
         'instruction': '빌드 전에 목표 소스와 일치하는지 확인하라',
         'resolved_when': '소스 지문 일치', 'evidence_ids': [evidence]},
    ]


@pytest.mark.parametrize('recovery', ['during_review', 'before_delivery'])
def test_finished_wait_preserves_independent_goal_finding(supervisor, monkeypatch, recovery):
    active = supervisor._start('wait', {'job': 'existing'})

    def invoke(c, *a, **kw):
        items = findings(c)
        if recovery == 'during_review':
            c._finish(active, 'returned')
            c._start('inspect', {'job': 'existing'})
        return verdict(c, 'REWORK', instruction='old combined instruction', findings=items)

    monkeypatch.setattr('supervisor_runtime.invoke', invoke)
    supervisor.review('tool_stalled')
    if recovery == 'before_delivery':
        supervisor._finish(active, 'returned')
    notice = supervisor.boundary()
    assert notice is not None
    assert [f['id'] for f in notice['findings']] == ['version']
    assert notice['findings'][0]['needs_recheck']
    assert '빌드 전에 목표 소스' in notice['instruction']
    assert '기존 호출을 확인하라' not in notice['instruction']
    assert 'old combined instruction' not in notice['instruction']
    assert supervisor.boundary() is None


def test_legacy_review_after_progress_becomes_recheck_not_retry(supervisor, monkeypatch):
    active = supervisor._start('wait', {})

    def invoke(c, *a, **kw):
        c._finish(active, 'done')
        return verdict(c, 'REWORK', instruction='retry old job and check independent target')

    monkeypatch.setattr('supervisor_runtime.invoke', invoke)
    supervisor.review('tool_stalled')
    notice = supervisor.boundary()
    assert notice is not None and notice['findings'][0]['needs_recheck']
    assert '재확인' in notice['instruction']
    assert '그대로 실행하지' in notice['instruction']


@pytest.mark.parametrize('change', ['cancel', 'goal'])
def test_review_cannot_survive_cancel_or_goal_change(supervisor, monkeypatch, change):
    supervisor._start('wait', {})
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw:
                        verdict(c, 'REWORK', instruction='repair', findings=findings(c)))
    supervisor.review('tool_stalled')
    if change == 'cancel':
        supervisor.cancel_check = lambda: True
        assert '종료' in supervisor.boundary()
    else:
        supervisor.framing = {'task_framing': 'different goal'}
        assert supervisor.boundary() is None


def test_unknown_evidence_requires_recheck_without_losing_finding(supervisor, monkeypatch):
    supervisor._start('wait', {})

    def invoke(c, *a, **kw):
        items = findings(c)[1:]
        items[0]['evidence_ids'] = ['not-a-reference']
        return verdict(c, 'REWORK', instruction='repair', findings=items)

    monkeypatch.setattr('supervisor_runtime.invoke', invoke)
    supervisor.review('tool_stalled')
    notice = supervisor.boundary()
    assert notice['findings'][0]['needs_recheck']
    assert notice['findings'][0]['evidence_status'] == 'unverified'


@pytest.mark.parametrize('channel', ['native', 'tool'])
def test_goal_correction_reaches_execution_boundary_once(supervisor, monkeypatch, channel):
    active = supervisor._start('wait', {})
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw:
                        verdict(c, 'REWORK', findings=findings(c)))
    supervisor.review('tool_stalled')
    supervisor._finish(active, 'done')
    effects = []
    if channel == 'native':
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api_supervision import router
        import supervision_hook

        app = FastAPI()
        app.include_router(router, prefix='/ibl')
        client = TestClient(app)
        monkeypatch.setenv('INDIEBIZOS_SUPERVISED', '1')
        monkeypatch.setenv('INDIEBIZOS_AGENT_ID', supervisor.owner)
        monkeypatch.setenv('INDIEBIZOS_TASK_ID', supervisor.task)

        def urlopen(request, **kwargs):
            import io
            reply = client.post('/ibl/supervision/boundary', json=json.loads(request.data))
            assert reply.status_code == 200
            return io.BytesIO(reply.content)

        monkeypatch.setattr(supervision_hook.urllib.request, 'urlopen', urlopen)
        text = supervision_hook.check()
        assert '빌드 전에 목표 소스' in text and '기존 호출을 확인하라' not in text
        assert supervision_hook.check() is None
    else:
        result = json.loads(supervisor.run_tool('build', {}, lambda: effects.append('build')))
        assert result['not_executed'] and not effects
        notice = result['supervisor_instruction']
        assert [f['id'] for f in notice['findings']] == ['version']
    events = [json.loads(s) for s in (supervisor.store.directory / 'events.jsonl').read_text().splitlines()]
    assert sum(e['kind'] == 'instruction.delivered' for e in events) == 1


@pytest.mark.parametrize('bad', [None, 'text', [{'scope': 'goal'}], [{'scope': []}]])
def test_incomplete_findings_preserve_original_review_for_recheck(supervisor, monkeypatch, bad):
    active = supervisor._start('wait', {})
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw:
                        verdict(c, 'REWORK', instruction='independent defect', findings=bad))
    supervisor.review('tool_stalled')
    supervisor._finish(active, 'done')
    notice = supervisor.boundary()
    assert 'independent defect' in notice['instruction']
    assert all(f['needs_recheck'] for f in notice['findings'])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
