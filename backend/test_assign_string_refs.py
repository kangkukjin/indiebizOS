"""식 할당의 따옴표 안 참조가 내부 바인딩 이름으로 새지 않아야 한다."""
import json
import sys

import pytest
import boot_paths  # noqa: F401

from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


def assign(expr, value):
    inputs = {'자료': json.loads(value)}
    return Runtime(compile_program('return ' + expr, inputs=inputs), inputs).run()


@pytest.mark.parametrize('quote', ['"', "'"])
@pytest.mark.parametrize('value', ['경로/보고서.md', '007', 'a"b\'c\\d\n다음', '$없는변수'])
def test_quoted_ref_preserves_string_without_code_injection(quote, value):
    out = assign('f' + quote + '${자료.path}' + quote,
                 json.dumps({'path': value}, ensure_ascii=False))
    assert out['success'], out
    assert out['value'] == value


def test_text_interpolation_and_numeric_ref_in_same_expression():
    out = assign('f"총 ${자료.n}건${자료.n + 1}"', json.dumps({'n': 2}))
    assert out['success'], out
    assert out['value'] == '총 2건3'


def test_missing_quoted_path_still_fails():
    out = assign('f"${자료.missing}"', json.dumps({'path': 'x'}))
    assert not out['success'] and ('missing' in str(out))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
