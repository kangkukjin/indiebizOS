"""선별 관용구의 결과 계약 및 실험에서 발견한 읽기 범위 회귀."""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_value_cases import GOLD, final_value, content
from idiom_experiment_worker import run_trial


@pytest.mark.parametrize('case', list(GOLD))
def test_value_references(case):
    result = run_trial(GOLD[case], case, suite='value_v3')
    assert result['quality_ok'], result['verdict']


@pytest.mark.parametrize('params', [
    'start_line:0,limit:2', 'start_line:4,end_line:2', 'offset:-1,limit:2',
    'start_line:"bad",limit:2', 'limit:-1', 'limit:1.5', 'tail:-1',
    'offset:2,start_line:1', 'start_line:2,end_line:4,limit:8',
])
def test_invalid_read_range_is_not_silently_changed(params):
    result = run_trial('[self:read]{path:"reports/a.md",' + params + '}', 'latest_window', suite='value_v3')
    assert result['result']['success'] is False
    assert '범위 오류' in result['result']['error']


@pytest.mark.parametrize('params', ['limit:0', 'offset:10,limit:0', 'start_line:221,limit:4'])
def test_empty_text_range_does_not_read_entire_file(params):
    result = run_trial('[self:read]{path:"reports/a.md",' + params + '}', 'latest_window', suite='value_v3')
    assert result['result']['success']
    assert content(final_value(result['result'])) == []


def test_empty_blocks_range_does_not_read_entire_file():
    result = run_trial('[self:read]{path:"reports/a.md",limit:0,blocks:true}', 'latest_window', suite='value_v3')
    assert result['result']['success']
    assert final_value(result['result'])['items'] == []


@pytest.mark.parametrize('params', ['start_line:25,end_line:31', 'offset:24,limit:7', 'start:24,end:31'])
def test_equivalent_read_ranges(params):
    result = run_trial('[self:read]{path:"reports/a.md",' + params + '}', 'latest_window', suite='value_v3')
    assert result['quality_ok'], result['verdict']


def test_pruned_catalog_keeps_only_intended_recommendations():
    from curate_idioms import validate_catalog
    catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())
    validate_catalog(catalog)
    active = {e['name'] for e in catalog['idioms'] if e.get('always_on', True)}
    assert active == {'열추려보기', '정렬해추리기', '최신범위읽기',
                      '미처리만고르기', '묶어순위내기', '주소마다읽기'}
    # 호환 항목을 명시 강등하면서도 선정집을 멱등 재적용할 수 있다.
    assert not active.intersection(catalog['demote'])


def test_oracle_rejects_lost_content_and_wrong_latest():
    wrong = '[self:read]{path:"reports/z.md"}'
    assert not run_trial(wrong, 'latest_full', suite='value_v3')['quality_ok']
    wrong = '[self:grep]{path:"notes",pattern:"NEEDLE",limit:20} >> [table:take]{n:5}'
    result = run_trial(wrong, 'five_contexts', suite='value_v3')
    assert result['result']['success'] and not result['quality_ok']


@pytest.mark.parametrize('code', [
    '[self:read]{path:"a.txt",end_line:3 + 6}',
    '[table:take]{n:2 * 3}',
])
def test_inline_arithmetic_gets_relevant_diagnosis(code):
    from ibl_parser import parse, IBLSyntaxError
    with pytest.raises(IBLSyntaxError, match='산술식') as exc:
        parse(code)
    assert '이스케이프되지 않았을 가능성' not in str(exc.value)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
