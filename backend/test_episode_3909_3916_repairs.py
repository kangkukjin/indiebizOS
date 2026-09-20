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


def test_original_size_result_can_be_filtered_on_next_call(scope):
    path, key = scope
    value = {"items": [{"url": "a", "text": "가" * 2_100_000},
                       {"url": "b", "text": "확인할 본문"}],
             "source": "x" * 2_100_000}
    assert variables.save(key, {"원문": value}) == (["원문"], [])
    manifest = json.loads(Path(variables.store_path(key)).read_text())
    assert "원문" in manifest["refs"] and "원문" not in manifest["values"]
    assert Path(variables.store_path(key)).stat().st_size < 20000
    assert variables.types_for({"원문": None}, key)["원문"].kind != "items"
    result = execute('$원문 >> [table:filter]{where:"url == b"} >> [table:select]{fields:["text"]}', path)
    assert result.get("success"), result
    final = result["final_result"]
    final = json.loads(final) if isinstance(final, str) else final
    assert final["items"] == [{"text": "확인할 본문"}]
    assert result["turn_vars"]["injected"] == ["원문"]


def test_total_budget_externalizes_without_forgetting_old_names(scope, monkeypatch):
    _, key = scope
    monkeypatch.setattr(variables, "MAX_STORE_CHARS", 50)
    values = {"a": {"items": [{"x": "old" * 30}]}, "b": "latest" * 20}
    variables.save(key, {"a": values["a"]})
    variables.save(key, {"b": values["b"]})
    restored = variables.load(key)
    assert json.loads(restored["a"]) == values["a"] and restored["b"] == values["b"]
    variables.save(key, {"a": "new"})
    assert variables.load(key)["a"] == "new"
    assert "a" not in json.loads(Path(variables.store_path(key)).read_text())["refs"]


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_reference_failure_is_explicit_and_unrelated_value_still_works(scope, monkeypatch, damage):
    path, key = scope
    monkeypatch.setattr(variables, "MAX_VALUE_CHARS", 100)
    variables.save(key, {"large": "x" * 101, "small": {"items": [{"x": 1}]}})
    record = json.loads(Path(variables.store_path(key)).read_text())
    body = Path(record["refs"]["large"]["path"])
    if damage == "missing":
        body.unlink()
    else:
        body.write_text("changed")
    assert execute('$small >> [table:take]{n:1}', path).get("success")
    failure = execute('$large', path)
    assert not failure.get("success") and "턴 변수 $large 복원 실패" in failure["error"]


def test_concurrent_store_updates_preserve_both_names(scope, monkeypatch):
    path, key = scope
    # worker 스레드의 contextvar에 기대지 않고 동일 저장 루트를 명시한다.
    monkeypatch.setattr(spill, "spill_dir", lambda: str(path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: variables.save(key, {f"v{i}": str(i)}), range(20)))
    assert variables.load(key) == {f"v{i}": str(i) for i in range(20)}


def test_short_call_only_hydrates_referenced_names(scope, monkeypatch):
    path, key = scope
    variables.save(key, {"needed": {"items": [{"x": 1}]}, "unrelated": "large source"})
    load = variables.load
    seen = []

    def observed(key, names=None):
        seen.append(names)
        return load(key, names)

    monkeypatch.setattr(variables, "load", observed)
    assert execute('$needed >> [table:take]{n:1}', path).get("success")
    assert seen and all(names is not None and "unrelated" not in names for names in seen)


@pytest.mark.parametrize("name", ["본문에서찾기", "열추려보기"])
def test_selected_korean_function_source_passes_grounding(name):
    calls = ['$원문 = [sense:crawl]{url:"https://example.com"}',
             f'$원문 >> [fn:{name}]{{}}']
    selected, note = select_distill_source({"call_ids": [2]}, calls)
    assert selected == "\n".join(calls), note
    assert _heads_grounded(selected, calls)
    assert _composition_grounded(selected, calls)
    assert not _heads_grounded('$원문 >> [fn:안쓴함수]{}', calls)


def test_new_function_pipeline_and_heads_only_in_quotes_comments_are_rejected():
    calls = ['[fn:함수하나]{}', '[fn:함수둘]{}']
    assert not _composition_grounded('[fn:함수하나]{} >> [fn:함수둘]{}', calls)
    assert not _heads_grounded('[fn:안쓴함수]{}',
        ['[self:write]{path:"x",content:"[fn:안쓴함수]{}"} # [fn:안쓴함수]'])


def test_quote_error_gives_valid_recovery_without_rewriting_input():
    from ibl_parser import parse, IBLSyntaxError
    with pytest.raises(IBLSyntaxError, match="바깥을 작은따옴표"):
        parse('[sense:search]{queries:[""Data work" full text"]}')
    parsed = parse('''[sense:search]{queries:['"Data work" full text']}''')
    assert parsed[0]["params"]["queries"] == ['"Data work" full text']


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
