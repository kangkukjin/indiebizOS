"""Next-boundary steering preserves effect receipts, actor scope and parallel admission."""
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


def test_unknown_writes_parallel_writes_and_effectful_each_not_exposed(tmp_path):
    from ibl_v2_compile import compile_program
    from ibl_run_journal import Journal
    from ibl_run_control import publish
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']}, lambda *_: 1),
           't:read': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['pure']}, lambda *_: 1)}
    for code in ('[t:write]{}', '[t:write]{} & [t:read]{}', '[1,2] >> [table:each]{[t:write]{}}'):
        plan = compile_program(code, reg)
        with Journal(tmp_path / 'runs', 'test') as journal:
            publish(journal, plan, tmp_path)
            assert journal.control['targets'] == {}


@pytest.fixture
def launch(tmp_path, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def start(code, extra=None, inputs=None):
        entered, release = threading.Event(), threading.Event()
        handles, output, crashes = [], [], []
        def gate(rt, args):
            handles.append(rt.journal.control['task_ref'])
            entered.set()
            assert release.wait(15)
            return 2
        reg = {'t:gate': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                                  'effects': ['read_external']}, gate), **(extra or {})}
        monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
        monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
        monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
        request = {'edition': 2, 'code': code, 'inputs': inputs or {}}
        context = snapshot()
        def run():
            restore(context)
            try:
                output.append(handle_request(request, str(tmp_path)))
            except BaseException as exc:
                crashes.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert entered.wait(8), (output, crashes)
            yield handles[0], output, release, worker, request, crashes
        finally:
            release.set()
            worker.join(15)
            assert not worker.is_alive()
    return start


def change(ref, action, expected, updates, *, occurrence=-1):
    progress = status(ref)['progress']
    target = [r for r in progress['boundaries'] if r['action'] == action][occurrence]
    return {'root_task': progress['root_task'], 'plan_hash': progress['plan_hash'],
            'node_id': target['node_id'], 'revision': target['revision'], 'ordinal': target['next_ordinal'],
            'expected_args_hash': digest(expected), 'changes': updates}


def writer(run):
    return Adapter({'version': 1, 'params': {'path': 'Text', 'content': 'Text'}, 'result': 'Text',
                    'effects': ['write_external'], 'write_resources': {'file': 'path'}}, run)


def test_unstarted_write_changes_content_and_resume_never_repeats_completed_effects(launch, tmp_path):
    calls = []
    def write(rt, args):
        calls.append(dict(args))
        Path(args['path']).write_text(args['content'])
        return args['content']
    first, second = str(tmp_path / 'first'), str(tmp_path / 'second')
    code = '[t:write]{path:$first,content:"kept"}; [t:gate]{}; return [t:write]{path:$second,content:"old"}'
    with launch(code, {'t:write': writer(write)}, {'first': first, 'second': second}) as (ref, out, release, worker, request, _):
        payload = change(ref, 't:write', {'path': second, 'content': 'old'}, {'content': 'new'})
        assert steer(ref, payload, 'edit')['delivery'] == 'accepted'
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == 'new', out
        assert [r['content'] for r in calls] == ['kept', 'new']
        state = status(ref)['progress']['requests'][0]
        assert state['state'] == 'applied' and state['effect_state'] == 'returned'
        assert state['call_ref']['run_id'] == ref['task_id']
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == 'new', resumed
        assert len(calls) == 2
        with pytest.raises(ValueError, match='이미 시작'):
            steer(ref, payload, 'new-id-cannot-rewrite-history')
        assert steer(ref, payload, 'edit')['delivery'] == 'applied'


def test_write_target_change_rejected_without_redirecting_effect(launch, tmp_path):
    calls = []
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        return args['content']
    path, other = str(tmp_path / 'original'), str(tmp_path / 'other')
    with launch('[t:gate]{}; [t:write]{path:$path,content:"original"}', {'t:write': writer(write)},
                {'path': path}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': path, 'content': 'original'}, {'path': other}), 'redirect')
        release.set(); worker.join(10)
        assert out[0]['success'] and Path(path).read_text() == 'original'
        assert not Path(other).exists() and len(calls) == 1
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'write_resource_changed_or_unknown'


def test_crash_after_write_keeps_unknown_effect_and_resume_does_not_resend(launch, tmp_path):
    class LostWorker(BaseException):
        pass
    calls = []
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        raise LostWorker()
    path = str(tmp_path / 'effect')
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': path}) as (ref, out, release, worker, request, crashes):
        payload = change(ref, 't:write', {'path': path, 'content': 'old'}, {'content': 'new'})
        steer(ref, payload, 'change')
        release.set(); worker.join(10)
        assert crashes and not out and Path(path).read_text() == 'new'
        row = status(ref)['progress']['requests'][0]
        assert row['effect_state'] == 'unknown'
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['diagnostic']['code'] == 'EFFECT_UNCERTAIN', resumed
        assert len(calls) == 1
        with pytest.raises(ValueError, match='이미 시작'):
            steer(ref, payload, 'retry-not-authorized')


def test_parallel_read_branch_changes_without_repeating_other_branch(launch, tmp_path):
    calls = []
    reader = Adapter({'version': 1, 'params': {'n': 'Number'}, 'pipe_input': 'n',
                      'result': 'Number', 'effects': ['read_external']}, lambda rt, args: calls.append(args['n']) or args['n'])
    with launch('([t:gate]{} >> [t:read]{}) & [t:read]{n:3}', {'t:read': reader}) as (ref, out, release, worker, request, _):
        payload = change(ref, 't:read', {'n': 2}, {'n': 7}, occurrence=0)
        steer(ref, payload, 'one-branch')
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [7, 3], out
        assert sorted(calls) == [3, 7]
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == [7, 3], resumed
        assert sorted(calls) == [3, 7]


def test_shared_function_in_parallel_requires_a_live_scope(tmp_path):
    from ibl_v2_compile import compile_program
    from ibl_run_journal import Journal
    from ibl_run_control import publish, boundaries
    reg = {'t:read': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}, lambda *_: 1)}
    plan = compile_program('[def:read](){return [t:read]{}}; [fn:read]{} & [fn:read]{}', reg)
    assert not plan.issues
    with Journal(tmp_path / 'runs', 'test') as journal:
        publish(journal, plan, tmp_path)
        assert journal.control['targets']
        assert all(t['addressing'] == 'scope' for t in journal.control['targets'].values())
        assert boundaries(journal.db, journal.control) == []


def test_cancel_before_write_boundary_preserves_original_file(launch, tmp_path):
    path = tmp_path / 'cancelled'
    path.write_text('kept')
    def write(rt, args):
        pytest.fail('cancelled write must never start')
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': str(path)}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': str(path), 'content': 'old'}, {'content': 'new'}), 'edit')
        assert cancel(ref)['state'] == 'cancel_requested'
        release.set(); worker.join(10)
        assert not out[0]['success'] and path.read_text() == 'kept'
        assert status(ref)['progress']['requests'][0]['state'] == 'not_applied'


def test_late_cancel_preserves_returned_write_receipt(launch, tmp_path):
    entered, finish = threading.Event(), threading.Event()
    calls = []
    path = str(tmp_path / 'late')
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        entered.set()
        assert finish.wait(10)
        return args['content']
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': path}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:write', {'path': path, 'content': 'old'}, {'content': 'new'}), 'edit')
        try:
            release.set()
            assert entered.wait(5)
            assert cancel(ref)['state'] == 'cancel_requested'
        finally:
            finish.set()
        worker.join(10)
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'
        assert Path(path).read_text() == 'new' and len(calls) == 1
        handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert len(calls) == 1


def test_steered_write_still_checks_adapter_source_revision(launch, tmp_path):
    from ibl_v2_ir import Fault
    path = tmp_path / 'revision'
    path.write_text('original')
    expected = digest('original')
    calls = []
    def write(rt, args):
        if digest(Path(args['path']).read_text()) != args['expected']:
            raise Fault('SOURCE_CHANGED', '원문 판본이 달라졌습니다')
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        return args['content']
    adapter = writer(write)
    adapter.contract['params']['expected'] = 'Text'
    values = {'path': str(path), 'content': 'old', 'expected': expected}
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old",expected:$expected}',
                {'t:write': adapter}, {'path': str(path), 'expected': expected}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', values, {'content': 'new'}), 'edit')
        path.write_text('external update')
        release.set(); worker.join(10)
        assert out[0]['diagnostic']['code'] == 'SOURCE_CHANGED', out
        assert not calls and path.read_text() == 'external update'


@pytest.mark.parametrize('code', [
    '[t:write]{path:"a",content:"x"} & [t:write]{path:"b",content:"y"}',
    '[table:each]{items:["a","b"]}{[t:write]{path:$it,content:"x"}}',
    '[table:each]{items:["a","b"],parallel:2}{[t:write]{path:$it,content:"x"}}',
])
def test_parallel_or_each_with_declared_write_resource_is_not_steerable(tmp_path, code):
    from ibl_v2_compile import compile_program
    from ibl_run_journal import Journal
    from ibl_run_control import publish
    plan = compile_program(code, {'t:write': writer(lambda rt, args: args['content'])})
    assert not plan.issues
    with Journal(tmp_path / 'runs', 'test') as journal:
        publish(journal, plan, tmp_path)
        assert not journal.control['targets']


@pytest.fixture
def scoped_run(tmp_path, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def start(code, wait_for=(10, 20)):
        entered = {n: threading.Event() for n in (10, 20)}
        release = {n: threading.Event() for n in entered}
        entered['read_twenty'] = threading.Event()
        handles, calls, output, crashes = {}, [], [], []
        def gate(rt, args):
            n = args['n']
            handles[n] = (rt.journal.control['task_ref'], rt.local.control_scope[0])
            entered[n].set()
            assert release[n].wait(15)
            return n
        contract = {'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['read_external'], 'pipe_input': 'n'}
        def read(rt, args):
            calls.append(args['n'])
            if args['n'] == 20:
                entered['read_twenty'].set()
            return args['n']
        reg = {'t:gate': Adapter(contract, gate),
               't:read': Adapter(dict(contract), read)}
        monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
        monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
        monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
        request = {'edition': 2, 'code': code}
        context = snapshot()
        def run():
            restore(context)
            try:
                output.append(handle_request(request, str(tmp_path)))
            except BaseException as exc:
                crashes.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            for n in wait_for:
                assert entered[n].wait(5), (output, crashes)
            yield handles, entered, release, calls, output, worker, request
        finally:
            for event in release.values():
                event.set()
            worker.join(15)
            assert not worker.is_alive() and not crashes, crashes
    return start


def scoped_change(handles, n, *, action='t:read', changes=None):
    ref, scope_id = handles[n]
    progress = status(ref)['progress']
    target = next(row for row in progress['boundaries'] if row.get('scope') == scope_id and row['action'] == action)
    return {'root_task': progress['root_task'], 'plan_hash': progress['plan_hash'],
            'node_id': target['node_id'], 'revision': target['revision'], 'ordinal': target['next_ordinal'],
            'scope': scope_id, 'expected_args_hash': digest({'n': n}), 'changes': changes or {'n': 99}}


@pytest.mark.parametrize('code', [
    '[table:each]{items:[10,20],parallel:2}{[t:gate]{n:$it};[t:read]{n:$it}}',
    '[def:work]($n){[t:gate]{n:$n};return [t:read]{n:$n}}; [fn:work]{n:10} & [fn:work]{n:20}',
    '$f=($n)=>([t:gate]{n:$n} >> [t:read]{}); return $f{n:10} & $f{n:20}',
    '[def:work]($n){[t:gate]{n:$n};return [t:read]{n:$n}}; '
    '[table:each]{items:[10,20],parallel:2}{[fn:work]{n:$it}}',
])
def test_scoped_read_changes_only_one_activation_and_resume_reuses_both(scoped_run, tmp_path, code):
    with scoped_run(code) as (handles, entered, release, calls, out, worker, request):
        ref, selected_scope = handles[10]
        payload = scoped_change(handles, 10)
        other = scoped_change(handles, 20)
        assert payload['node_id'] == other['node_id'] and selected_scope != other['scope']
        with pytest.raises(ValueError, match='scope'):
            steer(ref, {k: v for k, v in payload.items() if k != 'scope'}, 'ambiguous')
        with pytest.raises(ValueError, match='scope'):
            steer(ref, {**payload, 'scope': 'foreign-scope'}, 'forged')
        assert steer(ref, payload, 'only-ten')['delivery'] == 'accepted'
        assert steer(ref, payload, 'only-ten')['delivery'] == 'accepted'
        release[20].set()  # Completion order must not select the target.
        assert entered['read_twenty'].wait(5)
        release[10].set()
        worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [99, 20], out
        assert sorted(calls) == [20, 99]
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == [99, 20], resumed
        assert sorted(calls) == [20, 99]
        assert steer(ref, payload, 'only-ten')['delivery'] == 'applied'
        with pytest.raises(ValueError, match='scope'):
            steer(ref, payload, 'closed-activation')


def test_each_scope_ends_before_next_sequential_item(scoped_run):
    code = '[table:each]{items:[10,20]}{[t:gate]{n:$it};[t:read]{n:$it}}'
    with scoped_run(code, wait_for=(10,)) as (handles, entered, release, calls, out, worker, _):
        ref = handles[10][0]
        old = scoped_change(handles, 10)
        release[10].set()
        assert entered[20].wait(5)
        with pytest.raises(ValueError, match='scope'):
            steer(ref, old, 'old-item')
        steer(ref, scoped_change(handles, 20), 'new-item')
        release[20].set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [10, 99], out


def test_wrong_scoped_input_does_not_spill_into_other_item(scoped_run):
    code = '[table:each]{items:[10,20],parallel:2}{[t:gate]{n:$it};[t:read]{n:$it}}'
    with scoped_run(code) as (handles, entered, release, calls, out, worker, _):
        ref = handles[10][0]
        ten, twenty = scoped_change(handles, 10), scoped_change(handles, 20)
        steer(ref, {**twenty, 'expected_args_hash': ten['expected_args_hash']}, 'stale')
        for event in release.values():
            event.set()
        worker.join(10)
        assert out[0]['value'] == [10, 20]
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'input_revision_mismatch'


def test_scoped_cancel_preserves_running_reads_and_drops_pending_changes(scoped_run):
    code = '[table:each]{items:[10,20],parallel:2}{[t:gate]{n:$it};[t:read]{n:$it}}'
    with scoped_run(code) as (handles, entered, release, calls, out, worker, _):
        ref = handles[10][0]
        payload = scoped_change(handles, 10)
        steer(ref, payload, 'cancelled')
        with pytest.raises(ValueError, match='이미 시작'):
            gate = scoped_change(handles, 10, action='t:gate')
            steer(ref, {**gate, 'ordinal': 1}, 'active')
        assert cancel(ref)['state'] == 'cancel_requested'
        for event in release.values():
            event.set()
        worker.join(10)
        assert not out[0]['success'] and not calls
        assert status(ref)['progress']['requests'][0]['state'] == 'not_applied'


def test_unreached_scoped_change_expires_at_frame_exit(scoped_run):
    code = '[table:each]{items:[10,20]}{[t:gate]{n:$it};[if:$it==20]{[t:read]{n:$it}}[else]{0}}'
    with scoped_run(code, wait_for=(10,)) as (handles, entered, release, calls, out, worker, _):
        ref = handles[10][0]
        steer(ref, scoped_change(handles, 10), 'unreached')
        release[10].set()
        assert entered[20].wait(5)
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'scope_closed'
        release[20].set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [0, 20], out
        assert calls == [20]


def test_legacy_node_address_survives_new_scope_capability_on_resume(launch, tmp_path, monkeypatch):
    import ibl_run_control as control
    from ibl_v2_repair_graph import walk
    original = control.publish
    def legacy_publish(journal, plan, project):
        ref = original(journal, plan, project)
        shared = {n.id for n in walk(plan.functions)}
        metadata = journal.control
        metadata.pop('scoped')
        metadata['targets'] = {n: t for n, t in metadata['targets'].items() if n not in shared}
        for target in metadata['targets'].values():
            target.pop('addressing')
        journal.db.execute('UPDATE control_meta SET data=?', (json.dumps(metadata),))
        journal.db.commit()
        return ref
    monkeypatch.setattr(control, 'publish', legacy_publish)
    reads = []
    reader = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                      'effects': ['read_external']}, lambda rt, args: reads.append(args['n']) or args['n'])
    code = '[def:unused](){return [t:read]{n:0}};[t:gate]{};[t:read]{n:2} & [t:read]{n:3}'
    with launch(code, {'t:read': reader}) as (ref, out, release, worker, request, _):
        payload = change(ref, 't:read', {'n': 2}, {'n': 7}, occurrence=0)
        steer(ref, payload, 'legacy')
        release.set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [7, 3], out
        monkeypatch.setattr(control, 'publish', original)
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == [7, 3], resumed
        assert sorted(reads) == [3, 7]
        assert steer(ref, payload, 'legacy')['delivery'] == 'applied'


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
