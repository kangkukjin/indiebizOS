"""값 의미론 수렴 감사 — 연산별 복제 구현의 재발을 횡단 불변식으로 막는다."""

import importlib.util
from pathlib import Path

import pytest

from ibl.api_transforms import _apply_sort
from ibl.ibl_predicates import Evaluator, PredicateError


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
    assert Evaluator.compare("==", left, right)
    assert not Evaluator.compare("!=", left, right)


def test_structured_ordering_is_rejected_by_both_condition_languages(data_ops):
    with pytest.raises(data_ops._wdsl._WhereError):
        data_ops._wdsl._apply_op(">", {"a": 1}, {"a": 0})
    with pytest.raises(PredicateError):
        Evaluator.compare(">", {"a": 1}, {"a": 0})


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
