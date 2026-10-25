"""ep3656: 파이프 입력과 명시 인자의 호환, 빈 통화·실패 행·닫힌 서명."""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_worker import run_trial
from idiom_experiment_cases import decoded
from ibl_parser import parse_function_body
from workflow_contract import pipe_input_param


def execute(code):
    trial = run_trial(code, 'dedup')
    assert trial['result']['success'], trial['result']
    assert trial['observed']['brief'] == 0
    return decoded(trial['result']['final_result']), trial['observed']












@pytest.mark.parametrize('body', [
    '$a & $b >> [table:union]',
    '$a.items >> [table:take]{n:$n}',
    '$a\n[table:take]{n:$n}',
    '[table:take]{n:$n}\n$a >> [table:take]{n:1}',
])
def test_no_binding_for_ambiguous_or_nonleading_input(body):
    assert pipe_input_param(parse_function_body(body)) is None


def test_model_map_explains_pipe_and_explicit_precedence():
    from ibl_access import _pipe_input_note
    assert _pipe_input_note('$입력 >> [table:take]{n:$수}') == '앞 통화 → 입력 (명시 인자 우선)'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
