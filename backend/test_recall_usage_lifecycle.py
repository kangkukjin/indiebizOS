"""Turn observations survive absent distillation; late events join without double counting."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import associative_recall as ar
from test_episode4169_recall import journal  # noqa: F401
from test_episode3388_repairs import isolated, Runner  # noqa: F401


def report_module():
    spec = importlib.util.spec_from_file_location('recall_report_test',
        Path(__file__).parents[1] / 'scripts/recall_usage_report.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(kind, blocks, **extra):
    return {'run_id': 'run', 'episode_id': 1, 'kind': 'recall.' + kind,
            'data': json.dumps({'blocks': blocks, **extra})}


@pytest.mark.parametrize('completed', [True, False])
def test_turn_observation_needs_no_response_or_distiller(monkeypatch, completed):
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda k, d: events.append((k, d)))
    recall = ar.Recall(ar.RecallRequest(None, 'request', []))
    recall.blocks.append(ar.Block('hippocampus', 'execution_memory', 'x', ids=['1'],
        join={'items': [{'id': '1', 'alias': '재사용', 'code': '$return = $목록'}]}))
    recall.finish(tool_calls=[{'tool_name': 'execute_ibl', 'input': {'edition': 2,
        'code': '[fn:재사용]{목록:[]}'}}], completed=completed)
    kind, data = events[-1]
    assert kind == 'recall.used' and data['phase'] == 'turn'
    assert data['completed'] is completed
    assert data['blocks'][0]['used'] == ['1']
    assert data['blocks'][0]['recall_id'] == recall.recall_id


def test_report_separates_missing_and_merges_late_confirmation():
    p = {'source': 'recalled_memory', 'ids': ['1', '2']}
    used = {'source': 'recalled_memory', 'presented': ['1', '2'], 'used': ['1'],
            'recall_id': 'a', 'evidence': 'expanded'}
    rows = [event('presented', [p], recall_id='a', channel='pipeline'),
            event('used', [used], phase='turn'),
            event('used', [{**used, 'used': ['2'], 'evidence': 'confirmed'}], phase='distill'),
            event('used', [used], phase='turn'),
            event('presented', [p], recall_id='missing', channel='pipeline'),
            event('presented', [p], recall_id='preview', channel='preview')]
    groups = report_module().summarize(rows)
    assert len(groups) == 2
    assert groups[0]['measured'] and groups[0]['used'] == {'1', '2'}
    assert groups[0]['evidence'] == {'expanded', 'confirmed'}
    assert not groups[1]['measured']


def test_legacy_report_and_interpreter_error_do_not_mean_unused():
    p = {'source': 'hippocampus', 'ids': ['1']}
    u = {'source': 'hippocampus', 'presented': ['1'], 'used': []}
    rows = [event('presented', [p]), event('used', [{**u, 'evidence': 'error'}]),
            event('presented', [p]), event('used', [u])]
    groups = report_module().summarize(rows)
    assert [g['measured'] for g in groups] == [False, True]


def test_check_only_and_unfinished_calls_are_not_execution_evidence():
    call = {'tool_name': 'execute_ibl', 'input': {'edition': 2, 'code': '[fn:재사용]{}'}}
    assert ar._ibl_codes([{**call, '_t0': 1},
        {**call, 'input': {**call['input'], 'check': True}}]) == []


@pytest.mark.parametrize('fails', [False, True])
def test_pipeline_persists_usage_before_distill_even_on_failure(tmp_path, monkeypatch, isolated, fails):
    import episode_logger as el
    monkeypatch.setattr(ar, '_run_phase', lambda *a, **kw: None)
    def associate(self, message, **kwargs):
        recall = ar.Recall(ar.RecallRequest(self, message, []))
        recall.blocks.append(ar.Block('world_memory', 'world_map', '<world_map>Library</world_map>',
            ids=['x'], join={'names': {'x': ['Library']}}))
        return recall
    monkeypatch.setattr(Runner, '_associate', associate)
    monkeypatch.setattr('consciousness_agent.get_consciousness_agent',
        lambda: SimpleNamespace(is_ready=False))
    def stream(**kwargs):
        if fails:
            raise RuntimeError('model unavailable')
        yield {'type': 'final', 'content': 'Library'}
    runner = Runner(tmp_path, stream)
    queued = []
    def after(*args, **kwargs):
        with el._get_db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM trajectory_event WHERE kind='recall.used'").fetchone()[0] == 1
        queued.append(kwargs)
    runner._after_response_async = after
    with el.trajectory_scope(task_id='recall-test'):
        list(runner.cognitive_stream('질문'))
    with el._get_db() as conn:
        events = conn.execute("SELECT data FROM trajectory_event WHERE kind='recall.used'").fetchall()
    assert len(events) == 1
    data = json.loads(events[0]['data'])
    assert data['phase'] == 'turn' and data['completed'] is not fails
    assert data['blocks'][0]['used'] == ([] if fails else ['x'])
    assert bool(queued) is not fails


def test_resumed_queue_records_original_episode_and_restores_context(journal):
    import episode_logger as el
    from distill_queue import DistillQueue, _Job
    from thread_context import set_current_task_id, get_current_task_id, clear_current_task_id
    def after(*args, **kwargs):
        ar.record_usage([{'source': 'world_memory', 'ids': ['x'], 'recall_id': 'recall',
                          'join': {'names': {'x': ['Library']}}}], response='Library')
    prior_task = get_current_task_id()
    try:
        with el.trajectory_scope(task_id='unrelated'):
            prior = el.current_trajectory_identity()
            DistillQueue._execute(_Job(1, SimpleNamespace(_after_response=after),
                {'episode_id': 2, 'response': 'done'}, {}))
            assert el.current_trajectory_identity() == prior
        conn = el._get_db()
        try:
            row = conn.execute("SELECT run_id,episode_id FROM trajectory_event WHERE kind='recall.used'").fetchone()
        finally:
            conn.close()
        assert tuple(row) == ('run-2', 2)
    finally:
        set_current_task_id(prior_task) if prior_task else clear_current_task_id()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
