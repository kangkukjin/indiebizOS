"""43회차 상상훈련 — 숫자 표기 순서 의미론 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest

from common.value_semantics import numeric_value
from ibl.api_transforms import _apply_sort
from ibl.ibl_predicates import Evaluator, _num


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round43_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


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


@pytest.mark.parametrize("name,low,high", _NUMBER_SHAPES)
def test_round43_matrix_converges_numeric_ordering_surfaces(
        data_ops, name, low, high):
    """원 48칸(8숫자 표기×6순서 표면)을 내부 계약으로 재생한다."""
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


def test_percent_numeric_policy_has_one_source_and_reaches_response_sort():
    assert numeric_value("10%") == 10
    assert _num("10%") == numeric_value("10%")
    assert numeric_value(" 2.5% ") == 2.5
    assert numeric_value("%") is None
    rows = [{"label": "high", "v": "10%"}, {"label": "low", "v": "2%"}]
    assert _apply_sort(rows, {"by": "v"})[0]["label"] == "low"
    assert _apply_sort(rows, {"by": "v", "order": "desc"})[0]["label"] == "high"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
