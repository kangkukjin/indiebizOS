"""40회차 상상훈련 — groupby 키의 타입·구조 정체성 회귀 시험."""

import importlib.util
import json
from pathlib import Path

import pytest


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round40_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_MISSING = object()
_KEY_SHAPES = [
    ("strings", "A", "B", False),
    ("number_text", 0, "0", False),
    ("false_zero", False, 0, False),
    ("true_one", True, 1, False),
    ("null_missing", None, _MISSING, True),
    ("blank_space", " ", "", False),
    ("equal_lists", ["A"], ["A"], True),
    ("equal_dicts", {"x": 1}, {"x": 1}, True),
]


def _rows(k1, k2):
    second = {"v": 20} if k2 is _MISSING else {"g": k2, "v": 20}
    return [{"g": k1, "v": 10}, second]


def _items(result):
    assert result.get("success", True) is not False, result
    if isinstance(result.get("items"), list):
        return result["items"]
    columns, rows = result.get("columns"), result.get("rows")
    table = result.get("table") if not columns else result
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def _tag(value):
    if value is None:
        return "null", None
    if isinstance(value, bool):
        return "bool", value
    if isinstance(value, (int, float)):
        return "number", float(value)
    if isinstance(value, str):
        return "string", value
    return type(value).__name__, json.dumps(value, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize("name,k1,k2,merged", _KEY_SHAPES)
def test_round40_matrix_preserves_key_identity_across_six_aggregates(
        data_ops, name, k1, k2, merged):
    """원 48칸(8키 모양×6집계)을 재생한다."""
    aggregates = [
        ("count", "count", (1, 1), 2),
        ({"out": ["count", "v"]}, "out", (1, 1), 2),
        ({"out": ["sum", "v"]}, "out", (10, 20), 30),
        ({"out": ["avg", "v"]}, "out", (10, 20), 15),
        ({"out": ["min", "v"]}, "out", (10, 20), 10),
        ({"out": ["max", "v"]}, "out", (10, 20), 20),
    ]
    for agg, column, split_values, merged_value in aggregates:
        got = _items(data_ops._op_groupby(
            {"items": _rows(k1, k2)}, {"by": "g", "agg": agg}))
        actual = [(_tag(row.get("g")), row[column]) for row in got]
        if merged:
            output_key = None if k2 is _MISSING else k1
            expected = [(_tag(output_key), merged_value)]
        else:
            expected = [(_tag(k1), split_values[0]), (_tag(k2), split_values[1])]
        assert actual == expected, (name, agg, actual, expected)


def test_structural_keys_are_recursive_and_dict_order_is_irrelevant(data_ops):
    rows = [
        {"g": {"a": [False, {"x": 1}], "b": 2}, "v": 10},
        {"g": {"b": 2, "a": [False, {"x": 1}]}, "v": 20},
        {"g": {"a": [0, {"x": 1}], "b": 2}, "v": 30},
        {"g": ["A", "B"], "v": 40},
        {"g": ["B", "A"], "v": 50},
    ]
    got = _items(data_ops._op_groupby(
        {"items": rows}, {"by": "g", "agg": {"sum": ["sum", "v"]}}))
    assert [row["sum"] for row in got] == [30, 30, 40, 50]
    assert got[0]["g"] == rows[0]["g"], "공개 그룹 키는 첫 원값을 보존해야 한다"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
