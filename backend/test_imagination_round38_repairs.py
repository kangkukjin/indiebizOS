"""38회차 상상훈련 — 이항 관계 키 경계의 회귀 시험."""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round38_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_MISSING = object()
_KEY_SHAPES = [
    ("normal", "A", "A", True),
    ("case", "Alpha", "alpha", True),
    ("space", " A  B ", "a b", True),
    ("numeric_text", "10", "10", True),
    ("zero_numeric_text", 0, "0", True),
    ("blank", "", "", False),
    ("null", None, None, False),
    ("missing", _MISSING, _MISSING, False),
]


def _target(side, key):
    row = {"id": f"target{side}", f"{side.lower()}v": 1}
    if key is not _MISSING:
        row["k"] = key
    return row


def _inputs(left_key, right_key):
    left = [{"id": "controlL", "k": "CTRL", "lv": 0}, _target("L", left_key)]
    right = [{"id": "controlR", "k": "CTRL", "rv": 0}, _target("R", right_key)]
    return left, right


def _table(rows):
    cols = []
    for row in rows:
        for key in row:
            if key not in cols:
                cols.append(key)
    return {"columns": cols, "rows": [[row.get(col) for col in cols] for row in rows]}


def _count(result):
    if isinstance(result.get("items"), list):
        return len(result["items"])
    table = result.get("table") if isinstance(result.get("table"), dict) else result
    return len(table.get("rows") or [])


@pytest.mark.parametrize("name,left_key,right_key,has_key", _KEY_SHAPES)
def test_round38_matrix_preserves_key_meaning_across_six_paths(
        data_ops, name, left_key, right_key, has_key):
    """훈련의 48칸(8키 모양×6경로)을 handler 계약으로 그대로 재생한다."""
    left, right = _inputs(left_key, right_key)
    left_env, right_env = {"items": left}, {"items": right}

    join_expected = 2 if has_key else 1
    dedup_expected = 2 if has_key else 3
    results = {
        "join_items": data_ops._op_join([left_env, right_env], {"on": "k"}),
        "join_vars": data_ops._op_join([left, right], {"on": "k"}),
        "join_table": data_ops._op_join([_table(left), _table(right)], {"on": "k"}),
        "merge_items": data_ops._op_merge([left_env, right_env], {"by": "k"}),
        "merge_vars": data_ops._op_merge([left, right], {"by": "k"}),
    }
    unioned = data_ops._op_union([left_env, right_env], {})
    results["union_dedup"] = data_ops._op_dedup(unioned, {"by": "k"})

    for path in ("join_items", "join_vars", "join_table"):
        assert results[path].get("success", True) is not False, (name, path, results[path])
        assert _count(results[path]) == join_expected, (name, path, results[path])
    for path in ("merge_items", "merge_vars", "union_dedup"):
        assert results[path].get("success", True) is not False, (name, path, results[path])
        assert _count(results[path]) == dedup_expected, (name, path, results[path])


def test_falsey_scalars_are_not_erased_by_normalization(data_ops):
    assert data_ops._norm(0) == "0"
    assert data_ops._norm(False) == "false"
    assert data_ops._norm(None) == ""
    assert data_ops._join_key(0) == "0"
    assert data_ops._join_key(False) == "false"


@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_null_blank_and_whitespace_are_not_join_keys(data_ops, value):
    assert data_ops._join_key(value) is None


def test_items_envelopes_remain_items_and_explicit_tables_remain_tables(data_ops):
    left, right = _inputs("A", "A")
    item_result = data_ops._op_join([{"items": left}, {"items": right}], {"on": "k"})
    table_result = data_ops._op_join([_table(left), _table(right)], {"on": "k"})

    assert "items" in item_result and "table" not in item_result
    assert "table" in table_result and "items" not in table_result


def test_mixed_items_and_table_inputs_are_rejected_honestly(data_ops):
    left, right = _inputs("A", "A")
    out = data_ops._op_join([{"items": left}, _table(right)], {"on": "k"})
    assert out["success"] is False
    assert "같은 통화" in out["error"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
