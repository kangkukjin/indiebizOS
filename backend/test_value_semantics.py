"""Shared record ordering: exact timezone boundaries and one observation per row."""
from datetime import datetime
from decimal import Decimal

import pytest

from common import value_semantics as values


@pytest.mark.parametrize("value,reason,value_type", [
    (Decimal("123456789.123456789"), "precision_loss", "Decimal"),
    (Decimal("NaN"), "nonfinite_number", "Decimal"),
    (float("inf"), "nonfinite_number", "float"),
    (object(), "unsupported_type", "object"),
])
def test_public_json_violation_preserves_structured_cause(value, reason, value_type):
    with pytest.raises(ValueError) as caught:
        values.public_result({"rows": [value]}, strict=True)
    assert caught.value.details == {
        "reason": reason, "path": "$.rows[0]", "value_type": value_type}
    envelope = values.public_result({"rows": [value]})
    assert set(envelope) == {"success", "error_code", "error"}
    assert not envelope["success"] and envelope["error_code"] == caught.value.code


def test_nested_json_duplicate_and_container_cycle_have_distinct_causes():
    with pytest.raises(ValueError) as caught:
        values.public_result({"body": '{"a":1,"a":2}'}, strict=True)
    assert caught.value.details == {"reason": "duplicate_key", "path": "$.body<json>"}
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError) as caught:
        values.public_result({"rows": cycle}, strict=True)
    assert caught.value.details == {"reason": "cycle", "path": "$.rows[0]"}


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


@pytest.mark.parametrize('needle', ['\r', '\n', '\t', ' ', '\u00a0', '\r\n'])
def test_whitespace_search_uses_literal_pattern_on_every_surface(needle):
    for op in ('contains', 'startswith', 'endswith'):
        assert not values.text_match(op, 'abc', needle)
        assert values.text_match(op, needle + 'abc' + needle, needle)
    assert not values.text_match('in', needle, 'abc')
    assert values.text_match('in', needle, 'a' + needle + 'b')
    assert values.negative_text_match('contains', 'abc', needle)
    assert not values.text_match('contains', None, needle)
    assert not values.text_match('contains', {}, needle)


def test_empty_pattern_and_nonblank_search_keep_existing_policy():
    assert values.text_match('contains', 'abc', '')
    assert values.text_match('contains', '  ABC  ', ' b ')
    assert values.text_match('contains', [' x '], 'X')
    assert not values.text_match('contains', 'abc\n', '\r')


@pytest.mark.parametrize('source', [
    '음악 café', '\u110b\u1173\u11b7\u110b\u1161\u11a8 cafe\u0301',
    '앞 e\u0301\u0327 뒤', '\u0344끝', '\u212b!🙂',
])
def test_text_view_normalized_positions_and_verbatim_fragments(source):
    view = values.TextView(source)
    assert view.select(slice(None)) == source
    assert view.replace('never-matches', 'new') == source
    assert view.split('\n') == [source]
    for start in range(len(view.normalized) + 1):
        for end in range(start, len(view.normalized) + 1):
            assert values.normalized_text(view.fragment(start, end)) == view.normalized[start:end]


@pytest.mark.parametrize('body', [
    '{"x":1,"x":2}', '[{"x":1,"x":2}]', 'NaN', 'Infinity', '-Infinity',
    '1e999', '{"x":1e999}', 'not JSON', '\ufeff{}',
])
def test_explicit_json_parser_rejects_lossy_or_invalid_source(body):
    with pytest.raises(ValueError):
        values.parse_public_json(body)


@pytest.mark.parametrize('body,expected', [
    ('{"n":23000,"s":"007","x":null,"b":false}', {'n':23000,'s':'007','x':None,'b':False}),
    ('[1,2.5,"본문\\ufeff보존"]', [1,2.5,'본문\ufeff보존']),
    ('"NaN"', 'NaN'), ('0', 0), ('null', None), ('true', True),
])
def test_explicit_json_parser_preserves_json_types(body, expected):
    actual = values.parse_public_json(body)
    assert actual == expected
    assert type(actual) is type(expected)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
