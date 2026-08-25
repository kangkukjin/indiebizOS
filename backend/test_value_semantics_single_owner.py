"""값 의미론 단일 소유권·대수 불변식 가드."""

import ast
import importlib.util
from pathlib import Path

import pytest

from common import value_semantics as semantics
from ibl import ibl_predicates
from ibl.ibl_predicates import Evaluator, PredicateError


_ROOT = Path(__file__).resolve().parent.parent
_HANDLER = _ROOT / "data/packages/installed/tools/data-ops/handler.py"
_WHERE = _ROOT / "data/packages/installed/tools/data-ops/where_dsl.py"
_PREDICATES = _ROOT / "backend/ibl/ibl_predicates.py"
_GROUP_KEYS = _ROOT / "data/packages/installed/tools/data-ops/group_keys.py"


def _load_handler():
    spec = importlib.util.spec_from_file_location("single_owner_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_EQUAL_PAIRS = [
    (0, "0"),
    ("1,000", 1000),
    ("YES", "yes."),
    (False, "false"),
    ({"a": 1, "b": ["X"]}, {"b": ["x"], "a": "1"}),
]


@pytest.mark.parametrize("left,right", _EQUAL_PAIRS)
def test_condition_equality_has_one_answer_on_every_surface(data_ops, left, right):
    assert semantics.values_equal(left, right)
    assert semantics.values_equal(right, left), "동등성은 대칭이어야 한다"
    assert data_ops._num_eq(left, right)
    assert Evaluator.compare("==", left, right)
    assert not Evaluator.compare("!=", left, right)
    order = semantics.compare_order(left, right)
    if order is not None:
        assert order is semantics.OrderResult.EQUAL


_ORDERABLE = [
    -10, "-2", 0, "2%", 10, "10.5", "1,000",
]


def test_numeric_order_is_antisymmetric_transitive_and_equal_consistent():
    for left in _ORDERABLE:
        assert semantics.compare_order(left, left) is semantics.OrderResult.EQUAL
        assert semantics.values_equal(left, left)
        for right in _ORDERABLE:
            lr = semantics.compare_order(left, right)
            rl = semantics.compare_order(right, left)
            assert lr is not None and rl is not None
            assert int(lr) == -int(rl), (left, right, lr, rl)
            assert (lr is semantics.OrderResult.EQUAL) == semantics.values_equal(left, right)
    for low, middle, high in zip(_ORDERABLE, _ORDERABLE[1:], _ORDERABLE[2:]):
        assert semantics.compare_order(low, middle) < 0
        assert semantics.compare_order(middle, high) < 0
        assert semantics.compare_order(low, high) < 0


_TEXT_ORDERABLE = [" 2026-01-01 ", "2026-06-01", " 2026-12-31"]


def test_text_order_and_sort_share_the_same_normalized_order(data_ops):
    rows = [{"v": value} for value in reversed(_TEXT_ORDERABLE)]
    expected = [value.strip() for value in _TEXT_ORDERABLE]
    assert [row["v"].strip() for row in data_ops._sort_records(rows, "v")] == expected
    for low, high in zip(_TEXT_ORDERABLE, _TEXT_ORDERABLE[1:]):
        assert semantics.compare_order(low, high) < 0
        assert data_ops._num_cmp(low, high) < 0
        assert Evaluator.compare("<", low, high)


@pytest.mark.parametrize("left,right", [
    (False, 0),
    (10, "N/A"),
    ({"a": 1}, {"a": 2}),
    (None, 0),
    ([1], [2]),
])
def test_undefined_order_is_never_fabricated_by_an_adapter(data_ops, left, right):
    assert semantics.compare_order(left, right) is None
    with pytest.raises(data_ops._wdsl._WhereError):
        data_ops._num_cmp(left, right)
    with pytest.raises(PredicateError):
        Evaluator.compare(">", left, right)


def test_group_relation_and_numeric_observation_are_common_exports(data_ops):
    assert data_ops._group_keys.group_identity is semantics.group_identity
    assert data_ops._group_keys.relation_identity is semantics.relation_identity
    assert semantics.group_identity(False) != semantics.group_identity(0)
    assert semantics.group_identity(0) != semantics.group_identity("0")
    assert semantics.relation_identity(0) == semantics.relation_identity("0")
    assert semantics.relation_identity({"a": 1, "b": 2}) == semantics.relation_identity({"b": 2, "a": 1})
    assert semantics.numeric_observations([1, "2", False, None, "N/A", "inf"]) == [1, 2]


def test_adapters_only_translate_common_results(monkeypatch, data_ops):
    marker = object()
    monkeypatch.setattr(data_ops._wdsl, "values_equal", lambda _a, _b: marker)
    assert data_ops._num_eq("a", "b") is marker
    monkeypatch.setattr(ibl_predicates, "values_equal", lambda _a, _b: True)
    assert Evaluator.compare("==", "a", "b") is True

    monkeypatch.setattr(data_ops._wdsl, "compare_order",
                        lambda _a, _b: semantics.OrderResult.GREATER)
    assert data_ops._num_cmp("a", "b") == 1
    monkeypatch.setattr(ibl_predicates, "compare_order",
                        lambda _a, _b: semantics.OrderResult.LESS)
    assert Evaluator.compare("<", "a", "b") is True


def test_no_consumer_can_reintroduce_private_value_policy():
    forbidden_defs = {
        "_scalar_equal", "_scalar_num_eq", "_group_scalar_identity",
        "_relation_scalar_identity", "_numeric_observations",
    }
    handler_path = _ROOT / "data/packages/installed/tools/data-ops/handler.py"
    for path in (_WHERE, _PREDICATES, _GROUP_KEYS, handler_path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        local_defs = {node.name for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert not (local_defs & forbidden_defs), (path, local_defs & forbidden_defs)

    group_source = _GROUP_KEYS.read_text(encoding="utf-8")
    assert "from common.value_semantics import group_identity, relation_identity" in group_source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
