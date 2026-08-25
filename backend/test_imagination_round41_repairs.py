"""41회차 상상훈련 — 관계 연산 구조 키 정규화 회귀 시험."""

import importlib.util
from pathlib import Path

import pytest


_HANDLER = (Path(__file__).resolve().parent.parent / "data" / "packages" /
            "installed" / "tools" / "data-ops" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round41_data_ops", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


_KEY_SHAPES = [
    ("strings", "A", "A", True),
    ("dict_same", {"a": 1, "b": 2}, {"a": 1, "b": 2}, True),
    ("dict_reordered", {"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
    ("nested_reordered", {"a": [{"x": 1, "y": 2}]},
     {"a": [{"y": 2, "x": 1}]}, True),
    ("list_equal", ["A", 1], ["A", 1], True),
    ("list_reordered", ["A", 1], [1, "A"], False),
    ("false_zero", False, 0, False),
    ("number_text", 0, "0", True),
]


def _table(rows):
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return {"columns": columns,
            "rows": [[row.get(column) for column in columns] for row in rows]}


def _count(result):
    assert result.get("success", True) is not False, result
    if isinstance(result.get("items"), list):
        return len(result["items"])
    table = result.get("table") if isinstance(result.get("table"), dict) else result
    return len(table.get("rows") or [])


@pytest.mark.parametrize("name,left_key,right_key,same", _KEY_SHAPES)
def test_round41_matrix_preserves_structural_relation_keys(
        data_ops, name, left_key, right_key, same):
    """원 48칸(8키 모양×6관계 경로)을 handler 계약으로 재생한다."""
    left = [{"k": left_key, "lv": 10}]
    right = [{"k": right_key, "rv": 20}]
    left_env, right_env = {"items": left}, {"items": right}
    results = {
        "join_items": data_ops._op_join([left_env, right_env], {"on": "k"}),
        "join_vars": data_ops._op_join([left, right], {"on": "k"}),
        "join_table": data_ops._op_join([_table(left), _table(right)], {"on": "k"}),
        "merge_items": data_ops._op_merge([left_env, right_env], {"by": "k"}),
    }
    unioned = data_ops._op_union([left_env, right_env], {})
    results["union_dedup"] = data_ops._op_dedup(unioned, {"by": "k"})
    results["dedup_items"] = data_ops._op_dedup(
        {"items": left + right}, {"by": "k"})

    for path in ("join_items", "join_vars", "join_table"):
        assert _count(results[path]) == (1 if same else 0), (name, path, results[path])
    for path in ("merge_items", "union_dedup", "dedup_items"):
        assert _count(results[path]) == (1 if same else 2), (name, path, results[path])


def test_structural_relation_keys_recurse_existing_scalar_normalization(data_ops):
    left = {"label": " A  B ", "number": "0", "nested": [{"x": "YES"}]}
    right = {"nested": [{"x": "yes"}], "number": 0, "label": "a b"}
    assert data_ops._norm(left) == data_ops._norm(right)
    assert data_ops._norm({"A": 1, "a": 2}) == data_ops._norm({"a": 2, "A": 1})
    assert data_ops._norm(["A", 1]) != data_ops._norm([1, "A"])
    assert data_ops._norm(False) != data_ops._norm(0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
