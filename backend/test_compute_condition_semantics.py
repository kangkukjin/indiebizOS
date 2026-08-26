"""compute/reduce 식의 비교 의미론 — 조건 언어와 같은 한 벌 (2026-08-27 표면 동형성).

파이썬 원시 비교는 "Seoul"=="seoul" 을 거짓, 혼합 타입 순서를 TypeError 로 읽어
같은 몸의 filter/블록 술어와 다른 선고를 냈다(46회차 보고서의 '수용된 한계' 항목을
census 방법 전환으로 닫은 것). 동등=values_equal · 순서=compare_order 위임.
"""

import importlib.util
from pathlib import Path

import pytest

from common.safe_expr import compile_expr, eval_expr

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def data_ops():
    handler = ROOT / "data/packages/installed/tools/data-ops/handler.py"
    spec = importlib.util.spec_from_file_location("ce_data_ops", handler)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(expr, row):
    code, _, _ = compile_expr(expr)
    return eval_expr(code, row)


def test_equality_matches_condition_language():
    assert _run('1 if status == "OK" else 0', {"status": "ok"}) == 1     # casefold
    assert _run('a == b', {"a": " 서울 ", "b": "서울"}) is True            # strip
    assert _run('a == b', {"a": True, "b": "true"}) is True              # bool==텍스트 계약
    assert _run('a == b', {"a": True, "b": 1}) is False                  # bool≠숫자
    assert _run('a != b', {"a": "가", "b": "나"}) is True


def test_order_matches_condition_language():
    assert _run('a > b', {"a": "3,500", "b": 100}) is True
    assert _run('1 < a < 10', {"a": 5}) is True
    assert _run('a < b', {"a": "가", "b": "나"}) is True                  # 텍스트 순서


def test_mixed_type_order_is_honest_error_not_silent():
    code, _, _ = compile_expr('a > b')
    with pytest.raises(ValueError):
        eval_expr(code, {"a": "N/A", "b": 10})


def test_compute_cell_reports_undecidable_as_error(data_ops):
    """혼합 타입 비교는 그 행 None + compute_errors 신고 — 침묵 성공 금지."""
    rows = {"items": [{"a": "N/A", "b": 10}, {"a": 20, "b": 10}]}
    res = data_ops._op_compute(rows, {"set": {"큰가": "1 if a > b else 0"}})
    assert res["success"] is True
    assert res["items"][0]["큰가"] is None and res["items"][1]["큰가"] == 1
    assert res.get("compute_errors") == 1


def test_arithmetic_unchanged():
    assert _run('round(a / b * 100, 1)', {"a": 70300, "b": 271000}) == 25.9
    assert _run('abs(-3) + max(1, 2)', {}) == 5


def test_user_expression_cannot_reach_internal_compare():
    with pytest.raises(ValueError):
        compile_expr('_semantic_compare(1, [])')
    # 행 필드가 내부 이름과 겹쳐도 판정기는 가려지지 않는다
    assert _run('a == b', {"a": 1, "b": 1, "_semantic_compare": "오염"}) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
