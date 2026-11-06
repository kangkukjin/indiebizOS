import boot_paths  # noqa: F401
import codecs
import pytest
from lsp_positions import decode, encode, to_lsp, from_lsp, edit_text, uri_path


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
def test_unicode_roundtrip_crlf_combining_tab(encoding):
    text = '가😀e\u0301\t끝\r\n다음\n'
    for line, content in enumerate(text.split('\n'), 1):
        for column in range(1, len(content.removesuffix('\r')) + 2):
            point = {'line': line, 'column': column}
            assert from_lsp(text, to_lsp(text, point, encoding), encoding) == point
    with pytest.raises(ValueError):
        to_lsp(text, {'line': 1, 'column': 99}, encoding)


def test_utf16_inside_surrogate_is_not_a_character_boundary():
    with pytest.raises(ValueError):
        from_lsp('😀', {'line': 0, 'character': 1})


@pytest.mark.parametrize('data', [codecs.BOM_UTF8 + '한글'.encode(), codecs.BOM_UTF16_BE + '한글'.encode('utf-16-be'),
                                  codecs.BOM_UTF16_LE + '한글'.encode('utf-16-le')])
def test_encoding_preserves_bom_and_endianness(data):
    text, encoding = decode(data)
    assert text == '한글' and encode(text, encoding) == data


def test_insertions_have_declared_order_overlap_rejected():
    point = {'line': 0, 'character': 1}
    edits = [{'range': {'start': point, 'end': point}, 'newText': s} for s in ('X', 'Y')]
    assert edit_text('ab', edits) == 'aXYb'
    span = {'start': {'line': 0, 'character': 0}, 'end': point}
    with pytest.raises(ValueError):
        edit_text('ab', [{'range': span, 'newText': ''}] * 2)


def test_uri_escapes_are_decoded_once(tmp_path):
    path = tmp_path / '한글 %20.py'
    assert uri_path(path.as_uri()) == path
    with pytest.raises(ValueError):
        uri_path('https://example.com/code.py')
