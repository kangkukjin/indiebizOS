"""A submitted program survives a wait without retaining an HTTP worker."""
import boot_paths  # noqa: F401
import pytest
import task_receipts as T
import ibl_continuations as C
from ibl_v2_adapters import Adapter, decode_envelope
from ibl_v2_entry import handle_request


def test_completed_task_wakes_same_program_after_connection_is_gone(tmp_path, monkeypatch):
    import ibl_v2_adapters
    import ibl_v2_store
    import ibl_run_journal
    calls, state = [], {'done': False}
    monkeypatch.setattr(ibl_run_journal, 'runs_root', lambda: tmp_path / 'runs')
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    ref = T.ref('test_child', 'one')
    T.register('test_child', lambda r: T.view(r, T.SUCCEEDED if state['done'] else T.RUNNING, result=42))
    def wait(rt, args):
        raw = T.wait(ref, timeout=0, suspend=True)
        return decode_envelope(raw, {'protocol': 'legacy-envelope'}, args)[0]
    def adapter(fn, result='Record'):
        return Adapter({'version': 1, 'params': {}, 'result': result,
                        'effects': ['write_external'], 'implementation_fingerprint': 'one'}, fn)
    registry = {'t:start': adapter(lambda rt, a: calls.append('start') or {'ref': ref}),
                't:wait': adapter(wait), 't:publish': adapter(lambda rt, a: calls.append('publish') or {})}
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: registry)
    request = {'edition': 2, 'code': '$a=[t:start]{}\n$b=[t:wait]{}\n$c=[t:publish]{}\nreturn $b.result'}
    first = handle_request(request, str(tmp_path))
    assert first.get('suspended'), first
    C.sweep()
    assert calls == ['start']
    # No HTTP request is alive. The next worker only sees the durable journal.
    state['done'] = True
    C.sweep()
    result = C.task_status(first['task_ref'])
    assert result['state'] == T.SUCCEEDED and result['result'] == 42, result
    C.sweep()
    assert calls == ['start', 'publish']
    assert handle_request({**request, 'resume': first['resume']}, str(tmp_path))['success']
    assert calls == ['start', 'publish']


def test_suspending_wait_preserves_finite_wait_contract():
    T.register('wait-contract', lambda r: T.view(r, T.RUNNING))
    ref = T.ref('wait-contract', 'a')
    assert T.wait(ref, 0)['timed_out'] and T.wait(ref, 0)['success']
    assert T.wait(ref, 0, suspend=True)['suspended']


def test_cancelling_durable_wait_never_runs_following_effect(tmp_path, monkeypatch):
    import ibl_v2_adapters, ibl_v2_store, ibl_run_journal
    monkeypatch.setattr(ibl_run_journal, 'runs_root', lambda: tmp_path / 'runs')
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    T.register('still-running', lambda r: T.view(r, T.RUNNING))
    calls = []
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['write_external']}
    def wait(rt, args):
        return decode_envelope(T.wait(T.ref('still-running', 'one'), 0, suspend=True), {'protocol': 'legacy-envelope'}, args)[0]
    registry = {'t:wait': Adapter(contract, wait), 't:after': Adapter(contract, lambda rt,a: calls.append(1) or {})}
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: registry)
    first = handle_request({'edition': 2, 'code': '[t:wait]{}\n[t:after]{}'}, str(tmp_path))
    assert first.get('suspended'), first
    assert C.task_cancel(first['task_ref'])['state'] == T.CANCEL_REQUESTED
    C.sweep()
    assert C.task_status(first['task_ref'])['state'] == T.CANCELLED
    assert calls == []


def test_changed_definition_leaves_observable_failure_instead_of_stuck_wait(tmp_path, monkeypatch):
    import ibl_v2_adapters, ibl_v2_store, ibl_run_journal
    monkeypatch.setattr(ibl_run_journal, 'runs_root', lambda: tmp_path / 'runs')
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    T.register('ready-soon', lambda r: T.view(r, T.SUCCEEDED))
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['write_external'], 'implementation_fingerprint': 'one'}
    def wait(rt, args):
        from ibl_v2_ir import Fault
        raise Fault('TASK_PENDING', 'wait', kind='suspended', details={'task_ref': T.ref('ready-soon', 'x')})
    registry = {'t:wait': Adapter(contract, wait)}
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: registry)
    first = handle_request({'edition': 2, 'code': '[t:wait]{}'}, str(tmp_path))
    contract['implementation_fingerprint'] = 'two'
    C.sweep()
    assert C.task_status(first['task_ref'])['state'] == T.FAILED


def test_lost_child_is_reported_instead_of_waiting_forever(tmp_path, monkeypatch):
    import ibl_v2_adapters, ibl_v2_store, ibl_run_journal
    monkeypatch.setattr(ibl_run_journal, 'runs_root', lambda: tmp_path / 'runs')
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    state = {'value': T.RUNNING}
    T.register('may-disappear', lambda r: T.view(r, state['value']))
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['read_external'], 'per_run': True}
    def wait(rt, args):
        return decode_envelope(T.wait(T.ref('may-disappear', 'one'), 0, suspend=True), {'protocol': 'legacy-envelope'}, args)[0]
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {'t:wait': Adapter(contract, wait)})
    first = handle_request({'edition': 2, 'code': '[t:wait]{}'}, str(tmp_path))
    assert first.get('suspended'), first
    state['value'] = T.UNKNOWN
    C.sweep()
    assert C.task_status(first['task_ref'])['state'] == T.FAILED


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
