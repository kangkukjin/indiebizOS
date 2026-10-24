"""예약 원문은 창·모델 없이 실행하고 검증·실패 영수증을 그대로 보존한다."""
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from calendar_actions import CalendarActionsMixin


@pytest.fixture
def host(monkeypatch, tmp_path):
    h = CalendarActionsMixin()
    h._log = lambda message: None
    h._owner_run_path = lambda owner: str(tmp_path)
    for name in ('_execute_visible_system_ai', '_execute_visible_agent',
                 '_open_window_and_wait_ws', '_inject_message_via_ws'):
        monkeypatch.setattr(h, name, lambda *a, **kw: pytest.fail('예약이 창·모델 실행으로 우회함'))
    notices, history = [], []
    monkeypatch.setitem(sys.modules, 'notification_manager', SimpleNamespace(
        get_notification_manager=lambda: SimpleNamespace(
            success=lambda **kw: notices.append(('ok', kw)),
            warning=lambda **kw: notices.append(('warn', kw)))))
    import trigger_engine
    monkeypatch.setattr(trigger_engine, 'add_history', lambda **kw: history.append(kw))
    return h, notices, history


@pytest.mark.parametrize('owner,agent', [('__system_ai__', 'system_ai'), ('project', 'agent'), ('', '')])
@pytest.mark.parametrize('verified', [True, False])
def test_owned_schedule_executes_original_inputs_and_keeps_assertion_receipt(
        host, tmp_path, monkeypatch, owner, agent, verified):
    import thread_context as tc
    import ibl_v2_entry
    h, notices, history = host
    before = tc.snapshot()
    seen = []
    original = ibl_v2_entry.handle_request

    def handle(payload, path, agent_id=None):
        seen.append((path, agent_id, tc.get_current_agent_id(), tc.get_task_origin(),
                     tc.get_call_channel(), tc.get_current_task_id()))
        return original(payload, path, agent_id=agent_id)

    monkeypatch.setattr(ibl_v2_entry, 'handle_request', handle)
    result = h._action_run_pipeline({
        'owner_project_id': owner, 'owner_agent_id': agent, 'title': '검증 시험',
        'action_params': {'edition': 2, 'trigger_id': 'trigger', 'inputs': {'actual': verified},
                          'pipeline': 'assert $actual == true, "verification failed"\nreturn {verified:$actual}'}})
    assert len(seen) == 1
    path, aid, actor, origin, channel, task = seen[0]
    assert path == str(tmp_path) and aid == agent and actor == (agent or 'system_ai')
    assert origin == channel == 'scheduler' and task.startswith('task_schedule_')
    assert tc.snapshot() == before
    assert result['success'] is verified
    assert result['resume']['run_id']
    assert history[0]['success'] is verified
    assert notices[0][0] == ('ok' if verified else 'warn')
    if verified:
        assert result['value'] == {'verified': True}
    else:
        assert 'verification failed' in str(result['error'])


@pytest.mark.parametrize('failure', [False, True])
def test_notification_failure_does_not_repeat_execution_or_replace_receipt(host, monkeypatch, failure):
    import notification_manager
    h, _, _ = host
    calls = []
    receipt = {'success': not failure, 'resume': {'run_id': 'original'},
               'error': 'unknown effect' if failure else None, 'value': {'verified': not failure}}
    h._execute_scheduled_pipeline = lambda *a, **kw: calls.append(a) or receipt

    def unavailable():
        raise RuntimeError('notification unavailable')

    monkeypatch.setattr(notification_manager, 'get_notification_manager', unavailable)
    result = h._action_run_pipeline({'owner_project_id': '__system_ai__', 'owner_agent_id': 'system_ai',
                                    'action_params': {'pipeline': 'return 1'}})
    assert result is receipt and len(calls) == 1


def test_pipeline_exception_is_reported_without_fallback_execution(host):
    h, _, _ = host
    calls = []

    def broken(*a, **kw):
        calls.append(a)
        raise RuntimeError('connection lost after dispatch')

    h._execute_scheduled_pipeline = broken
    result = h._action_run_pipeline({'owner_project_id': '__system_ai__',
                                    'action_params': {'pipeline': 'return 1'}})
    assert not result['success'] and 'connection lost' in result['error']
    assert len(calls) == 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
