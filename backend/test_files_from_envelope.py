"""File transport after retirement: explicit inputs/read, no numbered substitution."""
import json

import boot_paths  # noqa: F401
import pytest

from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_runtime import Runtime


def pure(code, inputs):
    plan = compile_program(code, registry={}, inputs=inputs, definitions={})
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs).run()


def test_inline_only_passthrough():
    for value in ([], ['A'], None):
        assert pure('return $data', {'data': value})['value'] == value


def test_paths_appended_after_inline_numbering(tmp_path):
    path = tmp_path / 'body.md'
    path.write_text('경로 본문 — 따옴표 " 와 \\ 역슬래시')
    result = handle_request({'edition': 2, 'code':
        '$doc=[self:read]{path:$path}; return [$inline,$doc.text]',
        'inputs': {'path': str(path), 'inline': '인라인'}}, str(tmp_path))
    assert result['success'] and result['value'] == ['인라인', path.read_text()]


def test_korean_content_roundtrip():
    body = '# 부동산 발굴 보고서 — 서울 은평·서대문\n' * 2000
    result = pure('return $body', {'body': body})
    assert result['success'] and result['value'] == body


def test_missing_path_is_honest_error(tmp_path):
    result = handle_request({'edition': 2, 'code':
        '[self:read]{path:$path}; [self:write]{path:$out,content:"never"}',
        'inputs': {'path': str(tmp_path/'absent.md'), 'out': str(tmp_path/'out.md')}}, str(tmp_path))
    assert not result['success'] and not (tmp_path/'out.md').exists()


@pytest.mark.parametrize('key,value', [('files', ['inline']), ('files_from', ['path.md']),
                                       ('files_from', 'path.md'), ('files_from', [123])])
def test_non_list_and_non_str_rejected(monkeypatch, key, value):
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: pytest.fail('tools loaded'))
    result = handle_request({'edition': 2, 'code': 'return 1', key: value})
    assert not result['executed'] and 'REQUEST_FIELDS' in str(result)


def test_cap_enforced(monkeypatch):
    # Removed transport is refused before loading or reading any supplied path.
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: pytest.fail('tools loaded'))
    result = handle_request({'edition': 2, 'code': 'return 1', 'files_from': ['large.md'] * 1000})
    assert not result['executed'] and 'REQUEST_FIELDS' in str(result)


def test_substitution_uses_merged_list():
    result = pure('return $data[0] + " / " + $data[1]', {'data': ['본문A', '본문B']})
    assert result['value'] == '본문A / 본문B'


def test_file_ref_two_digit_index_is_one_token():
    result = pure('return [$data[10],$data[1],$data[11]]', {'data': [f'F{i}' for i in range(12)]})
    assert result['value'] == ['F10', 'F1', 'F11']


def test_file_ref_inserted_content_is_not_rescanned():
    body = '본문에 $file:1 이라는 글자 ${data} $it'
    assert pure('return $body', {'body': body})['value'] == body


def test_file_ref_out_of_range_is_reported_not_silently_written():
    result = pure('return $data[7]', {'data': ['A']})
    assert not result['success']


def test_file_ref_recurses_branches_and_fallback_chain():
    result = pure('[if:true]{return {nested:[$a,$b]}} [else]{return null}',
                  {'a': '$file:0', 'b': '$file:1'})
    assert result['value'] == {'nested': ['$file:0', '$file:1']}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
