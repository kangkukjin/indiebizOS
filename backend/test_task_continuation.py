"""명시적 인계가 근거·효과와 현재 실행 소유권을 보존한다."""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import task_continuation as tc


@pytest.mark.parametrize('phase,available', [
    ('execution', True), ('repair_apply', True), ('repair_active', True),
    ('verify_remaining', True), ('apply', False), ('activation', False),
    ('active_verify', False), ('review', False), ('unknown', False),
])
def test_additional_execution_respects_existing_handoff_owner(monkeypatch, phase, available):
    monkeypatch.setattr('repair_continuation.current', lambda: {'phase': phase})
    assert tc.execution_available() is available


def test_new_apply_reservation_stops_execution():
    assert not tc.execution_available(NS(apply_scheduled={'key': 'repair'}))
