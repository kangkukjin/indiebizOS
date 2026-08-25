"""44회차 상상훈련 — 숫자 정밀도·비유한수 경계 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest

from common.value_semantics import numeric_value
from ibl.api_transforms import _apply_sort
from ibl.ibl_predicates import Evaluator


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round44_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


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


@pytest.mark.parametrize("name,low,high", _INTEGER_SHAPES)
def test_round44_matrix_preserves_integer_order_across_six_surfaces(
        data_ops, name, low, high):
    """원 48칸(8정수 표기×6순서 표면)에서 float 정밀도 소실을 막는다."""
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
    assert Evaluator.compare(">", high, low), name


@pytest.mark.parametrize("value", [
    "nan", "NaN", "inf", "+Infinity", "-inf", "1e309",
    float("nan"), float("inf"),
])
def test_non_finite_values_are_not_numeric_observations(data_ops, value):
    """JSON에 유한 숫자로 실을 수 없는 값은 집계·숫자 버킷에 들어가지 않는다."""
    assert numeric_value(value) is None
    assert data_ops._agg_sum([value]) is None
    assert data_ops._agg_avg([value]) is None
    assert data_ops._agg_min([value]) is None
    assert data_ops._agg_max([value]) is None


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
