"""여섯 경계가 한 JSON 계약을 내는지 — 엄격 직렬화 행렬 (Codex r43 흡수)."""

import asyncio
import datetime
import decimal
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

import api_ibl  # noqa: E402
import ibl_engine  # noqa: E402
import system_tools  # noqa: E402
from common.response_formatter import format_json  # noqa: E402
from common.value_semantics import dumps_public_result  # noqa: E402


def _cycle_value():
    cycle = []
    cycle.append(cycle)
    return {"v": cycle}


_SHAPES = [
    ("normal", lambda: {"v": [1, "x", None]}, "normal"),
    ("tuple", lambda: {"v": (1, 2)}, "tuple"),
    ("key_collision", lambda: {1: "number", "1": "text"}, "pairs"),
    ("bytes", lambda: {"v": b"abc"}, "error"),
    ("datetime", lambda: {"v": datetime.datetime(2026, 8, 26, 1, 2, 3)}, "error"),
    ("decimal", lambda: {"v": decimal.Decimal("0.1")}, "error"),
    ("set", lambda: {"v": {1, 2}}, "error"),
    ("cycle", _cycle_value, "error"),
]


def _parsed(result):
    if isinstance(result, str):
        return json.loads(result, parse_constant=lambda token: pytest.fail(token))
    json.dumps(result, allow_nan=False)
    return result


def _boundary_results(value, monkeypatch, tmp_path):
    results = [
        dumps_public_result(value),
        format_json(value),
        system_tools._dict_to_json(value),
    ]

    original_inner = system_tools._execute_tool_inner
    monkeypatch.setattr(system_tools, "_execute_tool_inner", lambda *_args, **_kwargs: value)
    results.append(system_tools.execute_tool("round43", {}, str(tmp_path)))
    monkeypatch.setattr(system_tools, "_execute_tool_inner", original_inner)

    original_impl = ibl_engine._execute_ibl_impl
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", lambda *_args, **_kwargs: value)
    results.append(ibl_engine.execute_ibl({"_node": "sense", "action": "round43"}, str(tmp_path)))
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", original_impl)

    original_unified = system_tools._execute_ibl_unified
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", lambda *_args, **_kwargs: value)
    request = api_ibl.IBLRequest(code="[sense:round43]", project_path=str(tmp_path))
    results.append(asyncio.run(api_ibl.execute_ibl_code(request)))
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", original_unified)
    return [_parsed(result) for result in results]


@pytest.mark.parametrize("name,factory,expected", _SHAPES)
def test_round43_matrix_has_one_json_contract_across_six_boundaries(
        name, factory, expected, monkeypatch, tmp_path):
    """훈련 48칸(8값 모양×직렬화/포매터/직접/도구/IBL/HTTP)을 재생한다."""
    results = _boundary_results(factory(), monkeypatch, tmp_path)

    assert len(results) == 6
    if expected == "normal":
        assert all(result == {"v": [1, "x", None]} for result in results), name
    elif expected == "tuple":
        assert all(result == {"v": [1, 2]} for result in results), name
    elif expected == "pairs":
        assert all(result == {"$object_pairs": [[1, "number"], ["1", "text"]]}
                   for result in results), name
    else:
        assert all(result.get("success") is False and
                   result.get("error_code") == "NON_JSON_RESULT"
                   for result in results), (name, results)


@pytest.mark.parametrize("payload", [
    '{"a": 1, "a": 2}',
    '{"outer": {"x": 1, "x": 2}}',
])
def test_duplicate_keys_in_json_strings_fail_before_the_parser_loses_data(payload):
    result = _parsed(dumps_public_result({"result": payload}, producer="duplicate-test"))

    assert result["success"] is False
    assert result["error_code"] == "NON_JSON_RESULT"
    assert "중복 키" in result["error"]
    assert "$.result<json>" in result["error"]


def test_unsupported_value_error_reports_the_nested_path():
    result = _parsed(dumps_public_result(
        {"items": [{"metadata": {"created": datetime.date(2026, 8, 26)}}]}))

    assert result["error_code"] == "NON_JSON_RESULT"
    assert "$.items[0].metadata.created" in result["error"]
    assert "date" in result["error"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
