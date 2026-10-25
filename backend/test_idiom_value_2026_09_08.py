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












def test_pruned_catalog_keeps_only_intended_recommendations():
    from curate_idioms import validate_catalog
    catalog = json.loads((ROOT / 'data/idioms/curated.json').read_text())
    validate_catalog(catalog)
    active = {e['name'] for e in catalog['idioms'] if e.get('always_on', True)}
    # 2026-09-21 사용자 지정: 생성형 요약 없이 Jev 판정을 하는 두 관용구도 상시 소개.
    assert active == {'열추려보기', '정렬해추리기', '좁혀서읽기',
                      '주소마다읽기', '본문에서찾기', '관련자료골라읽기', '의미로본문찾기'}
    # 호환 항목을 명시 강등하면서도 선정집을 멱등 재적용할 수 있다.
    assert not active.intersection(catalog['demote'])




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
