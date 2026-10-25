"""ep3656: 파이프 입력과 명시 인자의 호환, 빈 통화·실패 행·닫힌 서명."""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
















def test_model_map_explains_current_pipe_input():
    from ibl_access import _pipe_input_note
    source = '#!ibl edition=2\n[def:추림]($입력,$수){return $입력 >> [table:take]{n:$수}}'
    assert _pipe_input_note(source) == '앞 값 → 입력 (같은 인자 동시 명시 금지)'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
