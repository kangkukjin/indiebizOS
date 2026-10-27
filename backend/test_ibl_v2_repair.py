import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter
from ibl_v2_entry import handle_request


@pytest.fixture
def execute(monkeypatch, tmp_path):
    calls = []
    adapter = Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number',
                       'effects': ['write_external'], 'write_resources': {'delivery': 'id'},
                       'implementation_fingerprint': 'test-v1'}, lambda rt, a: calls.append(a['id']) or 1)
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: {'t:send': adapter})
    monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    def run(code, **extra):
        return handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}, **extra}, str(tmp_path))
    return run, calls, adapter


ORIGINAL = '$sent=[t:send]{id:"delivery"}; return 10/$n'
EDITED = '$sent=[t:send]{id:"delivery"}; return 10/($n+1)'


def test_pure_tail_repair_inherits_without_repeating_effect(execute):
    run, calls, _ = execute
    first = run(ORIGINAL)
    assert not first['success'] and calls == ['delivery'], first
    handle = {'run_id': first['resume']['run_id']}
    checked = run(EDITED, check=True, repair=handle)
    assert checked['ok'], checked
    handle['plan_hash'] = checked['repair']['plan_hash']
    out = run(EDITED, repair=handle)
    assert out['success'], out
    assert out['value'] == 10 and calls == ['delivery']
    repeated = run(EDITED, repair=handle)
    assert repeated['success'] and calls == ['delivery'], repeated
    same = run(EDITED, resume={'run_id': first['resume']['run_id']})
    assert same['success'] and calls == ['delivery'], same


def test_whitespace_preserves_lineage_identity(execute):
    run, calls, _ = execute
    first = run(ORIGINAL)
    code = '\n  $sent = [t:send]{ id:"delivery" }; return 2'
    handle = {'run_id': first['resume']['run_id']}
    checked = run(code, repair=handle, check=True)
    assert checked['ok'], checked
    out = run(code, repair={**handle, 'plan_hash': checked['repair']['plan_hash']})
    assert out['success'] and calls == ['delivery'], out


@pytest.mark.parametrize('code', ['$sent=[t:send]{id:"other"}; return 1',
                                 '$other=[t:send]{id:"delivery"}; return 1',
                                 '$sent=[t:send]{id:"delivery"}; return [t:send]{id:"delivery"}'])
def test_changed_intent_is_not_guessed(execute, code):
    run, calls, _ = execute
    first = run(ORIGINAL)
    out = run(code, check=True, repair={'run_id': first['resume']['run_id']})
    assert not out.get('ok') and not out.get('success'), out
    assert calls == ['delivery']


def test_repair_requires_exact_reviewed_plan(execute):
    run, calls, _ = execute
    first = run(ORIGINAL)
    out = run(EDITED, repair={'run_id': first['resume']['run_id'], 'plan_hash': 'stale'})
    assert not out.get('success'), out
    assert calls == ['delivery']


def test_changed_implementation_cannot_inherit(execute):
    run, calls, adapter = execute
    first = run(ORIGINAL)
    adapter.contract['implementation_fingerprint'] = 'test-v2'
    out = run(EDITED, check=True, repair={'run_id': first['resume']['run_id']})
    assert not out.get('ok') and calls == ['delivery'], out


def test_wrapped_effect_and_repeat_preserve_operation_identity(execute):
    run, calls, _ = execute
    prefix = '[def:send]($id){return [t:send]{id:$id}}; [repeat:2]{[fn:send]{id:"delivery"}}; '
    first = run(prefix + 'return 1/$n')
    assert len(calls) == 2
    handle = {'run_id': first['resume']['run_id']}
    code = '\n\n' + prefix + 'return 1'
    checked = run(code, check=True, repair=handle)
    assert checked['ok'], checked
    out = run(code, repair={**handle, 'plan_hash': checked['repair']['plan_hash']})
    assert out['success'] and len(calls) == 2, out


@pytest.mark.parametrize('domain', ['publication', 'device'])
def test_whole_observe_decide_act_verify_repair(execute, domain):
    run, calls, _ = execute
    prefix = f'[def:decide]($x,$p){{[if:$p($x)]{{return $x}}[else]{{return 0}}}}; '
    prefix += f'$chosen=[fn:decide]{{x:1,p:($v)=>$v>0}}; $done=[t:send]{{id:"{domain}"}}; '
    obligations = [{'id': domain, 'predicate': '$value == 1',
                    'sources': [{'action': 't:send', 'targets': {'id': domain}}]}]
    first = run(prefix + 'return $done/$n', completion=obligations)
    code = prefix + 'return $done/($n+1)'
    handle = {'run_id': first['resume']['run_id']}
    checked = run(code, completion=obligations, repair=handle, check=True)
    assert checked['ok'], checked
    out = run(code, completion=obligations, repair={**handle, 'plan_hash': checked['repair']['plan_hash']})
    assert out['success'] and out['completion']['status'] == 'satisfied', out
    assert calls == [domain]


@pytest.mark.parametrize('policy', [{'composition': 'ibl-composition/1'},
    {'completion': [{'id': 'delivery', 'predicate': '$value == 10',
                     'sources': [{'action': 't:send', 'targets': {'id': 'delivery'}}]}]}])
def test_resume_cannot_change_completion_or_composition_policy(execute, policy):
    run, calls, _ = execute
    first = run(EDITED, **policy)
    assert first['success']
    resumed = run(EDITED, resume=first['resume'])
    assert not resumed['success'] and resumed['diagnostic']['code'] == 'RESUME_CHANGED', resumed
    assert calls == ['delivery']


def test_uncertain_effect_and_busy_lineage_do_not_retry(execute):
    import sqlite3
    from filelock import FileLock
    from ibl_run_journal import journal_root
    run, calls, _ = execute
    first = run(ORIGINAL)
    handle = first['resume']
    path = journal_root(first['task_ref']['owner']) / (handle['run_id'] + '.sqlite')
    with FileLock(str(path) + '.lock', timeout=0):
        blocked = run(EDITED, check=True, repair=handle)
    assert blocked['diagnostic']['code'] == 'RESUME_BUSY', blocked
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('UPDATE calls SET receipt=NULL')
    blocked = run(EDITED, check=True, repair=handle)
    assert blocked['diagnostic']['code'] == 'EFFECT_UNCERTAIN', blocked
    assert calls == ['delivery']


def test_repaired_continuation_retains_new_source(execute):
    import json
    import sqlite3
    from ibl_run_journal import journal_root
    from ibl_v2_ir import unpack
    run, calls, _ = execute
    first = run(ORIGINAL)
    handle = first['resume']
    checked = run(EDITED, check=True, repair=handle)
    out = run(EDITED, repair={**handle, 'plan_hash': checked['repair']['plan_hash']})
    path = journal_root(out['task_ref']['owner']) / (handle['run_id'] + '.sqlite')
    with sqlite3.connect(path, timeout=10) as db:
        saved = json.loads(db.execute('SELECT request FROM continuation').fetchone()[0])
    request = unpack(saved['request'])
    assert request['code'] == EDITED and 'repair' not in request and calls == ['delivery']


def test_checked_handle_carries_exact_repair_plan(execute, monkeypatch, tmp_path):
    import json
    from system_tools_ibl import _offer_checked_code, _resolve_checked_code
    from supervision_store import TurnStore
    import model_result_view
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: store)
    run, calls, _ = execute
    first = run(ORIGINAL)
    handle = first['resume']
    checked = run(EDITED, check=True, repair=handle)
    _offer_checked_code(checked, EDITED, {'repair': handle})
    request, error = _resolve_checked_code(checked['execute_args'])
    assert not error and request['repair']['plan_hash'] == checked['repair']['plan_hash']
    assert run(request['code'], repair=request['repair'])['success']
    assert calls == ['delivery']


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
