"""집계 관측의 정직성 — 유한 관측만 세고 제외를 자백한다 (Codex r39 흡수)."""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")
_MISSING = object()


def _load_handler():
    spec = importlib.util.spec_from_file_location("round39_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_VALUE_SHAPES = [
    ("int", [10, 20], [30.0, 15.0, 10.0, 20.0, 2, 2]),
    ("float", [1.5, 2.5], [4.0, 2.0, 1.5, 2.5, 2, 2]),
    ("numeric_text", ["10", "20"], [30.0, 15.0, 10.0, 20.0, 2, 2]),
    ("comma_text", ["1,000", "2,000"], [3000.0, 1500.0, 1000.0, 2000.0, 2, 2]),
    ("zero", [0, 0], [0.0, 0.0, 0.0, 0.0, 2, 2]),
    ("null", [10, None], [10.0, 10.0, 10.0, 10.0, 1, 2]),
    ("missing", [10, _MISSING], [10.0, 10.0, 10.0, 10.0, 1, 2]),
    ("invalid", [10, "무료"], [10.0, 10.0, 10.0, 10.0, 2, 2]),
]

_AGG_CASES = [
    ("sum", {"값": ["sum", "v"]}),
    ("avg", {"값": ["avg", "v"]}),
    ("min", {"값": ["min", "v"]}),
    ("max", {"값": ["max", "v"]}),
    ("count_field", {"값": ["count", "v"]}),
    ("count_rows", None),
]


def _rows(values):
    out = []
    for index, value in enumerate(values):
        row = {"group": "A", "id": index}
        if value is not _MISSING:
            row["v"] = value
        out.append(row)
    return out


def _value(result):
    table = result.get("table") if isinstance(result.get("table"), dict) else result
    return table["rows"][0][1]


@pytest.mark.parametrize("shape,values,expected", _VALUE_SHAPES)
def test_round39_matrix_uses_observed_values_for_six_aggregates(
        data_ops, shape, values, expected):
    """훈련의 48칸(8값 모양×6집계)을 그대로 재생한다."""
    for index, (op_name, agg) in enumerate(_AGG_CASES):
        params = {"by": "group"}
        if agg is not None:
            params["agg"] = agg
        result = data_ops._op_groupby({"items": _rows(values)}, params)
        assert result.get("success", True) is not False, (shape, op_name, result)
        assert _value(result) == expected[index], (shape, op_name, result)


@pytest.mark.parametrize("value", [None, "무료", float("nan"), float("inf"), -float("inf")])
def test_numeric_aggregates_report_and_exclude_unusable_values(data_ops, value):
    rows = [{"group": "A", "v": 10}, {"group": "A", "v": value}]
    for op in ("sum", "avg", "min", "max"):
        result = data_ops._op_groupby(
            {"items": rows}, {"by": "group", "agg": {"값": [op, "v"]}})
        assert _value(result) == 10.0, (op, value, result)
        assert result.get("aggregation_skips"), (op, value, result)
        assert "제외" in result.get("warning", ""), (op, value, result)


def test_all_unusable_numeric_values_are_unknown_not_zero(data_ops):
    rows = [{"group": "A", "v": None}, {"group": "A", "v": "무료"}]
    for op in ("sum", "avg", "min", "max"):
        result = data_ops._op_groupby(
            {"items": rows}, {"by": "group", "agg": {"값": [op, "v"]}})
        assert _value(result) is None, (op, result)


def test_explicit_count_differs_from_row_count(data_ops):
    rows = [{"group": "A", "v": 10}, {"group": "A", "v": None}, {"group": "A"}]
    field_count = data_ops._op_groupby(
        {"items": rows}, {"by": "group", "agg": {"값": ["count", "v"]}})
    row_count = data_ops._op_groupby({"items": rows}, {"by": "group"})
    assert _value(field_count) == 1
    assert _value(row_count) == 3


def test_numeric_results_are_finite_json_numbers(data_ops):
    rows = [{"group": "A", "v": 10}, {"group": "A", "v": "NaN"}]
    result = data_ops._op_groupby(
        {"items": rows}, {"by": "group", "agg": {"값": ["avg", "v"]}})
    assert math.isfinite(_value(result))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
