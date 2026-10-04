"""L15: portable failed arguments, complete recovery index and resume diagnostics."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

import pytest
from test_file_script import ibl, RESULT  # noqa: F401
from test_ibl_general_capabilities import boundary  # noqa: F401


def test_pure_computed_failed_script_arguments_recover_without_upstream(ibl, tmp_path, monkeypatch):
    from model_result_view import project_v2_result, resolve_input_refs, read_result
    from supervision_store import TurnStore
    from script_workspace import workspace
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr('model_result_view.evidence_store', lambda: store)
    bad = RESULT.replace('args = json.load(sys.stdin)', 'args = json.load(sys.stdin)\nraise ValueError("broken")')
    code = '''$f=[self:write]{path:"~turn/분석.py",content:$code}
$rows=[{n:2},{n:3}]
$total=reduce($rows,0,($acc,$r)=>$acc+$r.n)
return [self:script]{path:$f.path,args:{분석:{합계:$total,건수:len($rows)}}}'''
    failed = ibl(code, {'code': bad})
    assert not failed['success'] and failed['diagnostic']['code'] == 'SCRIPT_EXIT', failed
    projected = project_v2_result(failed)
    call = projected['result_ref']['failed_calls'][0]
    inputs, notes = resolve_input_refs(call['input_args'])
    assert inputs == {'입력': {'path': str(workspace() / '분석.py'), 'args': {'분석': {'합계': 5, '건수': 2}}}}
    assert call['source_complete'] is True  # the failed leaf does not taint its inputs
    assert read_result(call['read_args'])['read_scope']['complete']
    (workspace() / '분석.py').write_text(RESULT)
    recovered = ibl('return [self:script]{path:$입력.path,args:$입력.args}', inputs)
    assert recovered['success'] and recovered['value'] == {'분석': {'합계': 5, '건수': 2}}
    assert [r['action'] for r in recovered['recordings']] == ['self:script']


def test_recovery_index_keeps_omitted_calls_and_secret_boundary(boundary):
    from ibl_v2_ir import pack
    from model_result_view import project_v2_result, read_result, resolve_input_refs
    receipts = [{'action': 't:read', 'request_hash': str(i), 'value': pack({'n': i})} for i in range(9)]
    secret = 'sk-test-not-a-real-credential-12345678901234567890'
    receipts.append({'action': 't:fail', 'error': {}, 'arguments': pack({'api_key': secret}),
                     'argument_evidence': ['upstream']})
    result = project_v2_result({'edition': 2, 'success': False, 'diagnostic': {'code': 'FAIL'},
                               'recordings': receipts,
                               'evidence': [{'id': 'upstream', 'incomplete': True}]})
    refs = result['result_ref']
    assert len(refs['completed_calls']) == 6 and refs['completed_calls_omitted'] == 3
    index = json.loads(read_result(refs['calls_read_args'])['text'])
    last = index['completed_calls'][8]
    assert resolve_input_refs(last['input_args'])[0] == {'입력': {'n': 8}}
    failed = refs['failed_calls'][0]
    assert not failed['source_complete'] and 'input_args' not in failed
    assert 'input_unavailable' in failed
    assert secret not in json.dumps(result)
    with pytest.raises(ValueError, match='비밀'):
        resolve_input_refs({'x': {'$ref': failed['read_args']['id']}})


@pytest.mark.parametrize('field', ['args', 'invocation_dependency.source_hashes',
                                   'invocation_dependency.environment_fingerprint',
                                   'invocation_dependency.interpreter'])
def test_resume_reports_changed_dimension_without_executing(tmp_path, field):
    from ibl_run_journal import Journal, request_fingerprints
    from ibl_v2_ir import Fault, digest
    request = {'args': {'n': 2}, 'invocation_dependency': {'source_hashes': {'a.py': 'hash'},
               'environment_fingerprint': 'env', 'interpreter': 'python'}}
    before = request_fingerprints(request)
    with Journal(tmp_path, 'identity') as journal:
        run_id = journal.run_id
        journal.begin('call', digest(request), request_parts=before)
        journal.finish('call', {'value': 1})
    changed = json.loads(json.dumps(request))
    if '.' in field:
        changed['invocation_dependency'][field.split('.')[1]] = 'changed-secret-never-output'
    else:
        changed[field] = 'changed-secret-never-output'
    with Journal(tmp_path, 'identity', {'run_id': run_id}) as journal:
        with pytest.raises(Fault) as exc:
            journal.begin('call', digest(changed), request_parts=request_fingerprints(changed))
    assert exc.value.code == 'RESUME_DIVERGED'
    assert exc.value.details['changed'] == [field]
    assert exc.value.details['dimensions_known']
    assert 'changed-secret' not in json.dumps(exc.value.details)


def test_legacy_resume_and_uncertain_effect_stay_refused(tmp_path):
    from ibl_run_journal import Journal
    from ibl_v2_ir import Fault
    with Journal(tmp_path, 'identity') as journal:
        journal.begin('call', 'old')
        with pytest.raises(Fault) as exc:
            journal.begin('call', 'new', request_parts={'args': 'hash'})
        assert exc.value.code == 'RESUME_DIVERGED'
        assert exc.value.details['dimensions_known'] is False
        with pytest.raises(Fault) as exc:
            journal.begin('call', 'old')
        assert exc.value.code == 'EFFECT_UNCERTAIN'


@pytest.mark.parametrize('message, expected', [
    ('백엔드는 수정하지 말고 자료만 분석해 줘.', False),
    ('학원 보고서를 만들어 줘. 외부 발송이나 시스템 수정은 요청하지 않습니다.', False),
    ('시스템 수정은 필요 없습니다.', False),
    ('백엔드 수정 금지. 자료만 분석해 줘.', False),
    ('백엔드는 안 고쳐도 돼. 자료만 분석해 줘.', False),
    ('시스템을 고치지 마.', False),
    ('백엔드 수정 안 해도 돼.', False),
    ('"백엔드를 수정해 줘"라는 문장을 번역해 줘.', False),
    ('> 백엔드를 수정해 줘\n이 요청의 의미만 설명해 줘.', False),
    ('백엔드를 수정하면 무슨 일이 생기는지 설명해 줘.', False),
    ('백엔드를 고치면 어떤 영향이 있을까?', False),
    ("Don't fix the backend, just analyze the data.", False),
    ('What if we fix the backend?', False),
    ('백엔드를 수정해 줘.', True),
    ('api.py 버그를 고쳐 줘.', True),
    ('"백엔드"를 수정해 줘.', True),
    ('`api.py`를 수정해 줘.', True),
    ('Please fix the backend.', True),
    ('백엔드는 수정하지 말고 프론트엔드를 고쳐 줘.', True),
    ('"백엔드 수정 금지"는 옛 조건이야. 이제 백엔드를 수정해 줘.', True),
    ('자료를 분석해 줘.', False),
])
def test_repair_cue_distinguishes_request_from_mention(message, expected):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    assert CognitiveConsciousnessMixin()._is_repair_cue(message) is expected


def test_explicit_repair_tag_still_wins():
    from cognitive_consciousness import CognitiveConsciousnessMixin
    assert CognitiveConsciousnessMixin()._decide_request_type('#repair 백엔드는 수정하지 마', 0, '') == ('REPAIR', None)


@pytest.mark.system  # 2026-10-04: 전체 재생·전수 스캔은 system 묶음(docs/REGRESSION_TESTING.md 표)
def test_original_round15_full_program_recovers_without_recollecting(tmp_path, monkeypatch):
    """Original 200-line composition, with only the model leaf replaced by a deterministic double."""
    from dataclasses import replace
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    from script_workspace import request_scope, workspace
    from supervision_store import TurnStore
    from model_result_view import project_v2_result, resolve_input_refs
    root = Path(__file__).resolve().parents[1]
    source = root / 'docs/experiments/long_sentence_imagination/round_15/drafts'
    code = (source / 'full_failure_v0.ibl').read_text()
    render = (source / 'render_v1.py').read_text()
    registry = load_registry(str(root))
    model_calls = []
    def judge(runtime, args):
        model_calls.append(args)
        return {'items': [{**row, 'judgment_result_value': None, 'judgment_result_confidence': 0}
                          for row in args['items']]}
    registry['table:judge'] = replace(registry['table:judge'], run=judge)
    monkeypatch.setattr('script_workspace.storage_root', lambda: tmp_path / 'transient')
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr('model_result_view.evidence_store', lambda: store)
    def run(program, values):
        plan = compile_program(program, registry, values)
        assert not plan.issues, plan.report()
        return Runtime(plan, values, budget=Budget(steps=1000000, rows=100000)).run()
    with request_scope(root, 'round15-full-regression'):
        inputs = {'폴더': str(root / 'docs/experiments/long_sentence_imagination/round_10/input_09'),
                  '본문': render.replace('args["분석"]', 'args["분서"]'),
                  '태그': '검증, 전체', '출력': str(tmp_path / 'recovered')}
        failed = run(code, inputs)
        assert not failed['success'] and failed['diagnostic']['code'] == 'SCRIPT_EXIT', failed
        refs = project_v2_result(failed)['result_ref']
        assert refs['completed_calls_omitted'] > 0 and 'calls_read_args' in refs
        values, _ = resolve_input_refs(refs['failed_calls'][0]['input_args'])
        edited = run('[self:edit]{path:"~turn/조판.py",old_string:$old,new_string:$new}',
                     {'old': 'args["분서"]', 'new': 'args["분석"]'})
        assert edited['success'], edited
        before = len(model_calls)
        recovered = run('return [self:script]{path:$입력.path,args:$입력.args}', values)
        assert recovered['success'] and len(model_calls) == before
        assert [r['action'] for r in recovered['recordings']] == ['self:script']
        # A changed downstream rendering input is a new attempt, using the same computed analysis.
        variant = {**values['입력'], 'args': {**values['입력']['args'], '태그': ['다른 표시']}}
        changed = run('return [self:script]{path:$입력.path,args:$입력.args}', {'입력': variant})
        assert changed['success'] and len(model_calls) == before
        assert changed['value']['issues_json'] == recovered['value']['issues_json']
        normal = run(code, {**inputs, '본문': render, '출력': str(tmp_path / 'normal')})
        assert normal['success'] and normal['value']['문서같음'] and normal['value']['자료같음'], normal
        assert (tmp_path / 'normal/report.md').read_text() == recovered['value']['markdown']
        assert (tmp_path / 'normal/issues.json').read_text() == recovered['value']['issues_json']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
