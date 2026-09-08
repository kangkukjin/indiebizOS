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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
