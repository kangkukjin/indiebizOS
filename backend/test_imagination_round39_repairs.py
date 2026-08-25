"""39회차 상상훈련 — groupby 집계의 결측·무관측 의미 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round39_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_MISSING = object()
_VALUE_SHAPES = [
    ("clean_int", [10, 20], (2, 2, 30, 15, 10, 20)),
    ("numeric_text", ["10", "20"], (2, 2, 30, 15, 10, 20)),
    ("comma_numeric", ["1,000", "2,000"], (2, 2, 3000, 1500, 1000, 2000)),
    ("missing", [10, _MISSING], (2, 1, 10, 10, 10, 10)),
    ("null", [10, None], (2, 1, 10, 10, 10, 10)),
    ("nonnumeric", [10, "N/A"], (2, 2, 10, 10, 10, 10)),
    ("boolean", [10, False], (2, 2, 10, 10, 10, 10)),
    ("all_invalid", [None, _MISSING, "N/A"], (3, 1, None, None, None, None)),
]


def _rows(values):
    rows = []
    for value in values:
        row = {"group": "G"}
        if value is not _MISSING:
            row["value"] = value
        rows.append(row)
    return rows


def _first_row(result):
    assert result.get("success", True) is not False, result
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        table = result.get("table") or {}
        columns, rows = table.get("columns"), table.get("rows")
    assert columns and rows, result
    return dict(zip(columns, rows[0]))


@pytest.mark.parametrize("name,values,expected", _VALUE_SHAPES)
def test_round39_matrix_preserves_observation_meaning(
        data_ops, name, values, expected):
    """원 48칸(8값 품질×6집계)을 재생해 정상 숫자 속 침묵 왜곡을 막는다."""
    prev = {"items": _rows(values)}
    row_count = _first_row(data_ops._op_groupby(prev, {
        "by": "group", "agg": "count",
    }))["count"]
    combined = _first_row(data_ops._op_groupby(prev, {
        "by": "group",
        "agg": {
            "field_count": ["count", "value"],
            "sum": ["sum", "value"],
            "avg": ["avg", "value"],
            "min": ["min", "value"],
            "max": ["max", "value"],
        },
    }))
    actual = (row_count, combined["field_count"], combined["sum"],
              combined["avg"], combined["min"], combined["max"])
    assert actual == expected, (name, actual, expected)


@pytest.mark.parametrize("agg", [
    {"observed": ["count", "never_exists"]},
    {"never_exists": "count"},
])
def test_explicit_count_rejects_a_field_absent_from_every_row(data_ops, agg):
    """명시 field count의 원본열은 장식이 아니며 다른 집계처럼 실존해야 한다."""
    result = data_ops._op_groupby(
        {"items": [{"group": "G"}, {"group": "G"}]},
        {"by": "group", "agg": agg},
    )
    assert result.get("success") is False, result
    assert "never_exists" in result.get("error", ""), result


def test_zero_is_a_number_but_no_numeric_observation_is_null(data_ops):
    """실제 0과 관측 부재를 접지 않는다. false/N/A는 count에는 실존한다."""
    with_zero = _first_row(data_ops._op_groupby(
        {"items": _rows([0, None])},
        {"by": "group", "agg": {
            "count": ["count", "value"], "sum": ["sum", "value"],
            "avg": ["avg", "value"], "min": ["min", "value"],
            "max": ["max", "value"],
        }},
    ))
    assert with_zero == {
        "group": "G", "count": 1, "sum": 0, "avg": 0,
        "min": 0, "max": 0,
    }

    no_number = _first_row(data_ops._op_groupby(
        {"items": _rows([False, "N/A", None, _MISSING])},
        {"by": "group", "agg": {
            "count": ["count", "value"], "sum": ["sum", "value"],
            "avg": ["avg", "value"], "min": ["min", "value"],
            "max": ["max", "value"],
        }},
    ))
    assert no_number == {
        "group": "G", "count": 2, "sum": None, "avg": None,
        "min": None, "max": None,
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
