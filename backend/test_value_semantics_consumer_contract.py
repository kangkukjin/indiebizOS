"""값 의미론 소비처 계약 — 조건·목표·응답변환 전 표면이 한 엔진의 답을 내는지.

Codex 흡수(원본 test_value_semantics_contract.py, refs/codex/absorb-20260826)를
정본 API(values_equal/compare_order/order_matches/numeric_value)로 번역한 판.
"""

import importlib.util
import inspect
import itertools
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from common import value_semantics as values
from common.safe_expr import as_num
from ibl.api_transforms import _apply_sort, _match_condition, _safe_compare
from ibl.ibl_predicates import Evaluator, PredicateError
from cognition.agent_goals import AgentGoalsMixin
from cognition.goal_evaluator import evaluate_range, select_case_branch


_ROOT = Path(__file__).resolve().parent.parent
_WHERE = (_ROOT / "data/packages/installed/tools/data-ops/where_dsl.py")

_GREATER = values.OrderResult.GREATER
_EQUAL = values.OrderResult.EQUAL


def _scalar_sort_key(value):
    return values.value_sort_key("v")({"v": value})


@pytest.fixture(scope="module")
def where_dsl():
    spec = importlib.util.spec_from_file_location("consumer_contract_where_dsl", _WHERE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("left,right,expected", [
    (1, "1", True),
    ("01", "1", True),
    (" A ", "a", True),
    (True, "true", True),
    (True, 1, False),
    (None, None, True),
    (None, "None", False),
    ({"a": 1, "b": [2]}, {"b": [2], "a": 1}, True),
    ({"a": 1}, {"a": "1"}, True),
    (9007199254740993, 9007199254740992, False),
    (float("nan"), float("nan"), False),
])
def test_equality_matrix_is_identical_in_filter_and_block_predicate(
        where_dsl, left, right, expected):
    assert values.values_equal(left, right) is expected
    assert where_dsl._apply_op("==", left, right) is expected
    assert Evaluator.compare("==", left, right) is expected


@pytest.mark.parametrize("left,right,order", [
    (10, "2", _GREATER),
    ("1,000", 1000, _EQUAL),
    ("10%", 9, _GREATER),
    ("2026-08-26", "2025-12-31", _GREATER),
    ("A", "a", _EQUAL),
])
def test_order_matrix_is_shared_by_all_comparable_consumers(
        where_dsl, left, right, order):
    assert values.compare_order(left, right) is order
    expected_ge = order in (_GREATER, _EQUAL)
    assert where_dsl._apply_op(">=", left, right) is expected_ge
    assert Evaluator.compare(">=", left, right) is expected_ge
    assert _safe_compare(left, right, ">=") is expected_ge


@pytest.mark.parametrize("left,right", [
    (True, False), (10, "abc"), ("10", "abc"), ({"a": 1}, {"a": 2}),
    (float("nan"), 10), (float("inf"), 10),
])
def test_undefined_order_is_preserved_until_each_surface_translates_it(
        where_dsl, left, right):
    # 공통 판정 불능(None)을 오류를 낼 수 있는 표면은 오류로, 낼 수 없는 표면은
    # 불일치(False)로 번역한다 — 어느 표면도 임의 순서를 지어내지 않는다.
    assert values.compare_order(left, right) is None
    assert values.order_matches(None, "<=") is False
    assert _safe_compare(left, right, "<=") is False
    with pytest.raises(where_dsl._WhereError):
        where_dsl._apply_op("<=", left, right)
    with pytest.raises(PredicateError):
        Evaluator.compare("<=", left, right)


def test_null_order_is_no_match_not_an_error_in_filter(where_dsl):
    # B37-1 계약: 결측의 순서 주장은 filter 에서 불일치(False)다 — 오류 아님.
    assert values.compare_order(None, 1) is None
    assert where_dsl._apply_op("<=", None, 1) is False
    assert _safe_compare(None, 1, "<=") is False
    with pytest.raises(PredicateError):
        Evaluator.compare("<=", None, 1)


def test_numeric_observation_preserves_precision_and_rejects_nonfinite():
    huge = 10 ** 400
    assert values.numeric_value(str(huge)) == huge
    assert values.numeric_value("12.5%") == 12.5
    assert values.numeric_value(True) is None
    assert values.numeric_value(float("nan")) is None
    assert values.numeric_value("Infinity") is None
    assert values.is_nonfinite_number(math.inf) is True
    assert values.is_nonfinite_number("Infinity") is True
    assert values.is_nonfinite_number("12.5") is False


@pytest.mark.parametrize("text,expected", [
    ("0", 0), ("-0", 0), ("+1", 1), ("01", 1), ("1.", 1.0), (".5", 0.5),
    ("1e3", 1000.0), ("1E-3", 0.001), ("1,000", 1000),
    ("1,234.50", 1234.5), ("10%", 10), (" 1,234.50 % ", 1234.5),
])
def test_numeric_text_grammar_accepts_only_declared_forms(text, expected):
    assert values.numeric_value(text) == expected
    assert as_num(text) == expected


@pytest.mark.parametrize("text", [
    "", " ", "+", ".", "1,,000", "12,34", "123,", "1,00,000", "1_000",
    "10%%", "1 000", "１２３", "1,234,56", "1e", "--1",
])
def test_malformed_numeric_text_is_not_silently_repaired(where_dsl, text):
    assert values.numeric_value(text) is None
    assert as_num(text) is None
    assert where_dsl._apply_op("==", text, 1000) is False
    assert Evaluator.compare("==", text, 1000) is False
    assert _match_condition({"v": text}, {"field": "v", "eq": 1000}) is False


@pytest.mark.parametrize("left,right", [
    (True, "True."), (False, "false!"), ("Yes.", "yes"), ("NO。", "no"),
])
def test_answer_punctuation_policy_is_shared_by_all_equality_consumers(
        where_dsl, left, right):
    assert values.values_equal(left, right) is True
    assert where_dsl._apply_op("==", left, right) is True
    assert Evaluator.compare("==", left, right) is True
    assert _match_condition({"v": left}, {"field": "v", "eq": right}) is True
    if not isinstance(left, bool):
        assert _scalar_sort_key(left) == _scalar_sort_key(right)


@pytest.mark.parametrize("left,right,expected", [
    (["A"], ["a"], True),
    ([1, {"ok": "YES."}], ["1", {"OK": "yes"}], True),
    ({"v": "01"}, {"V": 1}, True),
    ([float("nan")], [float("nan")], False),
    # 정본 계약: inf 는 자기 자신과 같다(IEEE) — 공개 경계 밖 유출은 결과 관문이 막는다.
    ({"v": float("inf")}, {"v": float("inf")}, True),
])
def test_structures_compose_scalar_equality_recursively(where_dsl, left, right, expected):
    assert values.values_equal(left, right) is expected
    assert where_dsl._apply_op("==", left, right) is expected
    assert Evaluator.compare("==", left, right) is expected


def test_generated_algebra_contract_over_value_shapes():
    samples = [
        None, False, True, 0, 1, 1.0, 9007199254740993,
        "0", "01", "1.0", "A", " a ", "Yes.", "yes", "1,,000",
        ["A"], ["a"], {"v": 1}, {"V": "1"}, float("nan"),
    ]
    structured = (list, tuple, dict)
    for left, right in itertools.product(samples, repeat=2):
        assert values.values_equal(left, right) == values.values_equal(right, left)
        forward = values.compare_order(left, right)
        backward = values.compare_order(right, left)
        if forward is None:
            assert backward is None
        else:
            assert backward is not None and int(backward) == -int(forward)
        # 스칼라 계약: 같으면 정렬 키도 같다(구조형 정렬 키는 표시 문자열 — 계약 밖).
        if (values.values_equal(left, right)
                and not isinstance(left, structured)
                and not isinstance(right, structured)
                and not isinstance(left, bool) and not isinstance(right, bool)):
            assert _scalar_sort_key(left) == _scalar_sort_key(right)
    for left, middle, right in itertools.product(samples, repeat=3):
        if values.values_equal(left, middle) and values.values_equal(middle, right):
            assert values.values_equal(left, right)


def test_data_sort_uses_the_common_sort_key(where_dsl):
    rows = [{"v": None}, {"v": "10"}, {"v": 2}, {"v": "B"}, {"v": "a"}]
    assert [row["v"] for row in where_dsl._sort_records(rows, "v")] == [2, "10", "a", "B", None]
    assert [row["v"] for row in where_dsl._sort_records(rows, "v", desc=True)] == ["10", 2, "B", "a", None]


def test_legacy_condition_surfaces_delegate_to_the_same_policy():
    assert _match_condition({"v": "01"}, {"field": "v", "eq": 1}) is True
    assert _match_condition(
        {"v": {"a": 1, "b": 2}},
        {"field": "v", "eq": {"b": 2, "a": 1}},
    ) is True
    assert AgentGoalsMixin._evaluate_condition_expr(None, "sense:x >= 2", "10") is True
    assert AgentGoalsMixin._evaluate_condition_expr(
        None, "sense:x == 9007199254740992", 9007199254740993) is False
    assert evaluate_range("10%", {"op": "gt", "value": 9}) is True
    branches = [{"pattern": "OPEN", "action": {"id": "matched"}}]
    assert select_case_branch("open", branches)["id"] == "matched"


@pytest.mark.parametrize("order,expected", [
    ("asc", [2, "10", "bad", None]),
    ("desc", ["10", 2, "bad", None]),
])
def test_response_numeric_sort_keeps_unobserved_values_last(order, expected):
    rows = [{"v": None}, {"v": "10"}, {"v": "bad"}, {"v": 2}]
    result = _apply_sort(rows, {"by": "v", "type": "number", "order": order})
    assert [row["v"] for row in result] == expected


def test_consumer_modules_cannot_reintroduce_local_scalar_policy(where_dsl):
    consumers = [
        _ROOT / "backend/ibl/ibl_predicates.py",
        _ROOT / "backend/ibl/api_transforms.py",
        _ROOT / "backend/ibl/ibl_parser.py",
        _ROOT / "backend/cognition/agent_goals.py",
        _ROOT / "backend/cognition/goal_evaluator.py",
        _ROOT / "backend/common/safe_expr.py",
        _WHERE,
    ]
    forbidden = (
        "float(str(", "return float(s)", "float(sense_value)", "float(compare_raw)",
        "(na > nb) - (na < nb)", "str(lv).strip() == str(rv).strip()", "_norm_yesno",
    )
    for path in consumers:
        source = path.read_text(encoding="utf-8")
        assert "common.value_semantics" in source, f"{path.name}: 공통 값 엔진 위임 없음"
        for fragment in forbidden:
            assert fragment not in source, f"{path.name}: 로컬 값 정책 재도입: {fragment}"

    # 호환용 옛 이름은 허용하되 몸통은 공통 엔진 위임뿐이어야 한다.
    assert "values_equal" in inspect.getsource(where_dsl._num_eq)
    assert "compare_order" in inspect.getsource(where_dsl._num_cmp)
    from ibl import ibl_predicates as predicates
    assert "numeric_value" in inspect.getsource(predicates._num)
    from common import safe_expr
    assert "numeric_value" in inspect.getsource(safe_expr.as_num)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
