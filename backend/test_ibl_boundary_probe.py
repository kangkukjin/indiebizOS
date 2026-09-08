"""독립 기대값이 있는 조합 문장 회귀. 네트워크·모델 없이 실제 파서/엔진/도구 실행."""
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_cases import cases, additional_cases
from ibl_boundary_cases_round2 import cases as round2_cases
from ibl_boundary_cases_round2 import additional_cases as round2_additional
from ibl_boundary_cases_round3 import cases as round3_cases
from ibl_boundary_probe import probe


@pytest.mark.parametrize('case', cases() + additional_cases() + round2_cases() + round2_additional() + round3_cases(), ids=lambda c: c['id'])
def test_boundary_sentences(case):
    result = probe(case)
    assert result['syntax_ok'], result.get('error_text')
    assert result['ok'], f"{case['id']}: actual={result.get('actual')!r}; error={result.get('error_text')}"


def test_counter_scope_does_not_escape_repeat():
    from ibl_exec_each import _each_foreign_vars
    text = '[repeat:2]{[table:take]{items:[{n:$i}],n:1}}; [table:take]{items:[{n:$i}],n:1}'
    assert _each_foreign_vars(text, 'it') == ['i']


def test_error_scope_does_not_escape_catch():
    from ibl_exec_each import _each_foreign_vars
    text = '[try]{[self:read]{path:"x"}} [catch]{[self:read]{path:"$error.summary"}}; [self:read]{path:"$error.summary"}'
    assert _each_foreign_vars(text, 'it') == ['error']


def test_recursive_parser_and_executor_share_definition_table():
    # ibl.ibl_parser와 ibl_parser를 동시에 import하면 재귀 파서의 정의 표만
    # 다른 모듈에 생긴다. 전체 수집 순서에서만 중첩 fn이 사라지던 회귀.
    import ibl_parser
    import ibl_parser_blocks
    assert ibl_parser_blocks._PARSE_VARS is ibl_parser.parse_with_vars


@pytest.mark.parametrize('bad', ['[table:take]{items:[{n:$i} {n:2}]}', '[table:take]{items:[{n:$i},,3]}'])
def test_dynamic_arrays_reject_bad_separators(bad):
    from ibl_parser import parse, IBLSyntaxError
    with pytest.raises(IBLSyntaxError):
        parse(bad)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
