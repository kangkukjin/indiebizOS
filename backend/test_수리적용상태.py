"""수리적용상태는 소유자의 관측을 보존하며 미관측을 완료로 만들지 않는다."""
import boot_paths  # noqa: F401
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('repair_status_under_test', ROOT / 'data/scripts/수리적용상태.py')
status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status)


def test_missing_owner_observation_requests_lookup_and_remains_unknown():
    result = status.project_status({'key': 'repair-key'})
    assert result['state'] == 'unknown' and result['reported_complete'] is None
    assert not result['source_complete'] and not result['items']
    assert result['request']['args'] == {'op': 'status', 'key': 'repair-key'}


@pytest.mark.parametrize('stage,applied,complete', [
    ('staging', False, False), ('scheduled', False, False),
    ('activation_failed', True, False), ('complete', True, True),
])
def test_owner_stages_file_observation_and_receipts_remain_distinct(stage, applied, complete):
    row = {'key': 'repair-key', 'status': 'applied' if complete else 'staging',
           'stage': stage, 'applied': applied, 'complete': complete,
           'live_comparison': {'matching': 1}, 'activation': {'state': stage},
           'commit': {'state': 'committed' if complete else 'pending'}}
    snapshot = {'success': True, 'items': [row], 'complete': complete}
    result = status.project_status({'key': 'repair-key', 'status': snapshot, 'observed_at': 'fixture-time'})
    got = result['items'][0]
    assert result['reported_complete'] is complete
    assert got['stored_receipts']['stage'] == stage
    assert got['stored_receipts']['applied'] is applied
    assert got['stored_receipts']['commit'] == row['commit']
    assert got['file_observation'] == {'matching': 1}
    assert got['owner_observed_at'] == 'fixture-time'
    assert not result['active_rechecked_here'] and not got['active_rechecked_here']
    assert 'activation_checks' in got['unknown']


def test_other_key_is_not_evidence_for_requested_repair():
    result = status.project_status({'key': 'wanted', 'status': {'success': True,
                                   'items': [{'key': 'other', 'complete': True}]}})
    assert not result['items'] and not result['source_complete']
    assert result['reported_complete'] is None and result['unknown']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
