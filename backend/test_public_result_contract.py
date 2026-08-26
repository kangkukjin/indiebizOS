"""공개 결과의 유한 JSON 계약 — 실제 실행 경계를 시험한다 (Codex 흡수)."""

import asyncio
import inspect
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

from common.response_formatter import format_json  # noqa: E402
from common.value_semantics import (  # noqa: E402
    aggregate_numbers,
    dumps_public_result,
    public_result,
)
import api_ibl  # noqa: E402
import ibl_engine  # noqa: E402
import system_tools  # noqa: E402


_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("value,path", [
    ({"value": math.inf}, "$.value"),
    ({"nested": [0, math.nan]}, "$.nested[1]"),
    ({math.inf: "key"}, "$.<key>"),
    ([{"x": -math.inf}], "$[0].x"),
])
def test_public_result_rejects_nonfinite_at_the_exact_path(value, path):
    result = public_result(value, producer="contract-test")

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert path in result["error"]
    assert result["producer"] == "contract-test"
    json.dumps(result, allow_nan=False)


def test_public_result_inspects_json_envelopes_but_not_plain_text():
    invalid_json = '{"success": true, "nested": [Infinity]}'

    assert public_result(invalid_json)["error_code"] == "NONFINITE_RESULT"
    assert public_result("Infinity") == "Infinity"
    assert public_result("NaN은 데이터 표기가 아니라 설명입니다") == "NaN은 데이터 표기가 아니라 설명입니다"


def test_public_result_inspects_json_strings_nested_in_pipeline_envelopes():
    envelope = {
        "success": True,
        "results": [{"result": '{"items": [{"v": Infinity}]}' }],
    }

    result = public_result(envelope, producer="pipeline")

    assert result["success"] is False
    assert "$.results[0].result<json>.items[0].v" in result["error"]


def test_strict_serializer_and_shared_formatter_never_emit_json_constants():
    for render in (dumps_public_result, format_json):
        text = render({"success": True, "value": math.inf})
        parsed = json.loads(text, parse_constant=lambda token: pytest.fail(token))
        assert parsed["success"] is False
        assert parsed["error_code"] == "NONFINITE_RESULT"


@pytest.mark.parametrize("value", [
    {"success": True, "value": math.inf},
    '{"success": true, "value": NaN}',
])
def test_direct_tool_serialization_boundary_returns_an_error_envelope(value):
    text = system_tools._dict_to_json(value)
    result = json.loads(text, parse_constant=lambda token: pytest.fail(token))

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert result["producer"] == "execute_tool"


def test_outer_tool_boundary_catches_early_string_returns(monkeypatch):
    monkeypatch.setattr(
        system_tools, "_execute_tool_inner",
        lambda *_args, **_kwargs: '{"success": true, "value": Infinity}')

    text = system_tools.execute_tool("early-return", {}, ".")
    result = json.loads(text, parse_constant=lambda token: pytest.fail(token))

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert result["producer"] == "early-return"


def test_every_ibl_shape_passes_the_outer_result_gate(monkeypatch):
    monkeypatch.setattr(
        ibl_engine, "_execute_ibl_impl",
        lambda *_args, **_kwargs: {"success": True, "items": [{"v": math.inf}]})

    result = ibl_engine.execute_ibl({"_assign": True, "name": "x"}, "")

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert result["producer"] == "ibl:block"


def test_router_result_is_rejected_before_a_pipeline_can_consume_it(monkeypatch):
    monkeypatch.setattr(
        ibl_engine, "_route_handler",
        lambda *_args, **_kwargs: {"success": True, "items": [{"v": math.inf}]})

    result = ibl_engine.execute_ibl(
        {"_node": "table", "action": "compute", "params": {"set": {"x": "1"}}}, "")

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert result["producer"] == "table:compute"


def test_http_ibl_surface_uses_the_same_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system_tools, "_execute_ibl_unified",
        lambda *_args, **_kwargs: '{"success": true, "items": [{"v": Infinity}]}')
    request = api_ibl.IBLRequest(code="[table:compute]{}", project_path=str(tmp_path))

    result = asyncio.run(api_ibl.execute_ibl_code(request))

    assert result["success"] is False
    assert result["error_code"] == "NONFINITE_RESULT"
    assert result["producer"] == "POST /ibl/execute"


def test_stable_aggregation_is_owned_by_the_common_engine():
    huge = 10 ** 400
    assert aggregate_numbers("avg", [huge, huge]) == (huge, None)
    assert aggregate_numbers("sum", [1e308, 1e308, -1e308]) == (1e308, None)
    assert aggregate_numbers("sum", [5e-324, 5e-324]) == (1e-323, None)


def test_public_boundaries_cannot_reintroduce_per_surface_json_policy():
    boundaries = [
        _ROOT / "backend/cognition/system_tools.py",
        _ROOT / "backend/cognition/system_tools_ibl.py",
        _ROOT / "backend/ibl/ibl_engine.py",
        _ROOT / "backend/surface/api_ibl.py",
    ]
    for path in boundaries:
        source = path.read_text(encoding="utf-8")
        assert ("public_result" in source or "dumps_public_result" in source), path

    local_aggregate = (_ROOT / "data/packages/installed/tools/data-ops/dataops_value_semantics.py").read_text(
        encoding="utf-8")
    assert "aggregate_numbers" in local_aggregate
    assert "Decimal" not in local_aggregate and "localcontext" not in local_aggregate
    assert "public_result" in inspect.getsource(ibl_engine.execute_ibl)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
