"""Member structured file reads have the same lossless cells as owner reads."""
import boot_paths  # noqa: F401
import base64
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('extension,delimiter', [('csv', ','), ('tsv', '\t')])
@pytest.mark.parametrize('terminator', ['\r\n', '\r'])
def test_received_csv_cells_keep_newline_bytes(tmp_path, extension, delimiter, terminator):
    path = ROOT / 'data/packages/installed/tools/system_essentials/member_documents.py'
    spec = importlib.util.spec_from_file_location('member_newlines', path)
    member = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(member)
    content = terminator.join(['\ufeffa' + delimiter + 'b',
                               '1' + delimiter + '"CR\rLF\nCRLF\r\nend"', ''])
    requests = []

    def exchange(request):
        requests.append(request)
        return {'success': True, 'content': base64.b64encode(content.encode()).decode()}

    result = member.read_document({'path': 'received.' + extension, 'blocks': True},
                                  {}, exchange, tmp_path)
    assert result['text'] == content
    assert result['structured_data']['items'] == [{'a': '1', 'b': 'CR\rLF\nCRLF\r\nend'}]
    assert requests == [{'op': 'read', 'path': 'received.' + extension, 'encoding': 'base64'}]


@pytest.mark.parametrize('terminator', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('numbered', [False, True])
def test_member_text_ranges_share_physical_lines_and_numbering(tmp_path, terminator, numbered):
    path = ROOT / 'data/packages/installed/tools/system_essentials/member_documents.py'
    spec = importlib.util.spec_from_file_location('member_ranges', path)
    member = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(member)
    # Unicode paragraph separators and vertical tabs are content, not CR/LF rows.
    lines = ['private', 'excluded\u2028still excluded\vnot a new line',
             '한글 🧭  ', '  public\tline', 'last  ', 'private appendix']
    raw = (terminator.join(lines) + terminator).encode()
    commands = []
    def exchange(command):
        commands.append(command)
        return {'success': True, 'content': base64.b64encode(raw).decode()}
    result = member.read_document(
        {'path': 'manual.txt', 'start_line': 3, 'end_line': 5,
         'numbered': numbered, 'blocks': True}, {}, exchange, tmp_path)
    expected = ''.join((f'{n}\t' if numbered else '') + lines[n-1] + terminator
                       for n in range(3, 6))
    assert result['message'] == expected
    assert (result['start_line'], result['end_line'], result['total_lines']) == (3, 5, 6)
    assert commands == [{'op': 'read', 'path': 'manual.txt', 'encoding': 'base64'}]


@pytest.mark.parametrize('params,expected', [
    ({'tail': 2, 'numbered': True}, '2\tb\r3\tc'),
    ({'limit': 0, 'numbered': True}, ''),
    ({'offset': 1, 'limit': 1, 'numbered': True}, '2\tb\r'),
])
def test_member_numbered_tail_and_empty_ranges(tmp_path, params, expected):
    path = ROOT / 'data/packages/installed/tools/system_essentials/member_documents.py'
    spec = importlib.util.spec_from_file_location('member_range_edges', path)
    member = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(member)
    result = member.read_document({'path': 'manual.txt', 'blocks': True, **params}, {},
        lambda c: {'success': True, 'content': base64.b64encode(b'a\r\nb\rc').decode()}, tmp_path)
    assert result['message'] == expected


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
