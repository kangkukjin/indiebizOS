"""목록 관용구: 변수 보존, 정렬 방향·숨긴 기준 열, 진단 보존과 노출 교체."""
import json
import re
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
NEW = {'열추려보기', '정렬해추리기'}




def test_bodies_have_no_hidden_ai_or_writes():
    for entry in CATALOG['idioms']:
        if entry['name'] in NEW:
            assert set(re.findall(r'\[([a-z_]+:[a-z_]+)', entry['body'])) <= {
                'table:select', 'table:sort', 'table:take'}
            assert not re.search(r'\b(criteria|instruction|prompt|do)\s*:', entry['body'])














if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
