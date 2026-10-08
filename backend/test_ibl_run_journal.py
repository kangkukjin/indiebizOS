"""Durable continuation contracts across approval and process boundaries."""
import boot_paths  # noqa: F401
import pytest
import approval_tokens
import action_requires
from ibl_v2_adapters import Adapter, decode_envelope
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_run_journal import Journal
from thread_context import get_approval, set_approval


def _plan(calls, source=None):
    def action(rt, args):
        denial = action_requires.gate('t', 'delete', {'requires': {'human_confirm': True}}, None, args)
        if denial:
            decode_envelope(denial, {'protocol': 'legacy-envelope'}, args)
        calls.append(args['id'])
        return args['id']
    def adapter(fn, params):
        return Adapter({'version': 1, 'params': params, 'result': 'Text',
                        'effects': ['write_external'], 'implementation_fingerprint': 'v1'}, fn)
    registry = {'t:delete': adapter(action, {'id': 'Text'}),
                't:delegate': adapter(lambda rt, a: calls.append('delegate') or 'child', {}),
                't:cleanup': adapter(lambda rt, a: calls.append('cleanup') or 'done', {})}
    return compile_program(source or '$x = [t:delegate]{}\n$a = [t:delete]{id:"A"}\n$b = [t:delete]{id:"B"}\nreturn [$x,$a,$b]', registry)


def _run(path, plan, resume=None, token=None):
    old = get_approval()
    try:
        set_approval(token, 'test-request')
        with Journal(path, plan.fingerprint, resume) as journal:
            return Runtime(plan, journal=journal).run()
    finally:
        set_approval(*old)


def test_two_approvals_preserve_completed_effects_and_retransmission(tmp_path):
    calls = []
    plan = _plan(calls)
    first = _run(tmp_path, plan)
    assert first['run_status'] == 'suspended' and calls == ['delegate']
    ask = first['waiting']['approval_required']
    token = approval_tokens.issue(ask['challenge'])['token']
    second = _run(tmp_path, plan, first['resume'], token)
    assert second['run_status'] == 'suspended' and calls == ['delegate', 'A']
    ask2 = second['waiting']['approval_required']
    assert ask['challenge'] != ask2['challenge']
    again = _run(tmp_path, plan, first['resume'], token)
    assert again['waiting']['approval_required']['challenge'] == ask2['challenge']
    assert calls == ['delegate', 'A']
    third = _run(tmp_path, plan, second['resume'], approval_tokens.issue(ask2['challenge'])['token'])
    assert third['success'] and calls == ['delegate', 'A', 'B']
    assert _run(tmp_path, plan, third['resume'])['success']
    assert calls == ['delegate', 'A', 'B']


def test_suspension_does_not_run_catch_or_finally(tmp_path):
    calls = []
    plan = _plan(calls, '[try]{[t:delete]{id:"A"}}[catch]{[t:cleanup]{}}[finally]{[t:cleanup]{}}')
    first = _run(tmp_path, plan)
    assert first['run_status'] == 'suspended' and calls == []
    token = approval_tokens.issue(first['waiting']['approval_required']['challenge'])['token']
    second = _run(tmp_path, plan, first['resume'], token)
    assert second['success'] and calls == ['A', 'cleanup']


def test_approval_cannot_move_to_a_new_run_and_uncertain_effect_is_not_retried(tmp_path):
    calls = []
    plan = _plan(calls)
    first = _run(tmp_path, plan)
    token = approval_tokens.issue(first['waiting']['approval_required']['challenge'])['token']
    other = _run(tmp_path, plan, token=token)
    assert other['suspended'] and calls == ['delegate', 'delegate']
    with Journal(tmp_path / 'uncertain', 'identity') as journal:
        resume = {'run_id': journal.run_id}
        journal.begin('effect', 'request')
    with Journal(tmp_path / 'uncertain', 'identity', resume) as journal:
        with pytest.raises(Exception, match='완료를 확인'):
            journal.begin('effect', 'request')


def test_same_size_same_mtime_source_change_invalidates_receipt(tmp_path):
    import os
    from ibl_run_journal import resource_state
    path = tmp_path / 'source.txt'
    path.write_bytes(b'AAAA')
    stat = path.stat()
    before = resource_state([['file', str(path), None]])
    path.write_bytes(b'BBBB')
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert resource_state([['file', str(path), None]]) != before


def test_assertion_keeps_predicate_and_criterion_separate_from_success(tmp_path):
    plan = compile_program('assert 2 == 2, "bad", {criterion_id:"C1",criterion_text:"합계 보존"}\nreturn 4', {})
    result = _run(tmp_path, plan)
    assert result['success'], result
    check = result['verification']['checks'][0]
    assert check['passed'] and check['criterion_id'] == 'C1'
    from final_evaluator import assertion_evidence
    rows = assertion_evidence(None, [{'result': result}], {'criteria': [{'id': 'C1', 'text': '합계 보존'}]})
    assert rows[0]['criterion_matches']
    changed = assertion_evidence(None, [{'result': result}], {'criteria': [{'id': 'C1', 'text': '새 기준'}]})
    assert not changed[0]['criterion_matches']


@pytest.mark.parametrize('source', [
    '[table:each]{items:["A","B"],parallel:2}{[t:delete]{id:$it}}',
    '[table:each]{items:["A","B"]}{[t:delete]{id:$it}}',
])
def test_each_invocation_has_own_approval_and_expired_grant_does_not_execute(tmp_path, monkeypatch, source):
    calls = []
    plan = _plan(calls, source)
    first = _run(tmp_path, plan)
    assert first.get('suspended'), first
    challenge = first['waiting']['approval_required']['challenge']
    token = approval_tokens.issue(challenge)['token']
    approval_tokens._TOKENS[token]['expires'] = 0
    first = _run(tmp_path, plan, first['resume'], token)
    assert calls == [] and first['suspended']
    for _ in range(2):
        token = approval_tokens.issue(first['waiting']['approval_required']['challenge'])['token']
        first = _run(tmp_path, plan, first['resume'], token)
    assert first['success'] and sorted(calls) == ['A', 'B'], first


def test_assertions_reject_saved_but_incorrect_content_and_detect_stale_source(tmp_path):
    from final_evaluator import assertion_evidence
    path = tmp_path / 'source'
    path.write_text('one')
    from ibl_run_journal import resource_state
    result = _run(tmp_path / 'run', compile_program('assert 1 == 1, "bad", {criterion_id:"C",criterion_text:"검사"}\nreturn 1', {}))
    result['verification']['source_snapshots'] = resource_state([['file', str(path), None]])
    path.write_text('two')
    evidence = assertion_evidence(None, [{'result': result}], {'criteria': [{'id': 'C', 'text': '검사'}]})[0]
    assert evidence['value_matches'] and not evidence['sources_unchanged']
    for condition in ('"a\\r\\nb" == "a\\nb"', 'len([1,1]) == len([1])'):
        out = Runtime(compile_program('assert '+condition+', "독립 검사 실패"', {})).run()
        assert not out['success'] and not out['verification']['checks'][0]['passed']


def test_content_change_with_preserved_metadata_forces_new_read_but_presentation_does_not(tmp_path):
    import os
    from test_imagination_round33_repairs import file_registry, _run as run_file
    path = tmp_path / 'rows.json'
    path.write_text('[{"n":1}]')
    code = f'$d=[t:read]{{path:"{path}"}}\nreturn $d.data[0].n'
    calls = []
    first_id, first = run_file(code, file_registry(calls), tmp_path)
    calls.clear()
    _, shown = run_file(code + ' + 0', file_registry(calls), tmp_path, first_id)
    assert shown['value'] == 1 and calls == []
    stamp = path.stat()
    path.write_text('[{"n":2}]')
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    _, changed = run_file(code + ' * 2', file_registry(calls), tmp_path, first_id)
    assert changed['value'] == 4 and len(calls) == 1 and changed['reuse']['reused_calls'] == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('during', [False, True])
def test_unknown_writer_exclusion_is_durable_and_located(tmp_path, during):
    from ibl_run_journal import reusable_receipts
    with Journal(tmp_path, 'test') as journal:
        run_id = journal.run_id
        if during:
            journal.begin('write', 'w', call_info={'action': 't:write', 'location': {'line': 7}})
        journal.begin('read', 'r', reusable=True, state_change=False, resources=[['file', '/input', None]])
        journal.finish('read', {'value': 'data', 'reuse_key': 'r'})
        if not during:
            journal.begin('write', 'w', call_info={'action': 't:write', 'location': {'line': 7}})
        journal.finish('write', {'value': 'ok'})
        summary = journal.reuse_summary()
        assert summary['read_calls'] == 0
        assert summary['read_exclusions'] == [{'reason': 'unknown_write_resources',
            'write_call_id': 'write', 'action': 't:write', 'location': {'line': 7}, 'excluded_calls': 1}]
    assert not reusable_receipts(tmp_path, run_id)
    with Journal(tmp_path, 'test', {'run_id': run_id}) as journal:
        assert journal.reuse_summary() == summary
