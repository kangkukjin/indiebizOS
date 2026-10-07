"""Search content fidelity and bounded context retrieval."""
import builtins
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

SPEC = importlib.util.spec_from_file_location(
    'fs_grep_contract_test',
    ROOT / 'data/packages/installed/tools/system_essentials/fs_grep.py',
)
GREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GREP)


@pytest.mark.parametrize('use_rg', [True, False])
@pytest.mark.parametrize('encoding', ['utf-8', 'cp949'])
@pytest.mark.parametrize('ending', ['\n', '\r\n', ''])
def test_matching_text_preserves_encoding_and_trailing_whitespace(
    tmp_path, monkeypatch, use_rg, encoding, ending,
):
    if use_rg and not GREP._RG_BIN:
        pytest.skip('ripgrep unavailable')
    if not use_rg:
        monkeypatch.setattr(GREP, '_RG_BIN', None)
    path = tmp_path / 'device.txt'
    text = 'ALARM[1] 장비 점검  \t'
    path.write_bytes(('before\n' + text + ending).encode(encoding))
    result = json.loads(GREP.run({
        'path': str(path), 'pattern': 'ALARM[1]', 'regex': False, 'context': 1,
    }, str(tmp_path)))
    assert result['total'] == 1
    assert result['total_complete'] is True
    assert result['truncated'] is False
    assert result['items'][0]['내용'] == text
    assert result['items'][0]['문맥'] == f'1  before\n2> {text}'


def test_long_cp949_match_reports_clipping(tmp_path):
    if not GREP._RG_BIN:
        pytest.skip('ripgrep unavailable')
    path = tmp_path / 'device.txt'
    path.write_bytes(('ALARM ' + '가' * 600 + '\n').encode('cp949'))
    result = json.loads(GREP.run({'path': str(path), 'pattern': 'ALARM'}, str(tmp_path)))
    assert result['items'][0]['내용'].startswith('ALARM 가')
    assert result['truncated'] is True
    assert {'scope': 'source', 'reason': '일치 줄 본문 절단'} in result['truncations']


def test_context_stops_after_last_requested_line(tmp_path, monkeypatch):
    path = tmp_path / 'large.txt'
    path.write_text('before\nALARM 한글  \t\nafter\n' + 'unused\n' * 10000)
    observations = {'lines': 0, 'opens': 0}

    class WatchedFile:
        def __init__(self, *args, **kwargs):
            self.file = builtins.open(*args, **kwargs)
            observations['opens'] += 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def __iter__(self):
            return self

        def __next__(self):
            line = next(self.file)
            observations['lines'] += 1
            return line

    monkeypatch.setattr(GREP, 'open', WatchedFile, raising=False)
    cache = {}
    expected = {2: [(1, 'before'), (2, 'ALARM 한글  \t'), (3, 'after')]}
    assert GREP._context_windows(str(path), [2], 1, cache) == expected
    assert observations == {'lines': 3, 'opens': 1}
    assert GREP._context_windows(str(path), [2], 1, cache) == expected
    assert observations == {'lines': 3, 'opens': 1}


@pytest.mark.parametrize('encoding', ['utf-8', 'cp949'])
def test_context_sparse_overlapping_unsorted_and_eof(tmp_path, encoding):
    path = tmp_path / 'device.txt'
    lines = ['가  ', '나\t', '다', '라', '마', '바']
    path.write_bytes('\r\n'.join(lines).encode(encoding))
    cache = {}
    windows = GREP._context_windows(str(path), [6, 2, 1, 2, 4], 1, cache)
    assert windows == {
        ln: [(n, lines[n - 1]) for n in range(max(1, ln - 1), min(6, ln + 1) + 1)]
        for ln in [6, 2, 1, 4]
    }
    assert GREP._context_windows(str(path), [], 1, cache) == {}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
