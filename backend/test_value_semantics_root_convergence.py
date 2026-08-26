"""값 의미가 동사마다 갈라지지 않는지 — 관계 동사·검침·집계 횡단 (Codex 흡수)."""

import importlib.util
import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from common.safe_expr import as_num


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


@pytest.fixture(scope="module")
def data_ops():
    spec = importlib.util.spec_from_file_location("root_value_semantics_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table(rows):
    columns = list(rows[0])
    return {"columns": columns,
            "rows": [[row.get(column) for column in columns] for row in rows]}


@pytest.mark.parametrize("carrier", ["items", "table"])
def test_object_field_order_does_not_change_join_identity(data_ops, carrier):
    left = [{"k": {"a": 1, "nested": {"x": " A  B "}}, "left": 1}]
    right = [{"k": {"nested": {"x": "a b"}, "a": 1}, "right": 1}]
    if carrier == "table":
        left, right = _table(left), _table(right)
    else:
        left, right = {"items": left}, {"items": right}

    result = data_ops._op_join([left, right], {"on": "k"})

    assert result["success"] is True
    if carrier == "table":
        assert len(result["table"]["rows"]) == 1
    else:
        assert result["count"] == 1


@pytest.mark.parametrize("verb", ["dedup", "merge"])
@pytest.mark.parametrize("keys", [
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
    ({"a": [1, {"x": "A"}]}, {"a": [1, {"x": "a"}]}),
])
def test_structured_relation_keys_share_one_canonical_identity(data_ops, verb, keys):
    first, second = keys
    rows = [{"k": first, "id": 1}, {"k": second, "id": 2}]
    if verb == "dedup":
        result = data_ops._op_dedup({"items": rows}, {"by": "k"})
    else:
        result = data_ops._op_merge(
            [{"items": rows[:1]}, {"items": rows[1:]}], {"by": "k"})

    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["id"] == 1


@pytest.mark.parametrize("special", [
    float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity",
])
@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_nonfinite_values_never_claim_an_order(data_ops, special, op):
    # 정본 계약(45회차): filter 의 판정 불능은 침묵 False 가 아니라 정직 오류다.
    with pytest.raises(data_ops._wdsl._WhereError):
        data_ops._wdsl._apply_op(op, 10, special)
    with pytest.raises(data_ops._wdsl._WhereError):
        data_ops._wdsl._apply_op(op, special, 10)


@pytest.mark.parametrize("value, expected", [
    ("1,200", 1200), ("10%", 10), (False, None),
    ("1" + "0" * 400, 10 ** 400),
    (float("nan"), None), (float("inf"), None), ("NaN", None),
])
def test_all_numeric_consumers_use_finite_common_parser(data_ops, value, expected):
    common = as_num(value)
    local = data_ops._as_num(value)
    if isinstance(expected, float) and math.isnan(expected):
        assert math.isnan(common) and math.isnan(local)
    else:
        assert common == expected
        assert local == expected


def test_compute_and_groupby_observe_percent_numbers_the_same_way(data_ops):
    rows = [{"group": "A", "v": "10%"}]

    computed = data_ops._op_compute({"items": rows}, {"set": {"next": "v + 1"}})
    grouped = data_ops._op_groupby({"items": rows},
                                   {"by": "group", "agg": {"total": ["sum", "v"]}})

    assert computed["items"][0]["next"] == 11
    assert grouped["rows"][0][1] == 10


def test_since_migrates_order_dependent_object_keys_without_false_new(
        data_ops, tmp_path, monkeypatch):
    db = tmp_path / "since.db"

    def connect():
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS since_seen ("
            "stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT, "
            "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
            "PRIMARY KEY (stream, k))")
        return conn

    monkeypatch.setattr(data_ops, "_since_conn", connect)
    old_key = {"a": 1, "b": 2}
    new_order = {"b": 2, "a": 1}
    first = data_ops._op_since({"items": [{"k": old_key}]},
                               {"key": "object-key", "by": "k"})
    second = data_ops._op_since({"items": [{"k": new_order}]},
                                {"key": "object-key", "by": "k"})

    assert first["seeded"] is True
    assert second["items"] == []
    assert second["baseline_total"] == 1

    # 구버전이 str(dict)로 남긴 원장도 거짓 new 없이 읽고 정본 키로 이관한다.
    with connect() as conn:
        conn.execute("INSERT INTO since_seen VALUES (?,?,?,?,?)",
                     ("legacy-object", str(old_key), None, "old", "old"))
    migrated = data_ops._op_since({"items": [{"k": new_order}]},
                                  {"key": "legacy-object", "by": "k"})
    with connect() as conn:
        stored = conn.execute(
            "SELECT k FROM since_seen WHERE stream='legacy-object'").fetchall()
    assert migrated["items"] == []
    assert len(stored) == 1 and stored[0][0] != str(old_key)


def test_nonfinite_object_keys_become_lossless_strict_json(data_ops):
    key = {float("nan"): "number-key", "NaN": "text-key"}

    result = data_ops._op_groupby({"items": [{"group": key}]}, {"by": "group"})
    displayed = result["rows"][0][0]

    assert result["group_key_coercions"][0]["nonfinite_parts"] == 1
    assert displayed == {"$object_pairs": [["NaN", "number-key"], ["NaN", "text-key"]]}
    assert json.loads(json.dumps(displayed, allow_nan=False)) == displayed


def test_malformed_number_is_excluded_consistently_downstream(data_ops):
    rows = [{"group": "A", "v": "1,,000"}, {"group": "A", "v": 10}]

    grouped = data_ops._op_groupby(
        {"items": rows}, {"by": "group", "agg": {"total": ["sum", "v"]}})
    computed = data_ops._op_compute(
        {"items": rows}, {"set": {"next": "v + 1"}})
    sorted_rows = data_ops._op_sort({"items": rows}, {"by": "v"})

    assert grouped["rows"][0][1] == 10
    assert grouped["aggregation_skips"][0]["skipped"] == 1
    assert computed["items"][0]["next"] is None
    assert computed["compute_errors"] == 1
    assert [row["v"] for row in sorted_rows["items"]] == [10, "1,,000"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
