"""Incomplete envelope evidence survives projection without inspecting business rows."""
import boot_paths  # noqa: F401
import pytest

from ibl_honesty import completion_evidence, merge_into
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault


def test_errors_without_count_preserve_partial_rows_at_adapter_boundary():
    value = {"success": True, "items": [{"title": "available"}],
             "errors": ["source A: HTTP 429", {"source": "B", "status": 503}]}
    envelope = {"success": True, "value": value}
    merge_into(value, envelope)
    with pytest.raises(Fault) as failure:
        decode_envelope(envelope, {"value_path": "/value"})
    assert failure.value.code == "PARTIAL_SOURCE"
    assert failure.value.partial == value
    assert failure.value.details["completion"][0]["errors"] == value["errors"]


@pytest.mark.parametrize("value", [
    {"success": True, "errors": [], "items": []},
    {"success": True, "items": [{"errors": ["ordinary business field"]}]},
    {"success": True, "value": {"errors": ["typed business value"]}},
])
def test_empty_errors_and_business_values_are_not_failure_envelopes(value):
    assert completion_evidence(value) == []
    assert decode_envelope(value, {"value_path": ""})[0] == value


def test_repeated_completion_summary_does_not_duplicate_error_evidence():
    failure = {"errors": ["source unavailable"]}
    evidence = completion_evidence(failure)
    repeated = completion_evidence({**failure, "incomplete_steps": evidence})
    assert len(repeated) == 1 and repeated[0]['errors'] == failure['errors']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
