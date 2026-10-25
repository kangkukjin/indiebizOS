"""확정 코드 위임: 실제 접수/큐/원장/실행 경계. 모델·외부 발송 없이 검증한다."""
import json
import threading
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import thread_context as tc


@pytest.fixture
def code_world(tmp_path, monkeypatch):
    from agent_runner import AgentRunner
    from conversation_db import ConversationDB
    import delegation_tasks
    project = tmp_path / 'projects' / 'code-test'
    project.mkdir(parents=True)
    runner = object.__new__(AgentRunner)
    runner.config = {'id': 'target', 'name': '대상', 'allowed_nodes': ['self']}
    runner.project_id, runner.project_path = project.name, project
    runner.registry_key = project.name + ':target'
    runner.db = ConversationDB(str(project / 'conversations.db'))
    runner.cancel_event = threading.Event()
    runner.ai = None  # 코드 실행은 모델 초기화 여부에도 의존하지 않는다.
    runner._log = lambda message: None
    runner.cognitive_stream = lambda *a, **kw: pytest.fail('확정 코드를 모델에 전달했다')
    sent = []
    runner._send_response_to_sender = lambda *a: sent.append(a)
    monkeypatch.setattr(AgentRunner, 'agent_registry', {runner.registry_key: runner})
    monkeypatch.setattr(AgentRunner, 'internal_messages', {})
    monkeypatch.setattr(delegation_tasks, 'get_base_path', lambda: tmp_path)
    previous = tc.snapshot()
    tc.clear_all_context()
    tc.set_current_project_id(project.name)
    tc.set_current_agent_id('parent')
    tc.set_current_agent_name('부모')
    tc.set_task_origin('training')
    yield SimpleNamespace(runner=runner, cls=AgentRunner, project=project, sent=sent)
    tc.restore(previous)


def submit(world, code='return $값', **kwargs):
    from routing_system import _delegate_unified
    result = _delegate_unified({'mode': 'workflow', 'agent_id': 'target', 'steps': code,
                                'edition': 2, **kwargs}, str(world.project))
    return json.loads(result) if isinstance(result, str) else result


def drain(world):
    world.runner._check_internal_messages()


def test_code_uses_same_receipt_and_queue_without_ai_and_preserves_literal_input(code_world):
    w = code_world
    w.runner.db.create_task('parent-task', 'user', 'gui', '원 요청', '부모')
    tc.set_current_task_id('parent-task')
    value = {'text': '[task:literal] "원문"\n$다른값', 'rows': [1, 2]}
    receipt = submit(w, inputs={'값': value}, message='설명만 기록')
    assert receipt['accepted'] and receipt['state'] == 'queued'
    task_id = receipt['task_id']
    msg = w.cls.internal_messages[w.runner.registry_key][0]
    assert msg['execution_kind'] == 'ibl' and msg['origin'] == 'training'
    assert msg['chain'] == ['code-test:parent']
    before = w.runner.db.get_task(task_id)
    assert before['parent_task_id'] == 'parent-task' and before['status'] == 'pending'
    assert json.loads(before['delegation_context'])['ibl_request'] == {
        'code': '#!ibl edition=2\nreturn $값', 'edition': 2, 'inputs': {'값': value}}
    drain(w)
    child = w.runner.db.get_task(task_id)
    result = json.loads(child['result'])
    assert child['status'] == 'completed' and result['value'] == value
    assert result['resume']['run_id']
    parent = w.runner.db.get_task('parent-task')
    assert parent['pending_delegations'] == 0
    response, = json.loads(parent['delegation_context'])['responses']
    assert response['child_task_id'] == task_id and not response['failed']


def test_target_permission_and_inherited_restriction_identity_are_preserved(code_world, monkeypatch):
    import ibl_v2_entry
    import principal
    w = code_world
    w.runner.config['allowed_nodes'] = ['sense', 'limbs']
    tc.set_allowed_nodes({'self', 'table', 'others', 'sense', 'engines'})
    with principal.narrow(principal.member('member-fixture')):
        receipt = submit(w, 'return 7', allowed=['sense', 'limbs'])
    observed = []
    def execute(request, path, agent_id, cancel_check):
        observed.append((request, path, agent_id, tc.get_current_task_id(), tc.get_allowed_nodes(),
                         principal.current().key(), tc.get_task_origin()))
        return {'success': True, 'value': 7}
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', execute)
    drain(w)
    assert observed == [({'code': '#!ibl edition=2\nreturn 7', 'edition': 2}, str(w.project), 'target', receipt['task_id'],
                         {'self', 'table', 'others', 'sense'}, 'member:member-fixture', 'training')]
    assert principal.is_owner()
    assert tc.get_allowed_nodes() == {'self', 'table', 'others', 'sense', 'engines'}


@pytest.mark.parametrize('code', ['return [limbs:browser]{op:"snapshot"}', 'return $없는값'])
def test_denied_or_invalid_code_is_failed_without_model_or_legacy_fallback(code_world, monkeypatch, code):
    import workflow_engine
    monkeypatch.setattr(workflow_engine, 'execute_pipeline', lambda *a, **kw: pytest.fail('v2 실패 폴백'))
    receipt = submit(code_world, code)
    drain(code_world)
    row = code_world.runner.db.get_task(receipt['task_id'])
    assert row['status'] == 'failed' and json.loads(row['result'])['success'] is False


def test_cancel_before_execution_does_not_execute_code(code_world, monkeypatch):
    import ibl_v2_entry
    from task_cancellation import request
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', lambda *a, **kw: pytest.fail('취소 뒤 실행'))
    receipt = submit(code_world, 'return 7')
    request(code_world.project.name, receipt['task_id'])
    drain(code_world)
    assert code_world.runner.db.get_task(receipt['task_id'])['status'] == 'cancelled'


def test_delivery_failure_and_duplicate_do_not_rerun_code(code_world, monkeypatch):
    import ibl_v2_entry
    w = code_world
    calls = []
    monkeypatch.setattr(ibl_v2_entry, 'handle_request',
                        lambda *a, **kw: calls.append(a) or {'success': True, 'value': 'written'})
    report = w.runner._auto_report_to_chain
    monkeypatch.setattr(w.runner, '_auto_report_to_chain', lambda *a, **kw: (_ for _ in ()).throw(OSError('display')))
    receipt = submit(w, 'return 7')
    queued = dict(w.cls.internal_messages[w.runner.registry_key][0])
    drain(w)
    row = w.runner.db.get_task(receipt['task_id'])
    assert json.loads(row['delegation_context'])['ibl_result']['value'] == 'written'
    monkeypatch.setattr(w.runner, '_auto_report_to_chain', report)
    w.cls.internal_messages[w.runner.registry_key].append(queued)
    drain(w)
    assert len(calls) == 1 and w.runner.db.get_task(receipt['task_id'])['status'] == 'completed'
    w.cls.internal_messages[w.runner.registry_key].append(queued)
    drain(w)
    assert len(calls) == 1


def test_started_without_result_is_unknown_and_never_reexecuted(code_world, monkeypatch):
    import ibl_v2_entry
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', lambda *a, **kw: pytest.fail('불명확 실행 재시도'))
    receipt = submit(code_world, 'return 7')
    db = code_world.runner.db
    ctx = json.loads(db.get_task(receipt['task_id'])['delegation_context'])
    ctx['ibl_started'] = True
    db.update_task_delegation(receipt['task_id'], json.dumps(ctx), increment_pending=False)
    drain(code_world)
    row = db.get_task(receipt['task_id'])
    assert row['status'] == 'failed' and json.loads(row['result'])['status'] == 'unknown'


def test_explicit_async_child_reports_are_retained_without_ai_continuation(code_world, monkeypatch):
    from system_tools_delegate import _create_child_task
    import delegation_tasks
    import ibl_v2_entry
    w = code_world
    children = []
    def execute(*a, **kw):
        child = _create_child_task(tc.get_current_task_id(), '판단자', '명시 판단', str(w.project))
        children.append(child)
        return {'success': True, 'value': {'accepted': True, 'task_id': child}}
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', execute)
    receipt = submit(w, 'return 7')
    drain(w)
    w.runner.db.record_child_response(receipt['task_id'], {
        'child_task_id': children[0], 'response': '판단 결과', 'delivery_pending': True})
    assert delegation_tasks.recover_reports(w.project.name, '대상') == []
    ctx = json.loads(w.runner.db.get_task(receipt['task_id'])['delegation_context'])
    assert ctx['responses'][0]['response'] == '판단 결과' and 'ibl_request' in ctx


def test_explicit_legacy_array_rejects_before_creating_work(code_world):
    receipt = submit(code_world, ['[self:time]{}'], edition=1)
    assert not receipt['success'] and 'EDITION_RETIRED' in receipt['error']
    assert not code_world.cls.internal_messages


def test_conflicting_edition_rejects_before_creating_work(code_world):
    receipt = submit(code_world, '#!ibl edition=1\n[self:time]{}')
    assert not receipt['success'] and 'EDITION_CONFLICT' in receipt['error']
    assert not code_world.cls.internal_messages


def test_public_ibl_alias_inputs_and_authoring_edition_reach_the_same_executor(code_world, monkeypatch):
    from ibl_v2_entry import handle_request
    import ibl_routing
    from routing_system import _delegate_unified
    monkeypatch.setattr(ibl_routing, 'system_capability', lambda name: _delegate_unified)
    out = handle_request({'edition': 2, 'code':
        'return [others:delegate]{mode:"workflow",agent_id:"target",do:"return $값",inputs:{값:19}}'},
        str(code_world.project), 'parent')
    assert out['success'], out
    receipt = out['value']
    task_id = receipt['task_id']
    drain(code_world)
    row = code_world.runner.db.get_task(task_id)
    assert row['status'] == 'completed' and json.loads(row['result'])['value'] == 19
    assert json.loads(row['delegation_context'])['ibl_request']['edition'] == 2


def test_code_execution_observes_task_cancellation_during_run(code_world, monkeypatch):
    import ibl_v2_entry
    from task_cancellation import request
    def execute(payload, path, agent_id, cancel_check):
        assert not cancel_check()
        request(code_world.project.name, tc.get_current_task_id())
        assert cancel_check()
        return {'success': False, 'status': 'cancelled', 'error': 'cancelled'}
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', execute)
    receipt = submit(code_world, 'return 7')
    drain(code_world)
    assert code_world.runner.db.get_task(receipt['task_id'])['status'] == 'cancelled'


def test_qualified_local_target_works_and_other_project_is_rejected(code_world):
    receipt = submit(code_world, 'return 7', agent_id='code-test/target')
    assert receipt['accepted']
    drain(code_world)
    assert code_world.runner.db.get_task(receipt['task_id'])['status'] == 'completed'
    denied = submit(code_world, 'return 7', agent_id='other-project/target')
    assert not denied['success'] and denied['error_type'] == 'capability'
    assert not code_world.cls.internal_messages[code_world.runner.registry_key]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
