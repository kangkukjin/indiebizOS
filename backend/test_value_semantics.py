"""Shared record ordering: exact timezone boundaries and one observation per row."""
from datetime import datetime

import pytest

from common import value_semantics as values


@pytest.mark.parametrize("descending", [False, True])
def test_sort_full_iso_range_without_utc_overflow(descending):
    times = ["9999-12-31T23:59:59.999999-12:00",
             "0001-01-01T00:00:00.000001+14:00",
             "2026-10-08T00:00:00Z",
             "0001-01-01T00:00:00+14:00",
             "9999-12-31T23:59:59.999998-12:00"]
    rows = [{"at": value} for value in times]
    expected = sorted(rows, key=lambda row: datetime.fromisoformat(row["at"]),
                      reverse=descending)
    assert values.sort_records(rows, "at", descending) == expected
    assert [r["at"] for r in rows] == times


@pytest.mark.parametrize("left,right,different", [
    ("0001-01-01T00:00:00+14:00", "0001-01-01T01:00:00+15:00",
     "0001-01-01T00:00:00.000001+14:00"),
    ("9999-12-31T23:59:59.999999-12:00", "9999-12-31T22:59:59.999999-13:00",
     "9999-12-31T23:59:59.999998-12:00"),
])
def test_relation_identity_preserves_extreme_instant(left, right, different):
    assert values.values_equal(left, right)
    assert values.relation_identity(left) == values.relation_identity(right)
    assert values.group_identity(left) == values.group_identity(right)
    assert values.relation_identity(left) != values.relation_identity(different)
    assert values.group_identity(left) != values.group_identity(different)


@pytest.mark.parametrize("descending", [False, True])
def test_sort_observes_each_row_once_and_retains_stable_buckets(descending):
    calls = []

    def number(value):
        calls.append(value)
        return values.comparison_number(value)

    rows = [{"v": "B", "id": 0}, {"v": "2", "id": 1},
            {"v": "2026-10-08T09:00:00+09:00", "id": 2},
            {"v": None, "id": 3}, {"v": "b", "id": 4},
            {"v": "10", "id": 5}, {"id": 6},
            {"v": "2026-10-08T00:00:00Z", "id": 7}]
    result = values.sort_records(rows, "v", descending, number_parser=number)
    assert len(calls) == 6
    expected = [5, 1, 2, 7, 0, 4, 3, 6] if descending else [1, 5, 2, 7, 0, 4, 3, 6]
    assert [r["id"] for r in result] == expected
    assert all(any(row is original for original in rows) for row in result)


def test_regular_relation_keys_keep_persisted_spelling():
    assert values.relation_identity("2026-10-08T09:00:00+09:00") == "aware:2026-10-08T00:00:00"
    assert values.relation_identity("2026-10-08") == "naive:2026-10-08T00:00:00"


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
