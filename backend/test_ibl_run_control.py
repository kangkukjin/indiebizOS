"""Next-boundary steering cannot rewrite active calls, writes or another owner."""
import boot_paths  # noqa: F401
import json
import threading
from pathlib import Path

import pytest
from ibl_v2_adapters import Adapter
from ibl_v2_entry import handle_request
from ibl_v2_ir import digest
from ibl_run_control import status, steer, cancel
from thread_context import actor_context, snapshot, restore


@pytest.fixture(autouse=True)
def explicit_actor():
    # Exercise the actual non-default actor scope, even in a standalone run.
    with actor_context(agent_id='control-test-agent', task_id='control-test-task'):
        yield


@pytest.fixture
def running(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    observations, output, handles = [], [], []
    def read(rt, args):
        observations.append(args['n'])
        if args['n'] == 1:
            handles.append(rt.journal.control['task_ref'])
            entered.set()
            assert release.wait(10)
        return args['n']
    reg = {'t:read': Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                              'effects': ['read_external'], 'implementation_fingerprint': 'read-v1'}, read),
           't:write': Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                               'effects': ['write_external']}, lambda rt, a: observations.append('write') or a['n'])}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
    monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    request = {'edition': 2, 'code': '$first=[t:read]{n:1};$second=[t:read]{n:2};return {first:$first,second:$second}'}
    context = snapshot()
    def execute():
        restore(context)  # production offload uses this same context boundary
        output.append(handle_request(request, str(tmp_path)))
    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert entered.wait(5)
        ref = handles[0]
        observed = status(ref)
        assert observed['state'] == 'running', observed
        progress = observed['progress']
        assert progress['root_task'] == 'control-test-task'
        target = progress['boundaries'][-1]
        payload = {'root_task': progress['root_task'], 'plan_hash': progress['plan_hash'],
                   'node_id': target['node_id'], 'revision': target['revision'], 'ordinal': target['next_ordinal'],
                   'expected_args_hash': digest({'n': 2}), 'changes': {'n': 7}}
        yield ref, payload, release, worker, output, observations, request, tmp_path
    finally:
        release.set()
        worker.join(10)
        assert not worker.is_alive()


def test_next_read_changes_but_completed_read_and_resume_keep_values(running):
    ref, payload, release, worker, output, observations, request, project = running
    assert steer(ref, json.dumps(payload), 'change')['delivery'] == 'accepted'
    assert steer(ref, json.dumps(payload), 'change')['delivery'] == 'accepted'
    release.set(); worker.join(5)
    assert output[0]['success'], output
    assert output[0]['value'] == {'first': 1, 'second': 7}
    assert observations == [1, 7]
    assert steer(ref, json.dumps(payload), 'change')['delivery'] == 'applied'
    resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(project))
    assert resumed['success'] and resumed['value'] == output[0]['value'], resumed
    assert observations == [1, 7]  # neither read is executed again on receipt replay


def test_stale_input_and_duplicate_conflict_are_not_silently_applied(running):
    ref, payload, release, worker, output, observations, *_ = running
    wrong = {**payload, 'expected_args_hash': 'old'}
    assert steer(ref, wrong, 'change')['accepted']
    with pytest.raises(ValueError, match='같은 request_id'):
        steer(ref, payload, 'change')
    release.set(); worker.join(5)
    assert output[0]['value'] == {'first': 1, 'second': 2}
    row = status(ref)['progress']['requests'][0]
    assert row['state'] == 'not_applied' and row['reason'] == 'input_revision_mismatch'


def test_cancel_is_requested_and_pending_change_never_applies(running):
    ref, payload, release, worker, output, observations, *_ = running
    steer(ref, payload, 'change')
    assert cancel(ref)['state'] == 'cancel_requested'
    release.set(); worker.join(5)
    assert not output[0]['success'] and observations == [1]
    assert status(ref)['progress']['requests'][0]['state'] == 'not_applied'


def test_changed_definition_active_invocation_and_foreign_owner_rejected(running, monkeypatch):
    ref, payload, *_ = running
    with pytest.raises(ValueError, match='판본'):
        steer(ref, {**payload, 'revision': 'old'}, 'x')
    first = status(ref)['progress']['boundaries'][0]
    with pytest.raises(ValueError, match='이미 시작'):
        steer(ref, {**payload, 'node_id': first['node_id'], 'ordinal': 1}, 'active')
    monkeypatch.setattr('ibl_run_journal.receipt_access_scope', lambda: 'foreign')
    with pytest.raises(ValueError, match='소유'):
        steer(ref, payload, 'other')


def test_write_and_parallel_boundaries_not_exposed(tmp_path):
    from ibl_v2_compile import compile_program
    from ibl_run_journal import Journal
    from ibl_run_control import publish
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']}, lambda *_: 1),
           't:read': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['pure']}, lambda *_: 1)}
    for code in ('[t:write]{}', '[t:read]{} & [t:read]{}'):
        plan = compile_program(code, reg)
        with Journal(tmp_path / 'runs', 'test') as journal:
            publish(journal, plan, tmp_path)
            assert journal.control['targets'] == {}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
