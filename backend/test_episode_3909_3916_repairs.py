"""9/20 큰 원문·함수 학습·도구 계약의 실패를 외부 호출 없이 재현한다."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

import ibl_turn_vars as variables
from common import spill
from ibl_distill_gates import _composition_grounded, _heads_grounded, select_distill_source
from system_tools import _execute_ibl_unified
from thread_context import actor_context


@pytest.fixture
def scope(tmp_path):
    token = spill._spill_root.set(str(tmp_path))
    try:
        with actor_context(agent_id="episode-probe", task_id="episode-probe-task"):
            yield tmp_path, variables.turn_key("episode-probe")
    finally:
        spill._spill_root.reset(token)


def execute(code, path):
    return json.loads(_execute_ibl_unified({"code": code}, str(path), agent_id="episode-probe"))















def test_new_function_pipeline_and_heads_only_in_quotes_comments_are_rejected():
    calls = ['[fn:함수하나]{}', '[fn:함수둘]{}']
    assert not _composition_grounded('[fn:함수하나]{} >> [fn:함수둘]{}', calls)
    assert not _heads_grounded('[fn:안쓴함수]{}',
        ['[self:write]{path:"x",content:"[fn:안쓴함수]{}"} # [fn:안쓴함수]'])




def test_mcp_supervision_limit_and_execution_schema_match_backend():
    import anyio
    import mcp_server
    from supervision_bus import TOOL_SCHEMA, execution_tool_schema
    tools = anyio.run(mcp_server.mcp.list_tools)
    tool = next(t for t in tools if t.name == "supervision")
    props = tool.inputSchema["properties"]
    assert props["limit"]["minimum"] == 1 and props["limit"]["maximum"] == 24000
    assert props["offset"]["minimum"] == 0
    assert "execute" not in execution_tool_schema()["input_schema"]["properties"]["op"]["enum"]
    assert "execute" in TOOL_SCHEMA["input_schema"]["properties"]["op"]["enum"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
