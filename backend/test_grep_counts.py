"""L11-1: grep totals count matching lines, not occurrences within a line."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

SPEC = importlib.util.spec_from_file_location('round11_fs_grep', ROOT / 'data/packages/installed/tools/system_essentials/fs_grep.py')
GREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GREP)


@pytest.mark.parametrize('use_rg', [True, False])
@pytest.mark.parametrize('regex,pattern', [(False, 'needle'), (True, 'needle|pin')])
@pytest.mark.parametrize('mode', ['content', 'count', 'files_with_matches'])
def test_same_line_matches_count_once(tmp_path, monkeypatch, use_rg, regex, pattern, mode):
    if use_rg and not GREP._RG_BIN:
        pytest.skip('ripgrep unavailable')
    if not use_rg:
        monkeypatch.setattr(GREP, '_RG_BIN', None)
    path = tmp_path / 'a.txt'
    path.write_text('before\nneedle needle needle needle\nafter\n')
    result = json.loads(GREP.run({'path': str(path), 'pattern': pattern, 'regex': regex, 'output_mode': mode, 'context': 1}, str(tmp_path)))
    assert result['total'] == 1
    assert result['truncated'] is False
    assert len(result['items']) == 1
    if mode == 'content':
        assert result['total_complete'] is True
        assert result['items'][0]['줄번호'] == 2
        assert 'before' in result['items'][0]['문맥']
    if mode == 'count':
        assert result['items'][0]['매칭 수'] == 1


def test_real_selection_and_source_truncation_remain(tmp_path):
    if not GREP._RG_BIN:
        pytest.skip('ripgrep unavailable')
    path = tmp_path / 'a.txt'
    path.write_text('needle needle\nneedle needle needle\n')
    selected = json.loads(GREP.run({'path': str(path), 'pattern': 'needle', 'limit': 1}, str(tmp_path)))
    assert selected['total'] == 2
    assert len(selected['items']) == 1
    assert selected['truncations'][0]['scope'] == 'selection'
    path.write_text('needle ' * 100 + '\n')
    clipped = json.loads(GREP.run({'path': str(path), 'pattern': 'needle'}, str(tmp_path)))
    assert clipped['total'] == 1
    assert clipped['truncations'] == [{'scope': 'source', 'reason': '일치 줄 본문 절단'}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
