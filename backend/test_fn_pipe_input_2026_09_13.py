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


def test_filtered_pipe_matches_explicit_input_with_sources_and_failure_rows():
    prefix = '[self:read]{path:"input.json"} >> [table:take]{n:4}'
    piped, seen = execute(prefix + ' >> [fn:주소마다읽기]{개수:3}')
    named, _ = execute('$주소=' + prefix + '; [fn:주소마다읽기]{목록:$주소,개수:3}')
    assert piped['items'] == named['items']
    assert piped['error_count'] == named['error_count'] == 1
    assert len(piped['items']) == 3
    assert sorted(seen['crawl']) == ['https://fixture.test/a', 'https://fixture.test/bad', 'https://fixture.test/c']
    assert piped['items'][1]['_error']


@pytest.mark.parametrize('head,args', [
    ('[]', '개수:3'),
    ('[{url:"https://fixture.test/a"}]', '개수:0'),
    ('[{url:"https://fixture.test/a"}]', '목록:[],개수:3'),
])
def test_empty_pipe_explicit_empty_and_zero_limit_never_crawl(head, args):
    result, seen = execute(head + ' >> [fn:주소마다읽기]{' + args + '}')
    assert result['items'] == [] and seen['crawl'] == []


def test_explicit_list_wins_over_a_different_pipe():
    result, seen = execute('[{url:"https://fixture.test/a"}] >> '
                           '[fn:주소마다읽기]{목록:[{url:"https://fixture.test/c"}],개수:1}')
    assert seen['crawl'] == ['https://fixture.test/c']
    assert result['items'][0]['url'] == 'https://fixture.test/c'


@pytest.mark.parametrize('code,missing', [
    ('[fn:주소마다읽기]{개수:3}', '목록'),
    ('[] >> [fn:주소마다읽기]{}', '개수'),
    ('$앞=[]; [fn:주소마다읽기]{개수:3}', '목록'),
])
def test_no_input_other_missing_arg_and_statement_boundary_still_fail(code, missing):
    trial = run_trial(code, 'dedup')
    assert trial['result']['success'] is False
    assert missing in json.dumps(trial['result'], ensure_ascii=False)
    assert trial['observed']['crawl'] == []


def test_local_function_uses_the_same_rule_without_idiom_names():
    result, _ = execute('[def:잘라반환]{ $자료 >> [table:take]{n:$수} }\n'
                        '[{v:1},{v:2}] >> [fn:잘라반환]{수:1}')
    assert result['items'] == [{'v': 1}]


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
