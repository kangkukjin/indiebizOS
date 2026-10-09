"""Large replay receipts stay recoverable without copying them onto the wire."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

from ibl_result_transport import compact_recordings


def test_large_recordings_keep_lossless_reference_and_runtime_value():
    receipts = [{'action': 'limbs:screen', 'value': ['scalar', 'x' * 100_000]},
                {'error': {'code': 'TOOL', 'message': 'failure'}}]
    original = {'recordings': receipts, 'success': False, 'value': {'answer': 42}, 'diagnostic': {'code': 'TOOL'}}
    shown = compact_recordings(original)
    assert shown['recordings'] == [] and shown['recordings_count'] == 2
    assert shown['value'] == original['value'] and shown['diagnostic'] == original['diagnostic']
    path = shown['recordings_ref']['ref']['path']
    assert json.loads(Path(path).read_text()) == receipts
    assert original['recordings'] == receipts
    small = {'recordings': [{'error': 'small'}]}
    assert compact_recordings(small) is small


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
