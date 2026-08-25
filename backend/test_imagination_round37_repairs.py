"""37회차 상상훈련 — 희소 행 비교 의미의 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest


_WHERE_DSL = (Path(__file__).resolve().parent.parent / "data" / "packages" /
              "installed" / "tools" / "data-ops" / "where_dsl.py")


def _load_where_dsl():
    spec = importlib.util.spec_from_file_location("round37_where_dsl", _WHERE_DSL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def wdsl():
    return _load_where_dsl()


_VALUE_SHAPES = [
    (350000000, 400000000, 420000000, "400000000"),
    (199.5, 200.5, 201.5, "200.5"),
    ("70", "80", "90", "80"),
    ("900", "1,000", "1,100", "1000"),
    (-5, 0, 5, "0"),
    (0.1, 0.2, 0.3, "0.2"),
    (9000000000000, 10000000000000, 11000000000000, "10000000000000"),
    ("009", "010", "011", "10"),
]

_COMPARISONS = [
    ("==", {"equal"}), ("eq", {"equal"}),
    ("!=", {"low", "high"}), ("ne", {"low", "high"}),
    ("<", {"low"}), ("lt", {"low"}),
    ("<=", {"low", "equal"}), ("le", {"low", "equal"}),
    (">", {"high"}), ("gt", {"high"}),
    (">=", {"equal", "high"}), ("ge", {"equal", "high"}),
]


@pytest.mark.parametrize("low,equal,high,right", _VALUE_SHAPES)
def test_round37_matrix_excludes_missing_and_null_rows(
        wdsl, low, equal, high, right):
    """원래 96칸(12연산×8값 모양)을 그대로 재생해 결측 48칸 누출을 막는다."""
    rows = [
        {"id": "low", "value": low},
        {"id": "equal", "value": equal},
        {"id": "high", "value": high},
        {"id": "missing"},
        {"id": "null", "value": None},
    ]
    for op, expected in _COMPARISONS:
        matched = {row["id"] for row in rows
                   if wdsl._match(row, f"value {op} {right}")}
        assert matched == expected, (op, right, matched)


@pytest.mark.parametrize("op", ["!=", "ne", "<", "lt", "<=", "le",
                                       ">", "gt", ">=", "ge"])
@pytest.mark.parametrize("row", [{"id": "missing"}, {"id": "null", "value": None}])
def test_null_rejection_is_shared_by_string_structured_and_list_forms(wdsl, op, row):
    """파서 형식별 특례가 아니라 비교 관문 한 벌의 계약이어야 한다."""
    conditions = [
        f"value {op} 10",
        {"field": "value", "op": op, "value": 10},
        [{"field": "value", "op": op, "value": 10}],
    ]
    assert all(wdsl._match(row, condition) is False for condition in conditions)


def test_null_equality_and_non_null_query_remain_available(wdsl):
    """수리 범위를 넘겨 결측을 찾는 구조형 동등 비교까지 죽이지 않는다."""
    missing_row = {}
    null_row = {"value": None}
    value_row = {"value": 10}
    equals_null = {"field": "value", "op": "eq", "value": None}
    differs_from_null = {"field": "value", "op": "ne", "value": None}

    assert wdsl._match(missing_row, equals_null) is True
    assert wdsl._match(null_row, equals_null) is True
    assert wdsl._match(value_row, equals_null) is False
    assert wdsl._match(missing_row, differs_from_null) is False
    assert wdsl._match(null_row, differs_from_null) is False
    assert wdsl._match(value_row, differs_from_null) is True


def test_order_comparison_with_null_target_is_undecidable(wdsl):
    for op in ("<", "lt", "<=", "le", ">", "gt", ">=", "ge"):
        assert wdsl._match(
            {"value": 10}, {"field": "value", "op": op, "value": None}
        ) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
