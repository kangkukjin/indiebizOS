"""함수 결과의 중첩 실행 기록도 모델 경계에서만 접는다."""
import copy
import json
import sys

import pytest
import boot_paths  # noqa: F401

from ibl_envelope import diet_envelope


def fn_envelope(final, **metadata):
    return {
        'success': True, 'fn': '시험함수', 'fn_source': 'idiom',
        'steps_total': 2, 'steps_completed': 2,
        'results': [
            {'step': 1, 'result': json.dumps({'items': [{'body': '원문' * 9000}]}),
             'duration_ms': 1},
            {'step': 2, 'result': final, 'duration_ms': 1},
        ],
        'final_result': final, **metadata,
    }


@pytest.mark.parametrize('as_string', [False, True])
def test_nested_fn_keeps_value_and_diagnostics_without_raw_trace(as_string):
    value = json.dumps({'items': [{'title': '자료', 'message': '요약'}]})
    child = fn_envelope(value, errors=[{'url': 'bad', '_error': '없음'}],
                        error_count=1, warning='부분 결과', returned='$return')
    raw = json.dumps(child) if as_string else child
    env = {'results': [{'step': 1, 'result': raw}], 'final_result': raw}
    original = copy.deepcopy(env)
    out = diet_envelope(env)
    final = json.loads(out['final_result']) if as_string else out['final_result']
    assert final['_results_summarized']
    assert final['final_result'] == value
    for key in ('errors', 'error_count', 'warning', 'returned', 'fn', 'fn_source'):
        assert final[key] == child[key]
    assert 'result' not in final['results'][0]
    assert len(json.dumps(out)) < len(json.dumps(original)) / 5
    assert env == original
    assert diet_envelope(out) is out
    assert diet_envelope(env, verbose=True) is env


def test_nested_failure_keeps_definition_and_traceback():
    child = fn_envelope(None, success=False, error='읽기 실패',
                        traceback={'frames': [{'kind': 'fn', 'name': '시험함수'}]},
                        hint='정의를 고치세요', **{'def': '[def: 시험함수]{…}'})
    child['results'][1] = {'step': 2, 'result': {'success': False, 'error': '읽기 실패'}}
    out = diet_envelope(fn_envelope(json.dumps(child)))
    nested = json.loads(out['final_result'])
    for key in ('success', 'error', 'traceback', 'hint', 'def'):
        assert nested[key] == child[key]
    assert nested['results'][1]['error'] == '읽기 실패'


def test_plain_business_results_and_rows_are_never_traversed():
    payload = {'results': [{'result': '업무 원본'}], 'final_result': '업무 값'}
    for value in (payload, json.dumps(payload), {'items': [fn_envelope('본문')]}):
        out = diet_envelope(fn_envelope(value))
        assert out['final_result'] == value


def test_two_fn_levels_are_summarized_and_leaf_value_is_exact():
    leaf = '수정하지 않을 산문\n' * 100
    outer = fn_envelope(json.dumps(fn_envelope(json.dumps(fn_envelope(leaf)))))
    out = diet_envelope(outer)
    for _ in range(3):
        assert out['_results_summarized']
        out = out['final_result']
        if out.startswith('{'):
            out = json.loads(out)
    assert out == leaf


@pytest.mark.parametrize('source', ['idiom', 'def', 'workflow'])
@pytest.mark.parametrize('encode_list', [False, True])
@pytest.mark.parametrize('encode_branch', [False, True])
def test_parallel_fn_results_keep_values_failures_and_serialization(
        source, encode_list, encode_branch):
    value = {'items': [{'id': 7, 'body': '업무 원문', 'results': ['업무 기록']}]}
    good = fn_envelope(value, fn_source=source, warning='일부 출처 누락',
                       errors=[{'url': 'missing', '_error': '읽기 실패'}], error_count=1,
                       returned='$return', rows_processed=1, rows_requested=2)
    bad = fn_envelope(None, fn_source=source, success=False, error='분기 실패',
                      traceback={'frames': [{'kind': 'fn', 'name': '실패함수'}]},
                      resume={'from_step': 2}, **{'def': '[def: 실패함수]{…}'})
    bad['results'][1] = {'step': 2, 'result': {'success': False, 'error': '분기 실패'}}
    branches = [good, bad]
    if encode_branch:
        branches = [json.dumps(b, ensure_ascii=False) for b in branches]
    final = json.dumps(branches, ensure_ascii=False) if encode_list else branches
    env = {'success': False, 'results': [{'step': 1, 'type': 'parallel', 'result': final}],
           'final_result': final, 'branches_failed': 1}
    original = copy.deepcopy(env)
    out = diet_envelope(env)
    assert isinstance(out['final_result'], str) == encode_list
    actual = json.loads(out['final_result']) if encode_list else out['final_result']
    for expected, branch in zip([good, bad], actual):
        assert isinstance(branch, str) == encode_branch
        branch = json.loads(branch) if encode_branch else branch
        assert branch['_results_summarized']
        assert 'result' not in branch['results'][0]
        for key, val in expected.items():
            if key != 'results':
                assert branch[key] == val
    assert out['success'] is False and out['branches_failed'] == 1
    assert len(json.dumps(out)) < len(json.dumps(original)) / 5
    assert env == original
    assert diet_envelope(out) is out
    assert diet_envelope(env, verbose=True) is env


def test_parallel_walk_visits_nested_returns_but_not_business_records():
    business = {'items': [fn_envelope('업무 데이터 속 닮은 객체')],
                'results': [{'result': '업무 기록'}], 'final_result': '업무 값'}
    business_text = '  ' + json.dumps(business, ensure_ascii=False) + '\n'
    nested = [fn_envelope('첫째'), [fn_envelope([fn_envelope('둘째')])],
              business, business_text, '산문', 7, None]
    env = fn_envelope(nested)
    original = copy.deepcopy(env)
    out = diet_envelope(env)['final_result']
    assert out[0]['_results_summarized'] and out[0]['final_result'] == '첫째'
    inner = out[1][0]
    assert inner['_results_summarized']
    assert inner['final_result'][0]['_results_summarized']
    assert inner['final_result'][0]['final_result'] == '둘째'
    assert out[2:] == nested[2:]
    assert env == original
    plain = fn_envelope([business, business_text, '산문'])
    assert diet_envelope(plain)['final_result'] is plain['final_result']


def test_parallel_fn_from_actual_parser_and_executor():
    from test_ibl_functions import _run
    env = _run('[def: 앞둘]{[x:rows]{} >> [x:take]{n: 2}}\n'
               '[fn:앞둘]{} & [fn:앞둘]{}')
    assert env['success'], env
    original = copy.deepcopy(env)
    out = diet_envelope(env)
    before = json.loads(env['final_result'])
    after = json.loads(out['final_result'])
    for raw, thin in zip(before, after):
        raw = json.loads(raw) if isinstance(raw, str) else raw
        thin = json.loads(thin) if isinstance(thin, str) else thin
        assert thin['_results_summarized']
        assert thin['items'] == raw['items'] == [{'a': 1}, {'a': 2}]
        assert thin['final_result'] == raw['final_result']
    assert env == original


def test_parallel_fn_model_view_keeps_full_evidence_readable(tmp_path, monkeypatch):
    import model_result_view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: store)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *a, **kw: None)
    value = {'items': [{'id': 1, 'text': '업무 본문', 'source': '출처'}]}
    child = fn_envelope(value, error_count=1, errors=[{'error': '일부 실패'}])
    final = json.dumps([json.dumps(child, ensure_ascii=False)] * 2, ensure_ascii=False)
    env = {'success': True, 'results': [{'step': 1, 'type': 'parallel', 'result': final}],
           'final_result': final}
    original = copy.deepcopy(env)
    out = model_result_view.project_result(env)
    branches = out['final_result']
    branches = json.loads(branches) if isinstance(branches, str) else branches
    for branch in branches:
        branch = json.loads(branch) if isinstance(branch, str) else branch
        assert branch['_results_summarized']
        assert branch['final_result'] == value
        assert branch['errors'] == child['errors'] and branch['error_count'] == 1
        assert 'result' not in branch['results'][0]
    assert len(json.dumps(out, ensure_ascii=False)) < len(json.dumps(env, ensure_ascii=False)) / 5
    saved = store.read_evidence(out['result_ref']['id'], 0, None)
    assert json.loads(saved['text']) == original
    page = model_result_view.read_result({'id': out['result_ref']['id'], 'offset': 0,
                                         'limit': 200, 'path': ['final_result', 0,
                                                               'results', 0, 'result']})
    assert '원문' in page['text'] and page['next_read']
    assert env == original


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
