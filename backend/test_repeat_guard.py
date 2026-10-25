"""반복 관측: 입력/결과/실행 수명, 직결·MCP 경계와 기존 감독의 소유권."""
import asyncio
import json
import boot_paths  # noqa: F401
import pytest
import repeat_guard as guard
from thread_context import actor_context


@pytest.mark.parametrize('results', [list(range(10, 60, 10)), [{'time': i} for i in range(8)]])
def test_changed_results_are_neither_repetition_nor_a_progress_claim(results):
    with guard.execution_scope(['a'], 't') as key:
        assert all(guard.advise(key, 'same input', guard.digest(result)) == '' for result in results)


@pytest.mark.parametrize('result', [{'state': 'waiting'}, {'success': False, 'error': 'same failure'}])
def test_same_result_notice_describes_observation_without_instruction(result):
    with guard.execution_scope(['a'], 't') as key:
        outputs = [guard.advise(key, 'same', guard.digest(result)) for _ in range(5)]
    assert outputs == ['', '', '\n\n[반복 관측] 같은 입력으로 같은 결과를 연속 3회 관측했습니다.', '',
                       '\n\n[반복 관측] 같은 입력으로 같은 결과를 연속 5회 관측했습니다.']


@pytest.mark.parametrize('ending', ['complete', 'cancel', 'exception'])
def test_state_is_discarded_at_execution_end(ending):
    try:
        with guard.execution_scope(['a'], 't') as key:
            for _ in range(2): guard.advise(key, 'same', 'same')
            if ending == 'cancel': raise GeneratorExit()
            if ending == 'exception': raise RuntimeError('fixture')
    except (GeneratorExit, RuntimeError):
        pass
    assert key not in guard._chains and ('a', 't') not in guard._active
    with guard.execution_scope(['a'], 't') as next_key:
        assert key != next_key and guard.advise(next_key, 'same', 'same') == ''


def test_same_agent_concurrent_tasks_do_not_share_counts():
    with guard.execution_scope(['a'], 't1') as a, guard.execution_scope(['a'], 't2') as b:
        assert guard.advise(a, 'x', 'y') == guard.advise(a, 'x', 'y') == ''
        assert guard.advise(b, 'x', 'y') == ''
        assert '3회' in guard.advise(a, 'x', 'y')


def test_direct_observes_raw_result_before_its_own_advice(monkeypatch):
    import system_tools
    monkeypatch.setattr('supervision_bus.current', lambda *a: None)
    result = {'status': 'waiting', 'progress': 0}
    monkeypatch.setattr(system_tools, '_execute_tool_inner', lambda *a, **kw: dict(result))
    with actor_context(agent_id='a', task_id='t'), guard.execution_scope(['a'], 't'):
        for progress in [10, 20, 30]:
            result['progress'] = progress
            assert '_model_advisory' not in system_tools.execute_tool('fixture', {}, '.', agent_id='a')
        result['progress'] = 30
        system_tools.execute_tool('fixture', {}, '.', agent_id='a')
        same = system_tools.execute_tool('fixture', {}, '.', agent_id='a')
        assert '3회' in same['_model_advisory'] and same['progress'] == 30
        assert '_model_advisory' not in system_tools.execute_tool('fixture', {}, '.', agent_id='a')
        assert '5회' in system_tools.execute_tool('fixture', {}, '.', agent_id='a')['_model_advisory']


def test_active_supervisor_receives_observation_without_second_notice(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('supervision_bus.current', lambda *a: SimpleNamespace(enabled=True))
    with guard.execution_scope(['a'], 't') as key:
        for _ in range(5):
            assert guard.observe_result('fixture', {}, 'same', 'a', 't') == ''
        assert guard._chains[key] is None


def test_mcp_backend_roundtrip_has_execution_scoped_observation(tmp_path, monkeypatch):
    import mcp_server as mcp
    import api_ibl
    monkeypatch.setattr('supervision_bus.current', lambda *a: None)
    monkeypatch.setattr('system_tools._execute_ibl_unified', lambda *a, **kw: {'success': True, 'value': 'waiting'})
    monkeypatch.setattr(mcp, '_http_identity', lambda ctx: ('probe', str(tmp_path), 'turn', 'user'))
    def backend(route, payload, timeout):
        assert route == '/ibl/execute'
        return json.dumps(asyncio.run(api_ibl.execute_ibl_code(api_ibl.IBLRequest(**payload))))
    monkeypatch.setattr(mcp, '_post_backend', backend)
    with guard.execution_scope(['probe'], 'turn'):
        outputs = [asyncio.run(mcp.execute_ibl('return 1', str(tmp_path))) for _ in range(3)]
        assert all('_model_advisory' not in json.loads(o) for o in outputs[:2])
        assert '3회' in json.loads(outputs[2])['_model_advisory']
    with guard.execution_scope(['probe'], 'turn'):
        assert '_model_advisory' not in json.loads(asyncio.run(mcp.execute_ibl('return 1', str(tmp_path))))


def test_projected_result_ids_are_replaced_by_actual_evidence(tmp_path, monkeypatch):
    from supervision_store import TurnStore
    from model_result_view import repeat_observation
    store = TurnStore(tmp_path)
    monkeypatch.setattr('model_result_view.evidence_store', lambda: store)
    monkeypatch.setattr('supervision_bus.current', lambda *a: None)
    ref = store.evidence({'value': 42})
    with guard.execution_scope(['a'], 't'):
        out = [guard.observe_result('execute_ibl', {'code': 'return 42'},
                {'result_ref': {'id': ref['id']}, 'display_counter': i}, 'a', 't', read_observation=repeat_observation) for i in range(3)]
    assert '3회' in out[-1]


def test_job_observation_preserves_producer_progress(supervisor):
    from conscious_supervisor import _job_observation
    value = {'job_id': 'j', 'status': 'running', 'pages_written': 4, 'revision': 'v4'}
    assert _job_observation({'items': [value]}) == [value]
    for i in range(1, 5):
        key = supervisor._start('status', {})
        supervisor._finish(key, {**value, 'pages_written': i})
    assert supervisor.repeats == 1


@pytest.mark.parametrize('code', ['return {status:"waiting",progress:2}', 'assert false,"same failure"'])
def test_real_ibl_runs_compare_outcomes_despite_new_execution_receipts(tmp_path, monkeypatch, code):
    from ibl_v2_entry import handle_request
    from model_result_view import repeat_observation
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr('model_result_view.evidence_store', lambda: store)
    monkeypatch.setattr('supervision_bus.current', lambda *a: None)
    outputs = []
    with guard.execution_scope(['a'], 't'):
        for _ in range(3):
            result = handle_request({'edition': 2, 'code': code}, project_path=str(tmp_path))
            assert result['executed'] is True
            outputs.append(guard.observe_result('execute_ibl', {'code': code}, result, 'a', 't',
                                                read_observation=repeat_observation))
    assert outputs[:2] == ['', ''] and '3회' in outputs[-1]


def test_ibl_observation_preserves_producer_timestamps_and_partial_failure():
    from model_result_view import repeat_observation
    from copy import deepcopy
    result = {'edition': 2, 'executed': True, 'success': True, 'source_complete': True,
              'value': {'progress': 1, 'time': 10}, 'usage': {'elapsed_ms': 2}, 'resume': {'run_id': 'a'}}
    next_run = deepcopy(result)
    next_run.update(usage={'elapsed_ms': 4}, resume={'run_id': 'b'})
    assert repeat_observation(result) == repeat_observation(next_run)
    next_run['value']['time'] = 11
    assert repeat_observation(result) != repeat_observation(next_run)
    partial = {**result, 'success': False, 'partial_wire': {'data': [1]}, 'error': 'incomplete'}
    assert repeat_observation(partial)['partial_wire'] == {'data': [1]}


@pytest.mark.parametrize('code', ['return {status:"waiting",progress:2}', 'return 42',
                                      'return {job_id:"j",status:"running",progress:2}'])
def test_on_supervisor_uses_same_actual_ibl_result_view(supervisor, tmp_path, monkeypatch, code):
    from ibl_v2_entry import handle_request
    from model_result_view import project_v2_result
    monkeypatch.setattr('model_result_view.evidence_store', lambda: supervisor.store)
    initial = supervisor.last_progress
    for _ in range(3):
        result = handle_request({'edition': 2, 'code': code}, project_path=str(tmp_path))
        assert result['executed'] is True
        displayed = project_v2_result(result)
        supervisor._finish(supervisor._start('execute_ibl', {'code': code}), displayed)
    assert supervisor.repeats == 3 and supervisor.trigger == 'unchanged_repeat'
    if 'job_id' in code:
        assert supervisor.last_progress == initial


def test_job_subset_does_not_hide_other_changed_observations(supervisor):
    initial = supervisor.last_progress
    for i in range(5):
        result = {'job': {'job_id': 'j', 'status': 'running'}, 'new_records': i}
        supervisor._finish(supervisor._start('inspect', {}), result)
    assert supervisor.repeats == 1 and supervisor.trigger == ''
    assert supervisor.last_progress == initial  # 변화의 뜻은 감독기가 판단한다.


from test_conscious_supervisor import supervisor  # noqa: F401,E402

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
