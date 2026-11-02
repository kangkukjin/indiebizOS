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
    target = status(ref)['progress']['boundaries'][-1]
    assert target['input_contract']['params'] == {'n': 'Number'}
    assert target['input_state'] == 'unresolved_until_boundary' and target['expected_args_hash'] is None
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


@pytest.mark.parametrize('shift', [0, 2])
def test_repair_after_steering_preserves_applied_read_and_request_history(running, shift):
    ref, payload, release, worker, output, observations, request, project = running
    steer(ref, payload, 'change')
    release.set(); worker.join(5)
    assert output[0]['success'], output
    for offset in (10, 20):
        code = '\n' * (offset * shift) + request['code'].replace('second:$second}', f'second:$second+{offset}}}')
        updated = {**request, 'code': code}
        repair = {'run_id': ref['task_id']}
        checked = handle_request({**updated, 'check': True, 'repair': repair}, str(project))
        assert checked['ok'], checked
        assert checked['repair']['inherited_controls'][0]['request_id'] == 'change'
        result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(project))
        assert result['success'] and result['value'] == {'first': 1, 'second': 7 + offset}, result
        resumed = handle_request({**updated, 'resume': repair}, str(project))
        assert resumed['success'] and resumed['value'] == result['value'], resumed
        assert observations == [1, 7]
        assert steer(ref, payload, 'change')['delivery'] == 'applied'
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'


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


def test_repair_cas_includes_applied_control_history(running):
    from ibl_run_control import connection
    ref, payload, release, worker, output, observations, request, project = running
    steer(ref, payload, 'change')
    release.set(); worker.join(5)
    assert output[0]['success']
    updated = {**request, 'code': '\n' + request['code']}
    repair = {'run_id': ref['task_id']}
    checked = handle_request({**updated, 'check': True, 'repair': repair}, str(project))
    assert checked['ok'], checked
    with connection(ref, True) as (db, _, _):
        db.execute('UPDATE control_requests SET payload=? WHERE request_id=?',
                   (json.dumps({**payload, 'changes': {'n': 9}}), 'change'))
    blocked = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(project))
    assert blocked['diagnostic']['code'] == 'REPAIR_CHANGED', blocked
    assert observations == [1, 7]


def test_legacy_pure_steering_without_certificate_rejects_repair(launch, tmp_path):
    from ibl_run_control import connection
    pure = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['pure']}, lambda rt, args: args['n'])
    with launch('[t:gate]{}; return [t:pure]{n:2}', {'t:pure': pure}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:pure', {'n': 2}, {'n': 7}), 'pure-edit')
        release.set(); worker.join(5)
        assert out[0]['success'] and out[0]['value'] == 7, out
        with connection(ref, True) as (db, _, _):
            db.execute('DROP TABLE control_pure_bindings')
        blocked = handle_request({**request, 'code': '\n' + request['code'], 'check': True,
                                  'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert blocked['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', blocked
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == 7, resumed


@pytest.mark.parametrize('effect', [False, True])
def test_pure_steering_repair_recomputes_and_preserves_external_effects(launch, tmp_path, effect):
    computations, effects = [], []
    pure = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['pure']}, lambda rt, args: computations.append(args['n']) or args['n'])
    send = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['write_external'], 'write_resources': {'delivery': 'n'}},
                   lambda rt, args: effects.append(args['n']) or args['n'])
    code = '[t:gate]{}; $v=[t:pure]{n:2}; ' + ('[t:send]{n:$v}; ' if effect else '') + 'return $v'
    with launch(code, {'t:pure': pure, 't:send': send}) as (ref, out, release, worker, request, _):
        payload = change(ref, 't:pure', {'n': 2}, {'n': 7})
        steer(ref, payload, 'pure-edit')
        release.set(); worker.join(5)
        assert out[0]['success'] and out[0]['value'] == 7, out
        for offset in (10, 20):
            updated = {**request, 'code': '\n' * offset + code.replace('return $v', f'return $v+{offset}')}
            repair = {'run_id': ref['task_id']}
            checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
            assert checked['ok'], checked.get('diagnostic', checked)
            assert checked['repair']['inherited_controls'][0]['mode'] == 'recompute_pure'
            result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
            assert result['success'] and result['value'] == 7 + offset, result
            resumed = handle_request({**updated, 'resume': repair}, str(tmp_path))
            assert resumed['success'] and resumed['value'] == result['value'], resumed
            assert steer(ref, payload, 'pure-edit')['delivery'] == 'applied'
        assert computations == [7] * 5
        assert effects == ([7] if effect else [])


@pytest.mark.parametrize('replacement', [
    '$input=3', '$input=2; $input=3',
])
def test_pure_steering_repair_rejects_changed_input_producers(launch, tmp_path, replacement):
    calls = []
    pure = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['pure']}, lambda rt, args: calls.append(args['n']) or args['n'])
    code = '[t:gate]{}; $input=2; $v=[t:pure]{n:$input}; return $v'
    with launch(code, {'t:pure': pure}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:pure', {'n': 2}, {'n': 7}), 'pure-edit')
        release.set(); worker.join(5)
        assert out[0]['success'], out
        checked = handle_request({**request, 'code': code.replace('$input=2', replacement),
                                  'check': True, 'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert checked['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', checked
        assert calls == [7]


@pytest.mark.parametrize('prefix,changed', [
    ('[def:input](){return 2};', '[def:input](){return 3};'),
    ('[def:input](){return 2};', '[def:input](){return 2};'),
])
def test_pure_steering_repair_rejects_changed_definition_or_condition(launch, tmp_path, prefix, changed):
    pure = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['pure']}, lambda rt, args: args['n'])
    body = '[t:gate]{}; [if:2>1]{$v=[t:pure]{n:[fn:input]{}}; return $v}[else]{return 0}'
    with launch(prefix + body, {'t:pure': pure}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:pure', {'n': 2}, {'n': 7}), 'pure-edit')
        release.set(); worker.join(5)
        assert out[0]['success'], out
        code = changed + (body.replace('2>1', '3>1') if prefix == changed else body)
        checked = handle_request({**request, 'code': code, 'check': True,
                                  'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert checked['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', checked


def test_pure_repair_does_not_freeze_unsteered_computations(launch, tmp_path):
    calls = []
    pure = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                    'effects': ['pure']}, lambda rt, args: calls.append(args['n']) or args['n'])
    code = '[t:gate]{}; $v=[t:pure]{n:2}; $other=[t:pure]{n:8}; return [$v,$other]'
    with launch(code, {'t:pure': pure}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:pure', {'n': 2}, {'n': 7}, occurrence=0), 'pure-edit')
        release.set(); worker.join(5)
        assert out[0]['value'] == [7, 8], out
        updated = {**request, 'code': code.replace('n:8', 'n:9')}
        repair = {'run_id': ref['task_id']}
        checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
        assert checked['ok'], checked
        result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
        assert result['success'] and result['value'] == [7, 9], result
        assert calls == [7, 8, 7, 9]


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


def test_sequential_write_retargets_once_and_preserves_prior_effects(launch, tmp_path):
    calls = []
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        return args['content']
    path, other, prior = (str(tmp_path / name) for name in ('original', 'other', 'prior'))
    Path(path).write_text('kept')
    code = '[t:write]{path:$prior,content:"earlier"};[t:gate]{};$v=[t:write]{path:$path,content:"original"};return $v'
    with launch(code, {'t:write': writer(write)}, {'path': path, 'prior': prior}) as (ref, out, release, worker, request, _):
        targets = [b for b in status(ref)['progress']['boundaries'] if b['action'] == 't:write']
        assert all(b['resource_policy'] == 'declared' for b in targets)
        payload = change(ref, 't:write', {'path': path, 'content': 'original'}, {'path': other})
        steer(ref, payload, 'redirect')
        release.set(); worker.join(10)
        assert out[0]['success'] and Path(path).read_text() == 'kept'
        assert Path(other).read_text() == 'original' and Path(prior).read_text() == 'earlier' and len(calls) == 2
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'
        resumed = handle_request({**request, 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == 'original' and len(calls) == 2, resumed
        with pytest.raises(ValueError, match='이미 시작'):
            steer(ref, payload, 'retarget-again')
        updated = {**request, 'code': '\n' + code.replace('return $v', 'return {content:$v}')}
        repair = {'run_id': ref['task_id']}
        checked = handle_request({**updated, 'repair': repair, 'check': True}, str(tmp_path))
        assert checked['ok'], checked
        repaired = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
        assert repaired['success'] and repaired['value'] == {'content': 'original'} and len(calls) == 2, repaired
        assert steer(ref, payload, 'redirect')['delivery'] == 'applied'


@pytest.mark.parametrize('field', ['path', 'source'])
def test_retarget_requires_known_read_and_write_resources(launch, tmp_path, field):
    from dataclasses import replace
    calls = []
    original, unknown = (str(tmp_path / n) for n in ('original', 'unknown'))
    adapter = writer(lambda rt, args: calls.append(dict(args)) or args['content'])
    adapter.contract['params']['source'] = 'Text'
    adapter.contract['read_resources'] = {'file': 'source'}
    adapter = replace(adapter, resource_identity=lambda realm, value: None if value == unknown else value)
    expected = {'path': original, 'source': original, 'content': 'old'}
    with launch('[t:gate]{};[t:write]{path:$path,source:$path,content:"old"}', {'t:write': adapter},
                {'path': original}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', expected, {field: unknown}), 'redirect')
        release.set(); worker.join(10)
        assert out[0]['success'] and calls == [expected], out
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'write_resource_changed_or_unknown'


@pytest.mark.parametrize('bare_before', [False, True])
def test_retarget_rejects_ambiguous_bare_output_names(launch, tmp_path, bare_before):
    calls = []
    before = 'original.txt' if bare_before else str(tmp_path / 'original')
    after = str(tmp_path / 'destination') if bare_before else 'destination.txt'
    adapter = writer(lambda rt, args: calls.append(dict(args)) or args['content'])
    with launch('[t:gate]{};[t:write]{path:$path,content:"old"}', {'t:write': adapter},
                {'path': before}) as (ref, out, release, worker, *_):
        expected = {'path': before, 'content': 'old'}
        steer(ref, change(ref, 't:write', expected, {'path': after}), 'redirect')
        release.set(); worker.join(10)
        assert out[0]['success'] and calls == [expected], out
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'write_resource_changed_or_unknown'


def test_unchanged_bare_output_keeps_legacy_content_steering(launch):
    calls = []
    adapter = writer(lambda rt, args: calls.append(dict(args)) or args['content'])
    with launch('[t:gate]{};[t:write]{path:"output.txt",content:"old"}', {'t:write': adapter}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': 'output.txt', 'content': 'old'}, {'content': 'new'}), 'edit')
        release.set(); worker.join(10)
        assert out[0]['success'] and calls == [{'path': 'output.txt', 'content': 'new'}], out
        assert status(ref)['progress']['requests'][0]['state'] == 'applied'


def test_retarget_does_not_bypass_adapter_permission(launch, tmp_path):
    from ibl_v2_ir import Fault
    old, forbidden = (str(tmp_path / n) for n in ('old', 'forbidden'))
    Path(old).write_text('kept')
    attempts = []
    def write(rt, args):
        attempts.append(args['path'])
        if args['path'] == forbidden:
            raise Fault('TARGET_DENIED', '허용되지 않은 쓰기 대상', kind='permission')
        pytest.fail('rejected retarget must not fall back to an original write')
    with launch('[t:gate]{};[t:write]{path:$path,content:"new"}', {'t:write': writer(write)},
                {'path': old}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': old, 'content': 'new'}, {'path': forbidden}), 'redirect')
        release.set(); worker.join(10)
        assert out[0]['diagnostic']['code'] == 'TARGET_DENIED', out
        assert attempts == [forbidden] and Path(old).read_text() == 'kept' and not Path(forbidden).exists()
        assert status(ref)['progress']['requests'][0]['state'] == 'applied'


@pytest.mark.parametrize('fresh_revision', [False, True])
def test_retarget_checks_destination_revision(launch, tmp_path, fresh_revision):
    from ibl_v2_ir import Fault
    old, destination = (tmp_path / n for n in ('old', 'destination'))
    old.write_text('old revision'); destination.write_text('destination revision')
    expected = digest(old.read_text())
    def write(rt, args):
        if digest(Path(args['path']).read_text()) != args['expected']:
            raise Fault('SOURCE_CHANGED', '대상 판본 불일치')
        Path(args['path']).write_text(args['content'])
        return args['content']
    adapter = writer(write)
    adapter.contract['params']['expected'] = 'Text'
    values = {'path': str(old), 'content': 'new', 'expected': expected}
    with launch('[t:gate]{};[t:write]{path:$path,content:"new",expected:$expected}', {'t:write': adapter},
                values) as (ref, out, release, worker, *_):
        changes = {'path': str(destination)}
        if fresh_revision:
            changes['expected'] = digest(destination.read_text())
        steer(ref, change(ref, 't:write', values, changes), 'redirect')
        release.set(); worker.join(10)
        assert old.read_text() == 'old revision'
        if fresh_revision:
            assert out[0]['success'] and destination.read_text() == 'new', out
        else:
            assert out[0]['diagnostic']['code'] == 'SOURCE_CHANGED' and destination.read_text() == 'destination revision', out


def test_retarget_invalidates_reads_of_actual_destination(launch, tmp_path):
    from ibl_run_control import connection
    original, destination = (str(tmp_path / n) for n in ('original', 'destination'))
    Path(original).write_text('kept'); Path(destination).write_text('before')
    read = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
                    'effects': ['read_external'], 'read_resources': {'file': 'path'}},
                   lambda rt, args: Path(args['path']).read_text())
    def write(rt, args):
        Path(args['path']).write_text(args['content'])
        return args['content']
    code = '$a=[t:read]{path:$original};$b=[t:read]{path:$destination};[t:gate]{};[t:write]{path:$original,content:"after"}'
    with launch(code, {'t:read': read, 't:write': writer(write)},
                {'original': original, 'destination': destination}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': original, 'content': 'after'}, {'path': destination}), 'redirect')
        release.set(); worker.join(10)
        assert out[0]['success'] and Path(original).read_text() == 'kept' and Path(destination).read_text() == 'after', out
        with connection(ref) as (db, _, _):
            rows = db.execute('SELECT resources,reusable,reuse_exclusion FROM calls WHERE json_extract(call_info,\'$.action\')=?', ('t:read',)).fetchall()
        by_path = {json.loads(resources)[0][1]: (reusable, json.loads(exclusion) if exclusion else None)
                   for resources, reusable, exclusion in rows}
        assert by_path[str(Path(original).resolve())] == (1, None)
        assert by_path[str(Path(destination).resolve())][0] == 0
        assert by_path[str(Path(destination).resolve())][1]['reason'] == 'overlapping_write'


@pytest.mark.parametrize('redirect', [False, True])
def test_crash_after_write_keeps_unknown_effect_and_resume_does_not_resend(launch, tmp_path, redirect):
    class LostWorker(BaseException):
        pass
    calls = []
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        raise LostWorker()
    path = str(tmp_path / 'effect')
    destination = str(tmp_path / 'redirected') if redirect else path
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': path}) as (ref, out, release, worker, request, crashes):
        payload = change(ref, 't:write', {'path': path, 'content': 'old'}, {'content': 'new', 'path': destination})
        steer(ref, payload, 'change')
        release.set(); worker.join(10)
        assert crashes and not out and Path(destination).read_text() == 'new'
        assert not redirect or not Path(path).exists()
        row = status(ref)['progress']['requests'][0]
        assert row['effect_state'] == 'unknown'
        checked = handle_request({**request, 'code': '\n' + request['code'], 'check': True,
                                  'repair': {'run_id': ref['task_id']}}, str(tmp_path))
        assert checked['diagnostic']['code'] == 'EFFECT_UNCERTAIN', checked
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


def test_unused_unknown_writer_does_not_hide_read_only_parallel_controls(tmp_path):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_run_journal import Journal
    from ibl_run_control import publish
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                              lambda *_: pytest.fail('unused function must not execute')),
           't:read': Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                              'effects': ['read_external']}, lambda rt, args: args['n'])}
    plan = compile_program('[def:unused](){return [t:write]{}};'
                           '[def:read]($n){return [t:read]{n:$n}}; [fn:read]{n:1} & [fn:read]{n:2}', reg)
    assert not plan.issues and plan.effects == {'read_external'}
    with Journal(tmp_path / 'runs', 'test') as journal:
        publish(journal, plan, tmp_path)
        assert journal.control['targets']
        assert all(t['action'] == 't:read' for t in journal.control['targets'].values())
        result = Runtime(plan, journal=journal).run()
        assert result['success'] and result['value'] == [1, 2], result
        assert journal.db.execute('SELECT COUNT(*) FROM control_scopes').fetchone()[0] == 2


@pytest.mark.parametrize('redirect', [False, True])
def test_cancel_before_write_boundary_preserves_original_file(launch, tmp_path, redirect):
    path = tmp_path / 'cancelled'
    path.write_text('kept')
    destination = tmp_path / 'other' if redirect else path
    def write(rt, args):
        pytest.fail('cancelled write must never start')
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': str(path)}) as (ref, out, release, worker, *_):
        steer(ref, change(ref, 't:write', {'path': str(path), 'content': 'old'},
                          {'content': 'new', 'path': str(destination)}), 'edit')
        assert cancel(ref)['state'] == 'cancel_requested'
        release.set(); worker.join(10)
        assert not out[0]['success'] and path.read_text() == 'kept'
        assert not redirect or not destination.exists()
        assert status(ref)['progress']['requests'][0]['state'] == 'not_applied'


@pytest.mark.parametrize('redirect', [False, True])
def test_late_cancel_preserves_returned_write_receipt(launch, tmp_path, redirect):
    entered, finish = threading.Event(), threading.Event()
    calls = []
    path = str(tmp_path / 'late')
    destination = str(tmp_path / 'redirected') if redirect else path
    def write(rt, args):
        calls.append(args)
        Path(args['path']).write_text(args['content'])
        entered.set()
        assert finish.wait(10)
        return args['content']
    with launch('[t:gate]{}; [t:write]{path:$path,content:"old"}', {'t:write': writer(write)},
                {'path': path}) as (ref, out, release, worker, request, _):
        steer(ref, change(ref, 't:write', {'path': path, 'content': 'old'},
                          {'content': 'new', 'path': destination}), 'edit')
        try:
            release.set()
            assert entered.wait(5)
            assert cancel(ref)['state'] == 'cancel_requested'
        finally:
            finish.set()
        worker.join(10)
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'
        assert Path(destination).read_text() == 'new' and len(calls) == 1
        assert not redirect or not Path(path).exists()
        assert not out[0]['success'] and out[0]['diagnostic']['code'] == 'CANCELLED'
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
def test_parallel_or_each_with_declared_write_resource_uses_scopes(tmp_path, code):
    from ibl_v2_compile import compile_program
    from ibl_run_journal import Journal
    from ibl_run_control import publish
    plan = compile_program(code, {'t:write': writer(lambda rt, args: args['content'])})
    assert not plan.issues
    with Journal(tmp_path / 'runs', 'test') as journal:
        publish(journal, plan, tmp_path)
        assert journal.control['targets']
        assert all(t['addressing'] == 'scope' and t['resource_policy'] == 'admitted'
                   for t in journal.control['targets'].values())


@pytest.fixture
def scoped_run(tmp_path, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def start(code, wait_for=(10, 20), *, read_effect='read_external'):
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
               't:read': Adapter({**contract, 'effects': [read_effect]}, read)}
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


@pytest.mark.parametrize('prefix,expression', [
    ('', '[table:each]{items:[10,20],parallel:2}{[t:gate]{n:$it};[t:read]{n:$it}}'),
    ('[def:work]($n){[t:gate]{n:$n};return [t:read]{n:$n}};', '[fn:work]{n:10} & [fn:work]{n:20}'),
    ('[def:work]($n){[t:gate]{n:$n};return [t:read]{n:$n}};',
     '[table:each]{items:[10,20],parallel:2}{[fn:work]{n:$it}}'),
])
def test_scoped_pure_repair_keeps_exact_activation(scoped_run, tmp_path, prefix, expression):
    code = prefix + '$values=(' + expression + '); return $values'
    with scoped_run(code, read_effect='pure') as (handles, entered, release, calls, out, worker, request):
        ref = handles[10][0]
        payload = scoped_change(handles, 10)
        steer(ref, payload, 'only-ten')
        release[20].set()
        assert entered['read_twenty'].wait(5)
        release[10].set(); worker.join(10)
        assert out[0]['success'] and out[0]['value'] == [99, 20], out
        for label in ('one', 'two'):
            updated = {**request, 'code': '\n' + code.replace('return $values', f'return {{items:$values,label:"{label}"}}')}
            repair = {'run_id': ref['task_id']}
            checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
            assert checked['ok'], checked.get('diagnostic', checked)
            result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
            assert result['success'] and result['value'] == {'items': [99, 20], 'label': label}, result
            resumed = handle_request({**updated, 'resume': repair}, str(tmp_path))
            assert resumed['success'] and resumed['value'] == result['value'], resumed
            assert steer(ref, payload, 'only-ten')['delivery'] == 'applied'
        assert sorted(calls) == [20] * 5 + [99] * 5


def test_pure_repair_can_change_containing_function_result(scoped_run, tmp_path):
    code = '[def:work]($n){[t:gate]{n:$n};$v=[t:read]{n:$n};return $v}; [fn:work]{n:10} & [fn:work]{n:20}'
    with scoped_run(code, read_effect='pure') as (handles, _, release, calls, out, worker, request):
        ref = handles[10][0]
        steer(ref, scoped_change(handles, 10), 'only-ten')
        for event in release.values():
            event.set()
        worker.join(10)
        assert out[0]['success'], out
        updated = {**request, 'code': code.replace('return $v}', 'return $v+1}')}
        repair = {'run_id': ref['task_id']}
        checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
        assert checked['ok'], checked.get('diagnostic', checked)
        result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
        assert result['success'] and result['value'] == [100, 21], result
        assert sorted(calls) == [20, 20, 99, 99]


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


@pytest.fixture
def write_run(tmp_path, monkeypatch):
    from contextlib import contextmanager
    class LostWorker(BaseException):
        pass
    @contextmanager
    def start(code, *, wait_for=('a', 'b'), crash=None, extras=None, hold_write=None):
        paths = {name: str(tmp_path / name) for name in ('a', 'b')}
        entered = {p: threading.Event() for p in paths.values()}
        release = {p: threading.Event() for p in paths.values()}
        done = {p: threading.Event() for p in paths.values()}
        handles, effects, output, crashes, depths = {}, [], [], [], []
        write_release = threading.Event()
        def gate(rt, args):
            path = args['path']
            handles[path] = (rt.journal.control['task_ref'], rt.local.control_scope[0])
            entered[path].set()
            assert release[path].wait(15)
            return path
        def write(rt, args):
            depths.append(len(getattr(rt.local, 'resource_admissions', ())))
            Path(args['path']).write_text(args['content'])
            effects.append(dict(args))
            if args['path'] in done:
                done[args['path']].set()
            if args['path'] == paths.get(crash):
                raise LostWorker()
            if args['path'] == paths.get(hold_write):
                assert write_release.wait(15)
            return args['content']
        adapter = writer(write)
        adapter.contract['pipe_input'] = 'path'
        reg = {'t:write': adapter,
               't:gate': Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
                                  'effects': ['read_external'], 'read_resources': {'file': 'path'}}, gate),
               **(extras or {})}
        monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
        monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
        monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
        request = {'edition': 2, 'code': code, 'inputs': paths}
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
            for name in wait_for:
                assert entered[paths[name]].wait(5), (output, crashes)
            yield {'paths': paths, 'handles': handles, 'release': release, 'done': done, 'entered': entered,
                   'effects': effects, 'out': output, 'crashes': crashes, 'worker': worker, 'request': request,
                   'depths': depths, 'write_release': write_release}
        finally:
            for event in release.values():
                event.set()
            write_release.set()
            worker.join(15)
            assert not worker.is_alive()
            assert not crashes or (crash and all(isinstance(exc, LostWorker) for exc in crashes)), crashes
    return start


def write_change(state, name='a', *, action='t:write', expected=None, changes=None):
    path = state['paths'][name]
    ref, scope_id = state['handles'][path]
    progress = status(ref)['progress']
    target = next(row for row in progress['boundaries'] if row.get('scope') == scope_id
                  and row['action'] == action and row['next_ordinal'] == 1)
    return {'root_task': progress['root_task'], 'plan_hash': progress['plan_hash'],
            'node_id': target['node_id'], 'revision': target['revision'], 'ordinal': target['next_ordinal'],
            'scope': scope_id, 'expected_args_hash': digest(expected or {'path': path, 'content': 'old'}),
            'changes': changes or {'content': 'new'}}


WRITE_EACH = '[table:each]{items:[$a,$b],parallel:2}{[t:gate]{path:$it};[t:write]{path:$it,content:"old"}}'


@pytest.mark.parametrize('prefix,body', [
    ('', WRITE_EACH),
    ('[def:work]($p){[t:gate]{path:$p};return [t:write]{path:$p,content:"old"}}; ',
     '[fn:work]{p:$a} & [fn:work]{p:$b}'),
])
def test_definition_repair_preserves_scoped_write_and_repeated_lineage(write_run, tmp_path, prefix, body):
    code = prefix + '[def:result]($v){return $v}; $out=(' + body + '); return [fn:result]{v:$out}'
    with write_run(code) as state:
        ref = state['handles'][state['paths']['a']][0]
        payload = write_change(state)
        steer(ref, payload, 'edit')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'], state['out']
        assert len(state['effects']) == 2
        before = status(ref)['progress']['requests'][0]['call_ref']
        for suffix in ('one', 'two'):
            updated = {**state['request'], 'code': '\n\n' + code.replace('return $v}', f'return {{values:$v,label:"{suffix}"}}}}')}
            repair = {'run_id': ref['task_id']}
            checked = handle_request({**updated, 'check': True, 'repair': repair}, str(tmp_path))
            assert checked['ok'], checked
            result = handle_request({**updated, 'repair': {**repair, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
            assert result['success'] and result['value'] == {'values': ['new', 'old'], 'label': suffix}, result
            resumed = handle_request({**updated, 'resume': repair}, str(tmp_path))
            assert resumed['success'] and resumed['value'] == result['value'], resumed
            assert len(state['effects']) == 2
            assert Path(state['paths']['a']).read_text() == 'new'
            row = status(ref)['progress']['requests'][0]
            assert row['state'] == 'applied' and row['effect_state'] == 'returned' and row['call_ref'] == before
            assert steer(ref, payload, 'edit')['delivery'] == 'applied'


@pytest.mark.parametrize('code,nested', [
    (WRITE_EACH, False),
    ('[def:work]($p){[t:gate]{path:$p};return [t:write]{path:$p,content:"old"}}; '
     '[fn:work]{p:$a} & [fn:work]{p:$b}', False),
    ('[def:work]($p){[t:gate]{path:$p};return [t:write]{path:$p,content:"old"}}; '
     '[table:each]{items:[$a,$b],parallel:2}{'
     '[fn:work]{p:$it} & [t:write]{path:$it+".aux",content:"aux"}}', True),
])
def test_parallel_write_changes_one_target_content_and_preserves_receipts(write_run, tmp_path, code, nested):
    with write_run(code) as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        state['release'][b].set()
        assert state['done'][b].wait(5)
        state['release'][a].set(); state['worker'].join(10)
        expected = [['new', 'aux'], ['old', 'aux']] if nested else ['new', 'old']
        assert state['out'][0]['success'] and state['out'][0]['value'] == expected, state['out']
        assert Path(a).read_text() == 'new' and Path(b).read_text() == 'old'
        assert len(state['effects']) == (4 if nested else 2)
        if nested:
            assert all(depth == 2 for depth in state['depths'])
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'applied' and row['effect_state'] == 'returned'
        resumed = handle_request({**state['request'], 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == expected, resumed
        assert len(state['effects']) == (4 if nested else 2)


def test_sequential_each_write_uses_per_item_scope(write_run):
    with write_run(WRITE_EACH.replace('parallel:2', 'parallel:1'), wait_for=('a',)) as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        state['release'][a].set()
        assert state['entered'][b].wait(5)
        state['release'][b].set(); state['worker'].join(10)
        assert state['out'][0]['success'] and state['out'][0]['value'] == ['new', 'old'], state['out']
        assert len(state['effects']) == 2 and state['depths'] == [0, 0]


def test_parallel_write_cannot_redirect_into_sibling_resource(write_run):
    with write_run(WRITE_EACH) as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state, changes={'path': b}), 'redirect')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'] and state['out'][0]['value'] == ['old', 'old']
        assert sorted(r['path'] for r in state['effects']) == sorted([a, b])
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'PARALLEL_RESOURCE_CHANGED'


def test_parallel_read_change_cannot_escape_admitted_branch(write_run):
    reads = []
    reader = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
                      'effects': ['read_external'], 'read_resources': {'file': 'path'}},
                     lambda rt, args: reads.append(args['path']) or 'old')
    code = '[table:each]{items:[$a,$b],parallel:2}{[t:gate]{path:$it};$v=[t:read]{path:$it};[t:write]{path:$it,content:$v}}'
    with write_run(code, extras={'t:read': reader}) as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state, action='t:read', expected={'path': a}, changes={'path': b}), 'redirect')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'] and sorted(reads) == sorted([a, b]), state['out']
        row = status(ref)['progress']['requests'][0]
        assert row['state'] == 'not_applied' and row['reason'] == 'PARALLEL_RESOURCE_CHANGED'


def test_parallel_write_crash_preserves_unknown_effect_and_other_branch_receipt(write_run, tmp_path):
    with write_run(WRITE_EACH, crash='a') as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        state['release'][b].set()
        assert state['done'][b].wait(5)
        state['release'][a].set(); state['worker'].join(10)
        assert state['crashes'] and not state['out']
        assert Path(a).read_text() == 'new' and Path(b).read_text() == 'old'
        assert status(ref)['progress']['requests'][0]['effect_state'] == 'unknown'
        resumed = handle_request({**state['request'], 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['diagnostic']['code'] == 'EFFECT_UNCERTAIN', resumed
        assert len(state['effects']) == 2


def test_parallel_write_cancel_before_boundary_produces_no_effect(write_run):
    with write_run(WRITE_EACH) as state:
        a = state['paths']['a']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        assert cancel(ref)['state'] == 'cancel_requested'
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert not state['out'][0]['success'] and not state['effects']
        assert status(ref)['progress']['requests'][0]['state'] == 'not_applied'


def test_parallel_late_cancel_keeps_written_effect_and_return_receipt(write_run, tmp_path):
    from ibl_v2_ir import unpack
    with write_run(WRITE_EACH, hold_write='a') as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        for event in state['release'].values():
            event.set()
        assert state['done'][a].wait(5) and state['done'][b].wait(5)
        assert cancel(ref)['state'] == 'cancel_requested'
        state['write_release'].set(); state['worker'].join(10)
        assert not state['out'][0]['success']
        assert unpack(state['out'][0]['partial_wire']['data']) == ['new', 'old']
        assert Path(a).read_text() == 'new' and Path(b).read_text() == 'old'
        assert status(ref)['progress']['requests'][0]['effect_state'] == 'returned'
        handle_request({**state['request'], 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert len(state['effects']) == 2


def test_parallel_earlier_writes_survive_steering_and_resume(write_run, tmp_path):
    code = '[def:work]($p){[t:write]{path:$p,content:"kept"};[t:gate]{path:$p};'
    code += 'return [t:write]{path:$p,content:"old"}};[fn:work]{p:$a} & [fn:work]{p:$b}'
    with write_run(code) as state:
        a = state['paths']['a']
        ref = state['handles'][a][0]
        steer(ref, write_change(state), 'edit')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'] and state['out'][0]['value'] == ['new', 'old'], state['out']
        assert sorted(r['content'] for r in state['effects']) == ['kept', 'kept', 'new', 'old']
        resumed = handle_request({**state['request'], 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'] and resumed['value'] == ['new', 'old'], resumed
        assert len(state['effects']) == 4




@pytest.mark.parametrize('parallel', [1, 2])
def test_each_write_retargets_within_own_admitted_resources(write_run, tmp_path, parallel):
    code = ('[table:each]{items:[$a,$b],parallel:' + str(parallel) + '}'
            '{[t:gate]{path:$it};[t:write]{path:$it,content:"first"};'
            '[t:write]{path:$it+".next",content:"last"}}')
    with write_run(code, wait_for=('a',) if parallel == 1 else ('a', 'b')) as state:
        a, b = state['paths']['a'], state['paths']['b']
        ref = state['handles'][a][0]
        payload = write_change(state, expected={'path': a, 'content': 'first'}, changes={'path': a + '.next'})
        steer(ref, payload, 'move')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'], state['out']
        assert not Path(a).exists()
        assert [r['content'] for r in state['effects'] if r['path'] == a + '.next'] == ['first', 'last']
        assert Path(b).read_text() == 'first'
        assert status(ref)['progress']['requests'][0]['state'] == 'applied'
        resumed = handle_request({**state['request'], 'resume': {'run_id': ref['task_id']}}, str(tmp_path))
        assert resumed['success'], resumed
        assert len(state['effects']) == 4


def test_sequential_each_can_retarget_new_declared_resource(write_run):
    with write_run(WRITE_EACH.replace('parallel:2', 'parallel:1'), wait_for=('a',)) as state:
        a = state['paths']['a']
        ref = state['handles'][a][0]
        steer(ref, write_change(state, changes={'path': a + '.new'}), 'new-target')
        for event in state['release'].values():
            event.set()
        state['worker'].join(10)
        assert state['out'][0]['success'], state['out']
        assert not Path(a).exists() and Path(a + '.new').read_text() == 'old'
        assert status(ref)['progress']['requests'][0]['state'] == 'applied'


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
