"""42회차 상상훈련 — 조건 DSL 구조 동등성 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round42_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_VALUE_SHAPES = [
    ("strings", "A", "A", True),
    ("dict_same", {"a": 1, "b": 2}, {"a": 1, "b": 2}, True),
    ("dict_reordered", {"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
    ("nested_reordered", {"a": [{"x": 1, "y": 2}]},
     {"a": [{"y": 2, "x": 1}]}, True),
    ("list_equal", ["A", 1], ["A", 1], True),
    ("list_reordered", ["A", 1], [1, "A"], False),
    ("false_zero", False, 0, False),
    ("number_text", 0, "0", True),
]


def _count(result):
    assert result.get("success", True) is not False, result
    return len(result.get("items") or [])


@pytest.mark.parametrize("name,left,right,same", _VALUE_SHAPES)
def test_round42_matrix_preserves_structural_condition_equality(
        data_ops, name, left, right, same):
    """원 48칸(8값 모양×6조건 표기)을 handler 계약으로 재생한다."""
    conditions = {
        "shorthand_eq": {"k": right},
        "explicit_eq": {"field": "k", "op": "eq", "value": right},
        "symbol_eq": {"field": "k", "op": "==", "value": right},
        "explicit_ne": {"field": "k", "op": "ne", "value": right},
        "symbol_ne": {"field": "k", "op": "!=", "value": right},
        "list_eq": [
            {"field": "k", "op": "eq", "value": right},
            {"guard": "yes"},
        ],
    }
    previous = {"items": [{"k": left, "guard": "yes"}]}
    for path, condition in conditions.items():
        actual = _count(data_ops._op_filter(previous, {"where": condition}))
        equality = path not in ("explicit_ne", "symbol_ne")
        expected = 1 if same == equality else 0
        assert actual == expected, (name, path, actual, expected)


def test_structural_conditions_recurse_existing_scalar_equality(data_ops):
    left = {"amount": "1,000", "nested": [{"x": "YES"}]}
    right = {"nested": [{"x": "yes"}], "amount": 1000}
    assert data_ops._num_eq(left, right)
    assert data_ops._num_eq({"A": 1, "a": 2}, {"a": 2, "A": 1})
    assert not data_ops._num_eq(["A", 1], [1, "A"])
    assert not data_ops._num_eq(False, 0)
    assert not data_ops._num_eq({"a": 1}, "{'a': 1}")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
