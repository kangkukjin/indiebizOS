"""독립 기대값이 있는 조합 문장 회귀. 네트워크·모델 없이 실제 파서/엔진/도구 실행."""
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_cases import cases, additional_cases
from ibl_boundary_probe import probe


@pytest.mark.parametrize('case', cases() + additional_cases(), ids=lambda c: c['id'])
def test_boundary_sentences(case):
    result = probe(case)
    assert result['syntax_ok'], result.get('error_text')
    assert result['ok'], {k: v for k, v in result.items() if k != 'result'}


def test_counter_scope_does_not_escape_repeat():
    from ibl_exec_each import _each_foreign_vars
    text = '[repeat:2]{[table:take]{items:[{n:$i}],n:1}}; [table:take]{items:[{n:$i}],n:1}'
    assert _each_foreign_vars(text, 'it') == ['i']


def test_error_scope_does_not_escape_catch():
    from ibl_exec_each import _each_foreign_vars
    text = '[try]{[self:read]{path:"x"}} [catch]{[self:read]{path:"$error.summary"}}; [self:read]{path:"$error.summary"}'
    assert _each_foreign_vars(text, 'it') == ['error']


@pytest.mark.parametrize('bad', ['[table:take]{items:[{n:$i} {n:2}]}', '[table:take]{items:[{n:$i},,3]}'])
def test_dynamic_arrays_reject_bad_separators(bad):
    from ibl_parser import parse, IBLSyntaxError
    with pytest.raises(IBLSyntaxError):
        parse(bad)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
