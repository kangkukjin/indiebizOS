"""현행 문법의 문자열 손실·잘못된 인자 침묵 회귀."""
import sys
import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def test_malformed_argument_does_not_become_an_empty_record():
    with pytest.raises(Fault):
        compile_program('[sense:stock]{ticker: "N"VDA"}.price', {})


def test_string_escape_preserves_actual_value():
    result = Runtime(compile_program(r'return "첫째\n둘째\\경로"', {})).run()
    assert result['success'] is True
    assert result['value'] == '첫째\n둘째\\경로'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
