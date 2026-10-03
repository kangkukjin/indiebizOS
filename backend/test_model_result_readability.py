"""Readable rows and direct final-body reads without changing stored values."""
import copy
import json

import boot_paths  # noqa: F401
import pytest

from model_value_preview import preview_value


def test_multiple_long_fields_keep_complete_rows_and_explicit_coverage():
    rows = [{"source": "https://example.test/" + str(i) + "a" * 150,
             "body": "본문 문장 " * 120} for i in range(77)]
    original = copy.deepcopy(rows)
    shown, meta = preview_value(rows, 2500, "reference")
    assert 0 < len(shown) < len(rows)
    assert shown == rows[:len(shown)]
    assert len(json.dumps(shown, ensure_ascii=False)) <= 2500
    omission = next(c for c in meta["changes"] if c["kind"] == "list")
    assert omission["shown"] == len(shown) and omission["total"] == len(rows)
    assert omission["read_args"]["path"] == ["value"]
    assert rows == original


def test_one_long_field_keeps_candidate_overview():
    rows = [{"id": i, "date": "2026-10-03", "description": "detail " * 500}
            for i in range(10)]
    shown, meta = preview_value(rows, 2500, "reference")
    assert len(shown) == len(rows)
    assert [row["id"] for row in shown] == list(range(10))
    assert all(row["date"] == "2026-10-03" for row in shown)
    assert meta and len(json.dumps(shown, ensure_ascii=False)) <= 2500


def test_oversized_first_row_stays_bounded_and_readable():
    rows = [{"a": "a" * 10000, "b": "b" * 10000}] * 5
    shown, meta = preview_value(rows, 500, "reference")
    assert len(shown) == 1 and shown[0]
    assert len(json.dumps(shown, ensure_ascii=False)) <= 500
    assert any(c["kind"] == "text" for c in meta["changes"])


@pytest.mark.parametrize("function", [True, False])
def test_function_body_one_read_preserves_input_and_execution_evidence(
        monkeypatch, tmp_path, function):
    import model_result_view as view
    from ibl_result_transport import provider_tool_result
    from supervision_store import TurnStore

    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    rows = [{"url": "https://example.test/" + str(i) + "a" * 140,
             "text": "complete paragraph " * 30} for i in range(35)]
    value = {"items": rows, "count": len(rows),
             "final_result": json.dumps({"items": rows}),
             "truncations": [{"scope": "selection", "reason": "requested_limit"}]}
    if function:
        value["_fn_result"] = True
    raw = {"edition": 2, "success": True, "source_complete": True, "value": value}
    before = copy.deepcopy(raw)
    shown = view.project_v2_result(raw)
    delivered = json.loads(provider_tool_result(json.dumps(shown, ensure_ascii=False)))
    ref = delivered["result_ref"]
    assert ref["read_args"]["path"] == (["value", "items"] if function else ["value"])
    page = view.read_result(ref["read_args"])
    assert page["read_scope"]["complete"]
    assert json.loads(page["text"]) == (rows if function else value)
    restored, _ = view.resolve_input_refs(ref["input_args"])
    assert restored["입력"] == value
    assert raw == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
