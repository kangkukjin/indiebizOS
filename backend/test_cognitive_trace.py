"""평가용 실행 증거는 작은 결과·실패와 원본 참조를 예산 안에서 보존한다."""
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from cognitive_trace import serialize_tool_trace


@pytest.mark.parametrize('as_text', [False, True])
@pytest.mark.parametrize('passed', [False, True])
def test_v2_large_fields_do_not_hide_small_checks(as_text, passed):
    result = {'edition': 2, 'success': True, 'source_complete': False,
              'value': {'rows': ['x' * 10000], 'audit': {'passed': passed, 'missing': None},
                        'other_rows': ['z' * 10000]},
              'value_wire': {'duplicate': 'NO_DUPLICATE' * 5000},
              'evidence_summary': {'source_failures': 1},
              'result_ref': {'id': 'original-result', 'read': 'NO_HINT' * 2000}}
    original = json.dumps(result)
    calls = [{'name': 'execute_ibl', 'result': original if as_text else result}]
    trace = serialize_tool_trace(calls, total_budget=1400, per_result_chars=1100)
    assert len(trace) <= 1400
    assert '"passed": ' + str(passed).lower() in trace
    assert '"missing": null' in trace and '"source_complete": false' in trace
    assert '"source_failures": 1' in trace and 'original-result' in trace
    assert '_evaluation_omitted' in trace and '일부 결과 본문 생략됨' in trace
    assert 'NO_DUPLICATE' not in trace and 'NO_HINT' not in trace
    assert json.dumps(result) == original


def test_round17_original_receipt_keeps_verification_in_default_final_budget():
    path = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_17/harness/evaluation_gap.json'
    result = json.loads(path.read_text())['before_evaluation_result']
    calls = [{'name': 'execute_ibl', 'result': {'large': 'x' * 10000}} for _ in range(9)]
    calls.append({'name': 'execute_ibl', 'result': result})
    trace = serialize_tool_trace(calls, total_budget=24000, head_keep=12, tail_keep=12, per_result_chars=3000)
    assert len(trace) <= 24000
    for key, value in result['value']['verification'].items():
        assert json.dumps(key) + ': ' + json.dumps(value) in trace
    assert result['result_ref']['id'] in trace


def test_v2_failure_is_not_replaced_by_business_success_claim():
    result = {'edition': 2, 'success': False, 'executed': True, 'run_status': 'failed',
              'error': {'code': 'FAILED_CHECK'}, 'value': {'complete': True, 'rows': ['x' * 9000]}}
    trace = serialize_tool_trace([{'name': 'execute_ibl', 'result': result, 'is_error': True}], total_budget=900)
    assert '"success": false' in trace and '"run_status": "failed"' in trace
    assert 'FAILED_CHECK' in trace and '[ERROR]' in trace


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
