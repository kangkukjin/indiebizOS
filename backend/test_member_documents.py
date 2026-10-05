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


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
