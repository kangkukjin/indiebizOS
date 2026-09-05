"""수치 결과 경계 — 안정 집계와 compute/reduce/assign 유한 관문 (Codex r42 흡수)."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from common.safe_expr import compile_expr, eval_expr  # noqa: E402
from ibl import ibl_control_blocks as blocks  # noqa: E402


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


@pytest.fixture(scope="module")
def data_ops():
    spec = importlib.util.spec_from_file_location("round42_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SHAPES = [
    ("normal", [1, 2]),
    ("huge_int", [10 ** 400, 10 ** 400]),
    ("max_float", [1e308, 1e308]),
    ("cancellation", [1e308, 1e308, -1e308]),
    ("subnormal", [5e-324, 5e-324]),
    ("mixed_huge_int_float", [10 ** 400, 1.0]),
    ("exponent_text", ["1e308", "1e308"]),
    ("percent_text", ["10%", "20%"]),
]


def _strict_json(result):
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("name,values", _SHAPES)
def test_round42_matrix_keeps_all_six_numeric_consumers_strict_json(
        data_ops, name, values):
    """훈련 48칸(8크기 모양×집계4/compute/reduce)을 그대로 재생한다."""
    rows = [{"group": "A", "v": value} for value in values]

    for op in ("sum", "avg", "min", "max"):
        result = data_ops._op_groupby(
            {"items": rows}, {"by": "group", "agg": {"value": [op, "v"]}})
        assert result.get("success", True) is not False, (name, op, result)
        _strict_json(result)

    computed = data_ops._op_compute(
        {"items": rows}, {"set": {"value": "v * 2"}})
    assert computed.get("success", True) is not False, (name, computed)
    _strict_json(computed)

    reduced = blocks._execute_table_reduce(
        {"items": rows, "init": 0, "step": "acc + v", "as": "value"}, "")
    _strict_json(reduced)
    if reduced["success"]:
        assert not isinstance(reduced["value"], float) or math.isfinite(reduced["value"])
    else:
        assert ("비유한 수" in reduced["error"] or
                "too large to convert to float" in reduced["error"]), (name, reduced)


def _aggregate(data_ops, values, op):
    rows = [{"group": "A", "v": value} for value in values]
    result = data_ops._op_groupby(
        {"items": rows}, {"by": "group", "agg": {"value": [op, "v"]}})
    # 형태 보존(언어 개정 2026-09-06): items 입력엔 items — 집계열은 두 번째 값.
    return result, list(result["items"][0].values())[1]


def test_stable_aggregate_preserves_huge_integer_and_float_meaning(data_ops):
    huge = 10 ** 400
    _, integer_avg = _aggregate(data_ops, [huge, huge], "avg")
    _, float_avg = _aggregate(data_ops, [1e308, 1e308], "avg")
    _, overflow_sum = _aggregate(data_ops, [1e308, 1e308], "sum")

    assert integer_avg == huge and isinstance(integer_avg, int)
    assert float_avg == 1e308 and isinstance(float_avg, float)
    assert overflow_sum > 10 ** 308 and isinstance(overflow_sum, int)


def test_stable_aggregate_avoids_order_overflow_and_rounding_underflow(data_ops):
    _, cancellation = _aggregate(data_ops, [1e308, 1e308, -1e308], "sum")
    _, subnormal_sum = _aggregate(data_ops, [5e-324, 5e-324], "sum")
    _, subnormal_min = _aggregate(data_ops, [5e-324], "min")

    assert cancellation == 1e308
    assert subnormal_sum == 1e-323
    assert subnormal_min == 5e-324


def test_unrepresentable_fraction_is_null_with_an_honest_error(data_ops):
    result, value = _aggregate(data_ops, [10 ** 400, 1.0], "avg")

    assert value is None
    assert result["aggregation_errors"][0]["op"] == "avg"
    assert "표현할 수 없어 null" in result["warning"]
    _strict_json(result)


def test_compute_reduce_and_assign_share_the_finite_result_gate(data_ops):
    computed = data_ops._op_compute(
        {"items": [{"v": 1e308}]}, {"set": {"value": "v * 2"}})
    reduced = blocks._execute_table_reduce(
        {"items": [{"v": 1e308}, {"v": 1e308}], "step": "acc + v"}, "")
    assigned = blocks._execute_assign(
        {"name": "x", "expr": "$v * 2", "_var_values": {"v": {"value": 1e308}}},
        "", "")

    assert computed["items"][0]["value"] is None
    assert computed["compute_errors"] == 1 and "비유한 수" in computed["note"]
    assert reduced["success"] is False and reduced["rows_done"] == 1
    assert assigned["success"] is False and "비유한 수" in assigned["error"]
    for result in (computed, reduced, assigned):
        _strict_json(result)


def test_finite_gate_checks_nested_expression_results():
    code, _, _ = compile_expr("(v, v * 2)")
    with pytest.raises(ValueError, match=r"\$\[1\].*Infinity"):
        eval_expr(code, {"v": 1e308})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
