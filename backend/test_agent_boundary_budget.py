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
