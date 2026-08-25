"""45회차 상상훈련 — 혼합 스칼라·텍스트 공백 순서 경계 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest

from ibl.api_transforms import _apply_sort
from ibl.ibl_predicates import Evaluator, PredicateError


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round45_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_MIXED_SCALARS = [
    ("false_zero", False, 0),
    ("true_two", True, 2),
    ("int_text", 10, "N/A"),
    ("text_int", "N/A", 10),
    ("float_text", 2.5, "unknown"),
    ("zero_date", 0, "2026-08-25"),
    ("negative_empty", -1, ""),
    ("int_infinity_text", 1, "Infinity"),
]


@pytest.mark.parametrize("name,left,right", _MIXED_SCALARS)
def test_round45_matrix_rejects_mixed_scalar_order_across_six_surfaces(
        data_ops, name, left, right):
    """원 48칸(8혼합값×6조건 표면)이 표시 문자열 순서로 내려앉지 않는다."""
    previous = {"items": [{"v": left}]}
    conditions = [
        {"field": "v", "op": ">", "value": right},
        {"field": "v", "op": "gt", "value": right},
        [{"field": "v", "op": "<=", "value": right}],
    ]
    for condition in conditions:
        result = data_ops._op_filter(previous, {"where": condition})
        assert result.get("success") is False, (name, condition, result)
        assert "비교" in result.get("error", ""), (name, condition, result)

    for op in (">", "le"):
        with pytest.raises(data_ops._wdsl._WhereError):
            data_ops._wdsl._apply_op(op, left, right)
    with pytest.raises(PredicateError):
        Evaluator.compare(">", left, right)


_TEXT_BOUNDARIES = [
    ("plain", "2026-01-01", "2026-12-31"),
    ("left_space", " 2026-01-01", "2026-12-31"),
    ("right_space", "2026-01-01", " 2026-12-31"),
    ("both_space", " 2026-01-01 ", " 2026-12-31 "),
    ("left_tab", "\t2026-01-01", "2026-12-31"),
    ("right_tab", "2026-01-01", "2026-12-31\t"),
    ("left_newline", "\n2026-01-01", "2026-12-31"),
    ("mixed_whitespace", " \t2026-01-01\n", "\n2026-12-31 \t"),
]


@pytest.mark.parametrize("name,low,high", _TEXT_BOUNDARIES)
def test_text_whitespace_order_converges_across_filter_sort_and_predicate(
        data_ops, name, low, high):
    """텍스트 경계 공백은 여섯 순서 표면에서 같은 의미를 갖는다."""
    for op in ("gt", ">"):
        result = data_ops._op_filter(
            {"items": [{"v": high}]},
            {"where": {"field": "v", "op": op, "value": low}},
        )
        assert len(result.get("items") or []) == 1, (name, op, result)
    result = data_ops._op_filter(
        {"items": [{"v": low}]},
        {"where": {"field": "v", "op": "lt", "value": high}},
    )
    assert len(result.get("items") or []) == 1, (name, "lt", result)

    rows = [{"id": "high", "v": high}, {"id": "low", "v": low}]
    assert data_ops._sort_records(rows, "v")[0]["id"] == "low", name
    assert _apply_sort(rows, {"by": "v", "order": "desc"})[0]["id"] == "high", name
    assert Evaluator.compare(">", high, low), name


def test_string_where_form_rejects_native_number_against_text(data_ops):
    result = data_ops._op_filter(
        {"items": [{"v": 10}]}, {"where": "v > N/A"})
    assert result.get("success") is False, result
    assert "int" in result.get("error", "") and "str" in result.get("error", "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
