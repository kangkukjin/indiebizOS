"""CSV read failures must locate the record without exposing its cell values."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('round12_file_io', ROOT / 'data/packages/installed/tools/system_essentials/essentials_file_io.py')
IO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IO)


@pytest.mark.parametrize('sep', [',', '\t'])
@pytest.mark.parametrize('body,expected', [('a,b\n1,2\nprivate,3,4\n', '레코드 3'), ('a,b\n1\n', '레코드 2'), ('a,a\n1,2\n', '열 2'), ('a,\n1,2\n', '열 2')])
def test_delimited_error_locates_record_or_column(sep, body, expected):
    with pytest.raises(ValueError) as error:
        IO.delimited_data(body.replace(',', sep), sep)
    assert expected in str(error.value)
    assert 'private' not in str(error.value)


def test_quoted_newline_counts_logical_records():
    with pytest.raises(ValueError, match='레코드 3') as error:
        IO.delimited_data('a,b\n"first\nsecond",2\n3\n', ',')
    assert '물리 줄 4' in str(error.value)
    assert '기대 2' in str(error.value) and '실제 1' in str(error.value)


def test_quoted_delimiters_bom_and_zero_unchanged():
    result = IO.delimited_data('\ufeffa,b\n"x,y",0\n"line\nbreak",\n', ',')
    assert result['items'] == [{'a':'x,y','b':'0'}, {'a':'line\nbreak','b':''}]


def test_runtime_failure_keeps_file_path(tmp_path):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    path = tmp_path/'bad.csv'
    path.write_text('a,b\n1,2,3\n')
    inputs = {'path':str(path)}
    plan = compile_program('[self:read]{path:$path}', load_registry(str(ROOT)), inputs)
    result = Runtime(plan, inputs).run()
    assert not result['success']
    assert str(path) in result['diagnostic']['message']
    assert '레코드 2' in result['diagnostic']['message']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
