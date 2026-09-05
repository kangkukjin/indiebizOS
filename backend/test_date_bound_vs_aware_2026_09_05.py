"""달력 날짜 하한 vs 시간대 있는 시각 (2026-09-05 언어 개정, 시스템 AI 보고).

`[table:filter]{where: {field: "date", op: "ge", value: "2026-08-15"}}` 가 gnews 의 aware 시각
(`2026-09-01T06:36:45+00:00`)에 "크기 비교 불가 — 같은 종류여야" 로 죽었다. 실제 갈림은 종류가
아니라 시간대 표기의 유무였고, 오류문이 원인을 빗나갔다. 규칙:
  · 달력 날짜(YYYY-MM-DD, 시각 없음) vs aware 시각 = aware 값의 *자기 시간대* 달력 날짜로 비교
    (어느 쪽에도 시간대를 지어내지 않는다)
  · 시각이 있는 naive vs aware = 종전대로 판정 불능
  · where DSL 의 gte/lte 별칭 = 조건 언어와 한 벌
  · 오류문은 실제 갈림(시간대 표기 유무)을 말한다

실행: .venv/bin/python -m pytest -q backend/test_date_bound_vs_aware_2026_09_05.py
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: E402,F401

from common.value_semantics import compare_order, values_equal  # noqa: E402

_PKG = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_calendar_date_vs_aware_orders_by_the_aware_values_own_date():
    assert compare_order("2026-09-01T06:36:45+00:00", "2026-08-15") == 1
    assert compare_order("2026-08-15", "2026-09-01T06:36:45+00:00") == -1
    # 자기 시간대의 날짜 — +09:00 의 8월 15일 00:30 은 UTC 로는 14일이지만 적힌 대로 15일이다
    assert compare_order("2026-08-15T00:30:00+09:00", "2026-08-15") == 0
    assert compare_order("2026-08-14T23:30:00Z", "2026-08-15") == -1
    assert values_equal("2026-08-15T10:00:00Z", "2026-08-15")
    assert not values_equal("2026-08-16T00:00:00Z", "2026-08-15")


def test_naive_with_time_vs_aware_stays_undecidable():
    assert compare_order("2026-08-15T10:00", "2026-08-15T10:00Z") is None
    assert not values_equal("2026-08-15T10:00", "2026-08-15T10:00Z")
    assert compare_order("2026-08-15", "2026-08-15T00:00") == 0        # naive 끼리는 종전대로


@pytest.fixture
def ops():
    return _load("_t_datebound_dataops", os.path.join(_PKG, "data-ops", "handler.py"))


def test_filter_date_lower_bound_over_aware_rows(ops):
    rows = {"items": [{"date": "2026-09-01T06:36:45+00:00", "t": "new"},
                      {"date": "2026-08-15T00:10:00+09:00", "t": "edge"},
                      {"date": "2026-08-01T12:00:00Z", "t": "old"}]}
    for op in ("ge", "gte", ">="):
        res = ops._op_filter(rows, {"where": {"field": "date", "op": op, "value": "2026-08-15"}})
        assert res.get("success") is not False, res
        assert [r["t"] for r in res["items"]] == ["new", "edge"], (op, res)
    res = ops._op_filter(rows, {"where": {"field": "date", "op": "lte", "value": "2026-08-15"}})
    assert [r["t"] for r in res["items"]] == ["edge", "old"]


def test_error_names_the_real_split(ops):
    rows = {"items": [{"date": "2026-08-15T10:00:00+00:00"}]}
    res = ops._op_filter(rows, {"where": {"field": "date", "op": "ge", "value": "2026-08-15T09:00"}})
    assert res.get("success") is False
    assert "시간대" in res["error"] and "YYYY-MM-DD" in res["error"], res["error"]
    assert "같은 종류" not in res["error"]


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
