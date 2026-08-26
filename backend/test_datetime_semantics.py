"""시간 의미론 — 선언 표기(ISO 8601)의 한 벌 판정 (2026-08-27 사용자 판정 집행).

판정: "ISO 8601만 날짜로 선언" — 숫자 문법 엄격화와 동형. 선언 표기만 날짜이고
(YYYY-MM-DD[, T/공백 시각[, 초·소수초][, Z/±HH:MM]]), 표기 밖(슬래시·점)과 달력
위반은 수선 없이 텍스트로 남는다. 같은 순간은 표기가 달라도 같은 실체다.
전 표면(filter·블록 술어·compute·정렬·관계 키·그룹 키·기한 파서)이 코어 한 벌을 승계.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from common.safe_expr import compile_expr, eval_expr
from common.value_semantics import (ValueKind, classify_value, compare_order,
                                    datetime_value, group_identity,
                                    relation_identity, sort_records, text_match,
                                    values_equal)
from ibl.ibl_predicates import Evaluator, PredicateError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def data_ops():
    handler = ROOT / "data/packages/installed/tools/data-ops/handler.py"
    spec = importlib.util.spec_from_file_location("dt_data_ops", handler)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 선언 표기 관문 — 무엇이 날짜이고 무엇이 아닌가 ──────────────────────────

_IS_DATE = ["2026-08-25", "2026-08-25T10:00", "2026-08-25 10:00",
            "2026-08-25T10:00:00", "2026-08-25T10:00:00.500", "2026-08-25T10:00:00Z",
            "2026-08-25T10:00:00+09:00"]
_NOT_DATE = ["08/25/2026", "2026.8.25", "25 Aug 2026", "2026-13-45", "2026-08-32",
             "2026-8-5", "20260825T10", "내일"]


@pytest.mark.parametrize("text", _IS_DATE)
def test_declared_notation_is_datetime(text):
    assert classify_value(text).kind is ValueKind.DATETIME, text


@pytest.mark.parametrize("text", _NOT_DATE)
def test_undeclared_notation_stays_text_without_repair(text):
    """표기 밖·달력 위반은 침묵 수선 없이 텍스트 — 숫자 문법과 같은 판정."""
    assert classify_value(text).kind is ValueKind.TEXT, text


# ── 동등·순서 — 순간 의미론 ────────────────────────────────────────────────

def test_same_instant_equal_across_notations():
    assert values_equal("2026-08-25T01:00:00Z", "2026-08-25T01:00:00+00:00")
    assert values_equal("2026-08-25T10:00:00+09:00", "2026-08-25T01:00:00Z")
    assert values_equal("2026-08-25", "2026-08-25T00:00:00")   # 날짜만 = 그날 00:00
    assert not values_equal("2026-08-25", "2026-08-26")


def test_timezone_order_is_true_order_not_lexicographic():
    """+09:00 10시 = Z 01시 — 옛 텍스트 순서는 10>01 로 조용히 틀렸다."""
    assert compare_order("2026-08-25T10:00:00+09:00", "2026-08-25T01:00:00Z") == 0
    assert compare_order("2026-08-25T09:00:00+09:00", "2026-08-25T01:00:00Z") < 0
    assert compare_order("2026-08-25", "2026-08-25T10:00") < 0


def test_naive_vs_aware_is_undecidable_not_fabricated():
    """시간대를 모르는 시각과 아는 시각의 순서·동등을 지어내지 않는다."""
    assert compare_order("2026-08-25T10:00", "2026-08-25T10:00Z") is None
    assert not values_equal("2026-08-25T10:00", "2026-08-25T10:00Z")
    with pytest.raises(PredicateError):
        Evaluator.compare(">", "2026-08-25T10:00", "2026-08-25T10:00Z")


def test_date_vs_other_kinds_refused():
    assert compare_order("2026-08-25", "N/A") is None
    assert compare_order("2026-08-25", 0) is None
    assert not values_equal("2026-08-25", 20260825)


# ── 표면 승계 — filter·블록·compute·정렬 ───────────────────────────────────

def test_filter_gt_on_dates(data_ops):
    rows = {"items": [{"d": "2026-08-24T23:00:00Z"}, {"d": "2026-08-25T09:00:00+09:00"},
                      {"d": "2026-08-26T01:00:00Z"}]}
    res = data_ops._op_filter(rows, {"where": {"field": "d", "op": "gt",
                                               "value": "2026-08-25T00:00:00Z"}})
    assert res["success"] is True
    assert [r["d"] for r in res["items"]] == ["2026-08-26T01:00:00Z"]


def test_block_predicate_dates():
    assert Evaluator.compare(">", "2026-08-26", "2026-08-25T10:00") is True
    assert Evaluator.compare("==", "2026-08-25T01:00Z", "2026-08-25T01:00+00:00") is True


def test_compute_expression_dates():
    code, _, _ = compile_expr('1 if d > "2026-08-25" else 0')
    assert eval_expr(code, {"d": "2026-08-25T10:00"}) == 1
    assert eval_expr(code, {"d": "2026-08-24"}) == 0


def test_sort_orders_mixed_notation_dates(data_ops):
    rows = {"items": [{"d": "2026-08-25T10:00:00+09:00"},   # = 01:00Z
                      {"d": "2026-08-25T03:00:00Z"},
                      {"d": "2026-08-25T00:30:00Z"}]}
    res = data_ops._op_sort(rows, {"by": "d"})
    assert [r["d"] for r in res["items"]] == [
        "2026-08-25T00:30:00Z", "2026-08-25T10:00:00+09:00", "2026-08-25T03:00:00Z"]


def test_sort_buckets_number_date_text_missing():
    rows = [{"v": "표"}, {"v": "2026-08-25"}, {"v": 7}, {"v": None}]
    srt = sort_records(rows, "v")
    assert [r["v"] for r in srt] == [7, "2026-08-25", "표", None]
    desc = sort_records(rows, "v", descending=True)
    assert [r["v"] for r in desc] == [7, "2026-08-25", "표", None]  # 버킷 순서는 고정


def test_forced_text_sort_disables_date_semantics():
    rows = [{"v": "2026-08-25T10:00:00+09:00"}, {"v": "2026-08-25T03:00:00Z"}]
    srt = sort_records(rows, "v", number_parser=None)
    assert [r["v"] for r in srt] == ["2026-08-25T03:00:00Z", "2026-08-25T10:00:00+09:00"]


# ── 관계·그룹 키 — 같은 순간 같은 실체 ─────────────────────────────────────

def test_relation_keys_fold_same_instant(data_ops):
    assert relation_identity("2026-08-25T01:00Z") == relation_identity("2026-08-25T01:00+00:00")
    assert relation_identity("2026-08-25") == relation_identity("2026-08-25T00:00:00")
    assert relation_identity("2026-08-25T10:00") != relation_identity("2026-08-25T10:00Z")
    dedup = data_ops._op_dedup(
        {"items": [{"k": "2026-08-25T01:00Z"}, {"k": "2026-08-25T01:00+00:00"}]}, {"by": "k"})
    assert len(dedup["items"]) == 1
    joined = data_ops._op_join(
        [{"items": [{"k": "2026-08-25", "l": 1}]},
         {"items": [{"k": "2026-08-25T00:00:00", "r": 2}]}], {"on": "k"})
    assert len(joined["items"]) == 1


def test_group_identity_folds_notation_only():
    assert group_identity("2026-08-25T01:00Z") == group_identity("2026-08-25T01:00+00:00")
    assert group_identity("2026-08-25") != group_identity("2026-08-26")
    assert group_identity(datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)) == \
        group_identity("2026-08-25T01:00:00Z")


# ── 부속 — 텍스트 부분일치·기한 파서 위임 ──────────────────────────────────

def test_partial_match_keeps_display_view():
    assert text_match("contains", "2026-08-25T10:00", "2026-08") is True
    assert text_match("startswith", "2026-08-25", "2026") is True


def test_goal_deadline_parser_delegates_to_declared_notation():
    from cognition.goal_evaluator import _parse_datetime
    assert _parse_datetime("2026-08-25 10:00") == datetime(2026, 8, 25, 10, 0)
    assert _parse_datetime("2026-08-25T10:00:00Z") == \
        datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    assert _parse_datetime("08/25/2026") is None


def test_datetime_value_rejects_calendar_violations():
    assert datetime_value("2026-02-30") is None
    assert datetime_value("2026-08-25T25:00") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
