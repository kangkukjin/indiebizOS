"""에이전트 경계 예산 · Claude Code 도구 집합 회귀 (2026-09-04, ep2800 실측).

재현한 결함: 세 파일을 `&` 로 한 문장에 읽으면 REST 봉투 31,909자인데 MCP 경계 예산이 고정
24,000자라 잘렸고, 에이전트는 파일을 하나씩 다시 읽었다(재읽기 4왕복 ≈ 70초). 그 학습의 결과가
1액션 문장 60~75% — 큰 문장을 쓰면 벌 받는 통로였다. in-process 프로바이더는 원래부터
액션당 16,000자 × 액션 수였고 MCP 경계만 예외였다.

고정하는 계약:
  B1  경계의 액션당 예산은 in-process 프로바이더의 MAX_TOOL_RESULT_LENGTH 와 **같은 수**(동율 관문).
  B2  예산 = 액션당 × 액션 수, 상한 = 호스트 CLI 한도(MAX_MCP_OUTPUT_TOKENS, 기본 25,000토큰 ×
      1.6자/토큰 실측). env 로 호스트 한도를 올리면 상한도 따라간다.
  B3  3액션 문장의 32K 봉투는 손대지 않고 통과한다(ep2800 재현). 같은 봉투를 1액션으로 보면 줄인다.
  B4  Claude Code 명령은 `--tools` 로 내장 집합을 좁힌다(ToolSearch 소멸·MCP eager, CLI 2.1.258 실측)
      — 그리고 TOOL_POLICY 는 더는 ToolSearch 를 시키지 않는다(시키면 존재하지 않는 도구 호출 = 헛왕복).
  B5  세션 키는 도구 정책 지문을 달고 있다(ep2811: 정책을 바꿔도 resume 된 트랜스크립트가 옛 습관
      — ToolSearch 호출 — 을 재생했다). 정책이 바뀌면 키가 바뀌어 fresh, '새 대화' 스윕은 파생 키도 지운다.

실행: .venv/bin/python -m pytest backend/test_agent_boundary_budget.py -q
"""
import json
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, ROOT)
import boot_paths  # noqa: E402,F401


def _mcp():
    import mcp_server
    return mcp_server


# ---------------------------------------------------------------- B1 동율
def test_b1_per_action_budget_equals_inprocess_providers():
    m = _mcp()
    from providers import anthropic as pa, openai as po, ollama as pl
    assert m._PER_ACTION_CHARS == pa.MAX_TOOL_RESULT_LENGTH == po.MAX_TOOL_RESULT_LENGTH == pl.MAX_TOOL_RESULT_LENGTH


# ---------------------------------------------------------------- B2 식·상한
def test_b2_budget_scales_with_actions_under_host_cap(monkeypatch):
    m = _mcp()
    monkeypatch.delenv("MAX_MCP_OUTPUT_TOKENS", raising=False)
    cap = int(m._HOST_MCP_TOKENS_DEFAULT * m._CHARS_PER_TOKEN)
    assert m._agent_budget_chars(1) == m._PER_ACTION_CHARS
    assert m._agent_budget_chars(2) == min(2 * m._PER_ACTION_CHARS, cap)
    assert m._agent_budget_chars(3) == cap                       # 48K > 40K → 호스트 상한
    assert m._agent_budget_chars(0) == m._agent_budget_chars(1)  # 0·음수는 1
    monkeypatch.setenv("MAX_MCP_OUTPUT_TOKENS", "50000")
    assert m._agent_budget_chars(3) == 3 * m._PER_ACTION_CHARS   # env 로 올리면 상한이 따라온다
    monkeypatch.setenv("MAX_MCP_OUTPUT_TOKENS", "garbage")
    assert m._agent_budget_chars(3) == cap                       # 깨진 env 는 기본값


def test_b2_count_actions_from_code():
    m = _mcp()
    assert m._count_actions('[self:read]{path: "a"} & [self:read]{path: "b"} & [self:read]{path: "c"}') == 3
    assert m._count_actions('[sense:search]{query: "x"} >> [table:take]{n: 3}') == 2
    assert m._count_actions("") == 1


def test_cli_host_has_room_for_declared_display_and_keeps_explicit_limit(monkeypatch):
    from common.spill import DISPLAY_MCP_OUTPUT_TOKENS
    from providers.claude_code import ClaudeCodeProvider
    inst = object.__new__(ClaudeCodeProvider)
    inst._effective_token = None
    monkeypatch.setattr(inst, '_identity_env', lambda: {})
    monkeypatch.delenv('MAX_MCP_OUTPUT_TOKENS', raising=False)
    env = inst._build_env()
    assert env['MAX_MCP_OUTPUT_TOKENS'] == str(DISPLAY_MCP_OUTPUT_TOKENS)
    monkeypatch.setenv('MAX_MCP_OUTPUT_TOKENS', env['MAX_MCP_OUTPUT_TOKENS'])
    assert _mcp()._host_cap_chars() >= 60000 + 16000
    monkeypatch.setenv('MAX_MCP_OUTPUT_TOKENS', '10000')
    assert inst._build_env()['MAX_MCP_OUTPUT_TOKENS'] == '10000'


def test_declared_display_does_not_remove_overall_delivery_bound():
    from common.spill import AUTO_SPILL_THRESHOLD
    from ibl_envelope import display_delivery_budget
    ordinary = json.dumps({'items': [{'text': '가' * 70000}]}, ensure_ascii=False)
    assert display_delivery_budget(ordinary, 16000) == 16000
    huge = json.dumps({'_display': {'max_chars': 60000}, 'items': [
        {'text': '가' * (AUTO_SPILL_THRESHOLD + 10000)}]}, ensure_ascii=False)
    assert display_delivery_budget(huge, 16000) == AUTO_SPILL_THRESHOLD


# ---------------------------------------------------------------- B3 ep2800 재현
def _envelope(total_chars: int) -> str:
    body = ("가" * 400 + "\n") * (total_chars // 401 + 1)
    env = {"success": True, "steps_completed": 1, "steps_total": 1, "_results_summarized": True,
           "results": [{"step": 1, "type": "parallel", "branches": 3, "shape": "text"}],
           "final_result": body[: total_chars - 200]}
    return json.dumps(env, ensure_ascii=False)


def test_b3_three_action_envelope_passes_untouched(monkeypatch):
    m = _mcp()
    monkeypatch.delenv("MAX_MCP_OUTPUT_TOKENS", raising=False)
    raw = _envelope(32_000)
    assert 31_000 < len(raw) < m._agent_budget_chars(3)
    assert m._trim_for_agent(raw, actions=3) == raw
    one = m._trim_for_agent(raw, actions=1)
    assert len(one) <= m._agent_budget_chars(1) + 120 and "생략" in one


def test_verbose_small_envelope_keeps_explicit_final_result():
    final = json.dumps({"items": [7, 8, 9, 10], "count": 4})
    env = {"success": True, "results": [{"step": 1, "result": final}], "final_result": final}
    raw = json.dumps(env)
    assert _mcp()._trim_for_agent(raw) == raw


def test_negative_take_survives_verbose_turn_variable_delivery(tmp_path, monkeypatch):
    """ep3219: 엔진은 4행을 냈지만 verbose 원장 10행 뒤의 최종 값이 MCP에서 잘렸다."""
    from common import spill
    from system_tools import _execute_ibl_unified
    from thread_context import actor_context

    monkeypatch.setattr(spill, "spill_dir", lambda: str(tmp_path))
    rows = [{"id": n, "body": "원장 내용" * 160} for n in range(1, 11)]
    ledger = tmp_path / "ledger.json"
    rules = tmp_path / "rules.md"
    ledger.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    rules.write_text("방법론 규칙\n" * 1500, encoding="utf-8")
    code = ('$규칙 = [self:read]{path:' + json.dumps(str(rules)) + '}\n'
            '$원장 = [self:read]{path:' + json.dumps(str(ledger)) + '}')
    with actor_context(agent_id="probe", task_id="task_take_delivery"):
        first = json.loads(_execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe"))
        assert first["success"], first
        raw = _execute_ibl_unified({"code": '$규칙\n$원장 >> [table:take]{n: -4}', "verbose": True},
                                   str(tmp_path), agent_id="probe")
    original = json.loads(raw)
    assert original["results"][1]["count"] == 10
    assert "result_ref" in original
    delivered = _mcp()._trim_for_agent(raw, actions=1)
    assert len(delivered) <= _mcp()._agent_budget_chars(1)
    out = json.loads(delivered)
    final = json.loads(out["final_result"])
    assert final["count"] == 4 and final["items"] == rows[-4:]
    assert out["results"][1]["count"] == 10 and out["results"][2]["count"] == 4
    assert out["_results_summarized"]
    assert "final_result" in original and "result" not in original["results"][1]


@pytest.mark.parametrize("success", [True, False])
def test_oversized_final_stays_recoverable_json(tmp_path, monkeypatch, success):
    from common import spill

    monkeypatch.setattr(spill, "spill_dir", lambda: str(tmp_path))
    final = {"items": [{"id": 7, "body": "큰 값" * 20000}], "count": 1}
    env = {"success": success, "steps_total": 2,
           "results": [{"step": 1, "result": "중간 값" * 5000}],
           "final_result": json.dumps(final, ensure_ascii=False)}
    if not success:
        env.update(error="실패 상세" * 10000, resume={"from_step": 2, "vars_ref": "/tmp/live.json"})
    raw = json.dumps(env, ensure_ascii=False)
    text = _mcp()._trim_for_agent(raw)
    out = json.loads(text)
    assert len(text) <= _mcp()._agent_budget_chars(1)
    assert out["success"] is success and out["_spilled"] and out["_trimmed"]
    saved, error = spill.read_ref(out["ref"])
    assert error is None and json.loads(saved) == env
    assert out["final_result_summary"]["count"] == 1


# ---------------------------------------------------------------- B4 도구 집합
def test_b4_command_narrows_builtins_and_policy_stops_asking_toolsearch():
    from providers.claude_code import ClaudeCodeProvider as P
    assert "ToolSearch" not in P.TOOL_POLICY
    assert all(not t.startswith("mcp__") for t in P.EAGER_BUILTIN_TOOLS)
    assert "Bash" in P.EAGER_BUILTIN_TOOLS and "Write" in P.EAGER_BUILTIN_TOOLS
    inst = object.__new__(P)
    inst._binary_path = "claude"; inst.model = None; inst.system_prompt = "S"
    cmd = inst._build_command(stream=True, mcp_config_path="/tmp/x.json")
    i = cmd.index("--tools")
    assert cmd[i + 1] == ",".join(P.EAGER_BUILTIN_TOOLS)
    j = cmd.index("--allowed-tools")
    assert "mcp__indiebizos__execute_ibl" in cmd[j + 1]
    # 원샷(tools_mode) 경로는 그대로 — 도구 0
    cmd0 = inst._build_command(stream=False, mcp_config_path=None, tools_mode="none")
    assert cmd0[cmd0.index("--tools") + 1] == "" and "--allowed-tools" not in cmd0


# ---------------------------------------------------------------- B5 정책 지문
def test_b5_session_key_carries_tool_policy_fingerprint(monkeypatch, tmp_path):
    from providers.claude_code import ClaudeCodeProvider as P
    from providers import cli_provider as cp
    inst = object.__new__(P)
    inst.agent_id = "system_ai"; inst.agent_name = "시스템 AI"
    monkeypatch.setattr(cp, "get_current_registry_key", lambda: None, raising=False)
    fp = P.tool_policy_fingerprint()
    key = inst._get_session_key()
    assert key.endswith("#" + fp) and len(fp) == 8
    monkeypatch.setattr(P, "TOOL_POLICY", P.TOOL_POLICY + " (개정)")
    assert inst._get_session_key() != key                     # 정책이 바뀌면 키가 바뀐다
    # '새 대화'(bare key) 스윕이 파생 키도 지운다
    monkeypatch.setattr(cp, "_data_dir", lambda: tmp_path)
    store = cp.CliSessionStore("probe", "Probe")
    store.save_map({key: "sess-1", "다른": "sess-2"})
    store.clear_agent(key.split("#")[0])
    assert store.load_map() == {"다른": "sess-2"}


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
