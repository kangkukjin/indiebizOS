"""상상훈련 36회차에서 드러난 통화·진단 경계의 회귀 시험."""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from ibl_param_vocab import check_params  # noqa: E402
from ibl_parser import IBLSyntaxError, parse  # noqa: E402
from ibl_registry import load_nodes_installed  # noqa: E402
from ibl_routing import _route_handler  # noqa: E402


_DATA_OPS = (Path(__file__).resolve().parent.parent / "data" / "packages" /
             "installed" / "tools" / "data-ops")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round36_data_ops", _DATA_OPS / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data_ops():
    return _load_handler()


def test_sparse_items_to_table_preserves_later_keys(data_ops):
    table, _ = data_ops._get_table({"items": [{"name": "B"}, {"name": "A", "score": 80}]})
    assert table == {
        "columns": ["name", "score"],
        "rows": [["B", None], ["A", 80]],
    }

    # 실제 발견 경로: 두 items 분기가 table 로 흡수된 뒤 union 되어도 값이 남는다.
    out = data_ops._op_union([
        {"items": [{"name": "B"}, {"name": "A", "score": 80}]},
        {"items": [{"name": "A", "score": 80}]},
    ], {})
    assert out["table"]["rows"] == [["B", None], ["A", 80], ["A", 80]]


@pytest.mark.parametrize("desc, expected", [
    (False, ["낮음", "높음", "문자", "결측"]),
    (True, ["높음", "낮음", "문자", "결측"]),
])
def test_sort_keeps_missing_last_and_type_order_stable(data_ops, desc, expected):
    out = data_ops._op_sort({"items": [
        {"name": "결측"},
        {"name": "낮음", "score": 2},
        {"name": "문자", "score": "해당없음"},
        {"name": "높음", "score": 80},
    ]}, {"by": "score", "desc": desc})
    assert [row["name"] for row in out["items"]] == expected


@pytest.mark.parametrize("action_name, tool_name, extra", [
    ("filter", "data_filter", {"where": "x > 0"}),
    ("sort", "data_sort", {"by": "x"}),
])
def test_pipeline_only_items_warns_before_execution_and_guides_pipeline(
        action_name, tool_name, extra):
    """★계약 은퇴 (언어 개정 2026-08-27, 사용자 판정): 옛 계약은 "단항 변환자의 items
    직접 입력=비공개(take 로만 진입)"였고 이 시험이 그 거절을 지켰다. 새 계약: items 는
    단항 변환자 전부의 공개 파라미터(array) — 경고 없이 씨앗으로 수용한다(치환 의미론
    개정으로 `$변수` 가 원형 목록을 넣게 되면서, 리터럴만 거절하는 비대칭이 무의미해졌다).
    이 시험은 같은 자리에서 **새 계약**을 지킨다."""
    action = load_nodes_installed()["nodes"]["table"]["actions"][action_name]
    params = {"items": [{"x": 1}], **extra}
    warning = check_params("table", action_name, params, action)
    assert not (warning and "공개 파라미터가 아닙니다" in (warning.get("message") or "")), \
        f"items 는 이제 공개 파라미터다 — 옛 경고가 살아 있다: {warning}"

    out = _route_handler(tool_name, params, ".", scope="workspace")
    assert out.get("success") is not False or "입력 통화가 없습니다" not in str(out.get("error")), \
        f"items 씨앗이 거절됐다: {out.get('error')}"


def test_try_catch_reports_unparseable_body_not_missing_catch():
    with pytest.raises(IBLSyntaxError) as caught:
        parse('[try]{[self:time]} [catch]{$return = []}')
    message = str(caught.value)
    assert "catch 블록은 있지만" in message
    assert "목록·사전 리터럴" in message
    assert "하나 이상 필요" not in message

    parsed = parse('[try]{[self:time]} [catch]{$return = 0}')
    assert parsed[0]["catch"]["_assign"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
