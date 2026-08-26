"""그룹 키 JSON 타입×통화 전달 경로 행렬 (Codex r40 흡수)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")
_MISSING = object()


def _load_handler():
    spec = importlib.util.spec_from_file_location("round40_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_KEY_CASES = [
    ("text_equal", ["A", "A"], 1, [2]),
    ("text_distinct", ["A", "a"], 2, [1, 1]),
    ("zero_false", [0, False], 2, [1, 1]),
    ("one_true", [1, True], 2, [1, 1]),
    ("null_missing", [None, _MISSING], 1, [2]),
    ("list_equal", [["A"], ["A"]], 1, [2]),
    ("dict_equal", [{"a": 1, "b": 2}, {"b": 2, "a": 1}], 1, [2]),
    ("list_distinct", [["A"], ["B"]], 2, [1, 1]),
]


def _rows(values):
    rows = []
    for index, value in enumerate(values):
        row = {"id": index}
        if value is not _MISSING:
            row["group"] = value
        rows.append(row)
    return rows


def _table(rows):
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return {"columns": columns,
            "rows": [[row.get(column) for column in columns] for row in rows]}


def _carriers(rows):
    return {
        "root": rows,
        "items": {"items": rows},
        "table": _table(rows),
        "data": {"data": rows},
        "results": {"results": rows},
        "nested_data": {"data": {"records": rows}},
    }


def _result_rows(result):
    table = result.get("table") if isinstance(result.get("table"), dict) else result
    return table.get("rows") or []


@pytest.mark.parametrize("name,values,group_count,member_counts", _KEY_CASES)
def test_round40_matrix_preserves_json_key_identity_across_six_carriers(
        data_ops, name, values, group_count, member_counts):
    """훈련의 48칸(8키 모양×6전달 경로)을 그대로 재생한다."""
    for carrier, prev in _carriers(_rows(values)).items():
        result = data_ops._op_groupby(prev, {"by": "group"})
        assert result.get("success", True) is not False, (name, carrier, result)
        rows = _result_rows(result)
        assert len(rows) == group_count, (name, carrier, rows)
        assert [row[1] for row in rows] == member_counts, (name, carrier, rows)


def test_booleans_do_not_alias_numbers(data_ops):
    result = data_ops._op_groupby(
        {"items": _rows([0, False, 1, True])}, {"by": "group"})
    keys = [row[0] for row in _result_rows(result)]
    assert [(type(key), key) for key in keys] == [
        (int, 0), (bool, False), (int, 1), (bool, True)]


def test_integer_and_equivalent_float_keep_existing_numeric_identity(data_ops):
    result = data_ops._op_groupby(
        {"items": _rows([1, 1.0])}, {"by": "group"})
    assert _result_rows(result) == [[1, 2]]


def test_structured_keys_use_canonical_json_identity(data_ops):
    values = [
        {"outer": [1, {"a": True, "b": None}]},
        {"outer": [1.0, {"b": None, "a": True}]},
    ]
    result = data_ops._op_groupby({"items": _rows(values)}, {"by": "group"})
    assert _result_rows(result) == [[values[0], 2]]


def test_default_row_count_and_explicit_field_count_remain_distinct(data_ops):
    rows = _rows([None, _MISSING])
    row_count = data_ops._op_groupby({"items": rows}, {"by": "group"})
    field_count = data_ops._op_groupby(
        {"items": rows}, {"by": "group", "agg": {"관측": ["count", "group"]}})
    assert _result_rows(row_count) == [[None, 2]]
    assert _result_rows(field_count) == [[None, 0]]


def test_nonfinite_keys_are_strict_json_with_an_honest_coercion(data_ops):
    rows = _rows([float("nan"), float("nan"), float("inf"), -float("inf")])
    result = data_ops._op_groupby({"items": rows}, {"by": "group"})
    assert _result_rows(result) == [["NaN", 2], ["Infinity", 1], ["-Infinity", 1]]
    assert result.get("group_key_coercions")
    assert "엄격한 JSON" in result.get("warning", "")
    json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
