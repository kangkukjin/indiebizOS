"""값 의미론 수렴 감사 — 연산별 복제 구현의 재발을 횡단 불변식으로 막는다."""

import importlib.util
from pathlib import Path

import pytest

from ibl.api_transforms import _apply_sort
from common.expression_ops import binary
from common.expression_ir import Fault
from common.value_semantics import numeric_value


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("value_semantics_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


def test_structural_equality_converges_across_value_surfaces(data_ops):
    left = {"a": [{"x": 1, "y": "YES"}], "b": 2}
    right = {"b": 2, "a": [{"y": "YES", "x": 1}]}
    assert data_ops._group_identity(left) == data_ops._group_identity(right)
    assert data_ops._norm(left) == data_ops._norm(right)
    assert data_ops._num_eq(left, right)
    assert binary("==", left, right)
    assert not binary("!=", left, right)


def test_structured_ordering_is_rejected_by_both_condition_languages(data_ops):
    with pytest.raises(data_ops._wdsl._WhereError):
        data_ops._wdsl._apply_op(">", {"a": 1}, {"a": 0})
    with pytest.raises(Fault):
        binary(">", {"a": 1}, {"a": 0})


@pytest.mark.parametrize(
    "descending,expected",
    [
        (False, ["n2", "n3", "n10", "text", "missing"]),
        (True, ["n10", "n3", "n2", "text", "missing"]),
    ],
)
def test_numeric_auto_sort_converges_and_keeps_missing_last(
        data_ops, descending, expected):
    rows = [
        {"id": "missing", "v": None},
        {"id": "n10", "v": 10},
        {"id": "n2", "v": 2},
        {"id": "n3", "v": "3"},
        {"id": "text", "v": "x"},
    ]
    data_sorted = data_ops._sort_records(rows, "v", descending)
    response_sorted = _apply_sort(
        rows, {"by": "v", "order": "desc" if descending else "asc"})
    assert [row["id"] for row in data_sorted] == expected
    assert [row["id"] for row in response_sorted] == expected


_NUMBER_SHAPES = [
    ("native_int", 2, 10),
    ("numeric_text", "2", "10"),
    ("comma_text", "2,000", "10,000"),
    ("decimal_text", "2.5", "10.5"),
    ("negative_text", "-10", "-2"),
    ("percent_text", "2%", "10%"),
    ("spaced_text", " 2 ", " 10 "),
    ("leading_zero", "02", "010"),
]

_INTEGER_SHAPES = [
    ("float_boundary", "9007199254740992", "9007199254740993"),
    ("large_positive", "999999999999999999999999999999", "1000000000000000000000000000000"),
    ("large_negative", "-1000000000000000000000000000000", "-999999999999999999999999999999"),
    ("fifty_digits", "10000000000000000000000000000000000000000000000000",
     "10000000000000000000000000000000000000000000000001"),
    ("leading_zero", "09007199254740992", "09007199254740993"),
    ("comma_text", "9,007,199,254,740,992", "9,007,199,254,740,993"),
    ("explicit_plus", "+9007199254740992", "+9007199254740993"),
    ("percent_text", "9007199254740992%", "9007199254740993%"),
]

@pytest.mark.parametrize("name,low,high", _NUMBER_SHAPES + _INTEGER_SHAPES)
def test_numeric_ordering_surfaces_preserve_notation_and_precision(
        data_ops, name, low, high):
    """숫자 표기 8종과 큰 정수 8종의 순서 계약을 같은 소비자 행렬로 검사한다."""
    high_row = {"v": high}
    low_row = {"v": low}
    for op in ("gt", ">"):
        result = data_ops._op_filter(
            {"items": [high_row]},
            {"where": {"field": "v", "op": op, "value": low}},
        )
        assert len(result.get("items") or []) == 1, (name, op, result)
    result = data_ops._op_filter(
        {"items": [low_row]},
        {"where": {"field": "v", "op": "lt", "value": high}},
    )
    assert len(result.get("items") or []) == 1, (name, "lt", result)

    rows = [{"label": "high", "v": high}, {"label": "low", "v": low}]
    assert data_ops._sort_records(rows, "v")[0]["label"] == "low", name
    assert data_ops._sort_records(rows, "v", True)[0]["label"] == "high", name
    assert binary(">", high, low), name

def test_percent_numeric_policy_has_one_source_and_reaches_response_sort():
    assert numeric_value("10%") == 10
    assert numeric_value(" 2.5% ") == 2.5
    assert numeric_value("%") is None
    rows = [{"label": "high", "v": "10%"}, {"label": "low", "v": "2%"}]
    assert _apply_sort(rows, {"by": "v"})[0]["label"] == "low"
    assert _apply_sort(rows, {"by": "v", "order": "desc"})[0]["label"] == "high"

@pytest.mark.parametrize("value", [
    "nan", "NaN", "inf", "+Infinity", "-inf", "1e309",
    float("nan"), float("inf"),
])
def test_non_finite_values_are_not_numeric_observations(data_ops, value):
    """JSON에 유한 숫자로 실을 수 없는 값은 집계·숫자 버킷에 들어가지 않는다."""
    assert numeric_value(value) is None
    for op in ("sum", "avg", "min", "max"):
        observed, skipped, error = data_ops._aggregate_members(op, [{"v": value}], "v")
        assert observed is None and skipped == 1 and error is None

def test_non_finite_text_has_deterministic_cross_surface_sorting(data_ops):
    rows = [
        {"id": "nan", "v": "nan"},
        {"id": "ten", "v": 10},
        {"id": "inf", "v": "inf"},
        {"id": "two", "v": 2},
    ]
    expected = ["two", "ten", "inf", "nan"]
    assert [row["id"] for row in data_ops._sort_records(rows, "v")] == expected
    assert [row["id"] for row in _apply_sort(rows, {"by": "v"})] == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
