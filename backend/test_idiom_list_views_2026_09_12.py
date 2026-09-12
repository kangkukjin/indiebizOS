"""목록 관용구: 변수 보존, 정렬 방향·숨긴 기준 열, 진단 보존과 노출 교체."""
import json
import re
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_worker import run_trial
from idiom_experiment_cases import decoded

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
NEW = {'열추려보기', '정렬해추리기'}


def run(code):
    trial = run_trial(code, 'dedup')
    assert trial['result']['success'], trial['result'].get('error')
    assert trial['observed']['brief'] == 0
    assert set(trial['observed']['leaf_calls']) <= {'table:select', 'table:sort', 'table:take'}
    return decoded(trial['result']['final_result'])


def test_bodies_have_no_hidden_ai_or_writes():
    for entry in CATALOG['idioms']:
        if entry['name'] in NEW:
            assert set(re.findall(r'\[([a-z_]+:[a-z_]+)', entry['body'])) <= {
                'table:select', 'table:sort', 'table:take'}
            assert not re.search(r'\b(criteria|instruction|prompt|do)\s*:', entry['body'])


def test_projection_keeps_order_and_original_variable():
    result = run('$원본=[{id:2,text:"둘",source:"원문2"},{id:1,text:"하나",source:"원문1"}]; '
                 '$보기=[fn:열추려보기]{목록:$원본,열:["text"],개수:1}; '
                 '$return={보기:$보기.items,원본:$원본.items}')['value']
    assert result['보기'] == [{'text': '둘'}]
    assert result['원본'] == [{'id': 2, 'text': '둘', 'source': '원문2'},
                            {'id': 1, 'text': '하나', 'source': '원문1'}]


@pytest.mark.parametrize('descending,expected', [('false', ['싼것', '중간']),
                                               ('true', ['비싼것', '중간'])])
def test_sort_uses_typed_boolean_and_key_not_in_output(descending, expected):
    result = run('$목록=[{title:"중간",price:20},{title:"싼것",price:5},{title:"비싼것",price:90}]; '
                 '[fn:정렬해추리기]{목록:$목록,기준:"price",내림차순:' + descending + ','
                 '열:["title"],개수:2}')
    assert result['items'] == [{'title': title} for title in expected]


def test_composite_sort_and_tail_count_follow_existing_primitives():
    result = run('$목록=[{id:1,a:2,b:1},{id:2,a:1,b:9},{id:3,a:1,b:2}]; '
                 '[fn:정렬해추리기]{목록:$목록,기준:["a","b"],내림차순:false,열:["id"],개수:-2}')
    assert result['items'] == [{'id': 2}, {'id': 1}]


@pytest.mark.parametrize('rows,count', [('[]', 5), ('[{id:1}]', 0)])
@pytest.mark.parametrize('name,extra', [('열추려보기', ''),
                                     ('정렬해추리기', '기준:"id",내림차순:false,')])
def test_empty_selection_does_not_return_entire_input(rows, count, name, extra):
    result = run('$목록=' + rows + '; [fn:' + name + ']{목록:$목록,' + extra +
                 '열:["id"],개수:' + str(count) + '}')
    assert result['items'] == []


@pytest.mark.parametrize('call', [
    '[fn:열추려보기]{목록:$목록,열:["missing"],개수:1}',
    '[fn:정렬해추리기]{목록:$목록,기준:"missing",내림차순:false,열:["id"],개수:1}',
])
def test_missing_columns_are_not_silently_accepted(call):
    trial = run_trial('$목록=[{id:1}]; ' + call, 'dedup')
    assert not trial['result']['success']
    assert 'missing' in trial['result']['error']


@pytest.mark.parametrize('call', [
    '[fn:열추려보기]{목록:$목록,열:["id"],개수:1}',
    '[fn:정렬해추리기]{목록:$목록,기준:"id",내림차순:false,열:["id"],개수:1}',
])
def test_upstream_failure_and_truncation_survive_views(call):
    result = run('$목록={items:[{id:2},{id:1}],error_count:1,errors:["접근 제한"],'
                 'truncated:true}; ' + call)
    encoded = json.dumps(result, ensure_ascii=False)
    assert result['error_count'] == 1
    assert result['truncated'] is True
    assert '접근 제한' in encoded


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
