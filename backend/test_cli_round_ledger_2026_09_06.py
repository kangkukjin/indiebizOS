"""CLI 프로바이더의 실행 라운드가 스텝 원장에 찍히는가 (2026-09-06).

재현한 결함: 연구 에이전트(Claude Code) 09-06 에피소드 11건의 model.round 42건이 전부
DeepSeek 원샷(oneshot:classify·oneshot:background)이고 **execution 라운드 0건** — CLI
서브프로세스 루프는 CLI 안에 살아 아무도 notify_round 를 부르지 않았다. 스텝 원장의 존재
이유(test_step_ledger 결함 A: 관측이 프로바이더에 결박돼 전환에 끊김)가 새 프로바이더에서
같은 모양으로 재발한 것. 여기서는 **벤더 어댑터가 라운드 경계에서 기록하는가**를 잠근다.

실행: .venv/bin/python -m pytest backend/test_cli_round_ledger_2026_09_06.py -q
"""
from types import SimpleNamespace

import boot_paths  # noqa: F401


def _provider():
    from providers import get_provider
    return get_provider("claude_code", api_key="", model="opus", system_prompt="")


def _assistant(model="claude-opus-5", text="안녕"):
    return {"type": "assistant", "message": {"model": model, "usage": {"input_tokens": 10},
                                             "content": [{"type": "text", "text": text}]}}


def test_assistant_event_notifies_execution_round(monkeypatch):
    """assistant 이벤트 1건 = notify_round 1회, 계수는 턴 안에서 1·2·3… 으로 오른다."""
    import providers.cli_provider as CP
    calls = []
    monkeypatch.setattr(CP, "notify_round",
                        lambda prov, model, n, budget: calls.append((prov, model, n, budget)))
    p = _provider()
    p._model_rounds = 0
    p._translate_stream_event(_assistant(), "", 0.0)
    p._translate_stream_event(_assistant(text="둘"), "", 0.0)
    assert [c[2] for c in calls] == [1, 2], calls
    assert calls[0][0] == p.CLI_DISPLAY and calls[0][1] == "claude-opus-5" and calls[0][3] == 0


def test_non_assistant_events_do_not_count(monkeypatch):
    """system·빈 user 이벤트는 라운드가 아니다 — 세면 왕복 수가 부풀어 효율 지표가 거짓이 된다."""
    import providers.cli_provider as CP
    calls = []
    monkeypatch.setattr(CP, "notify_round", lambda *a: calls.append(a))
    p = _provider()
    p._model_rounds = 0
    p._translate_stream_event({"type": "system", "subtype": "init"}, "", 0.0)
    p._translate_stream_event({"type": "user", "message": {"content": []}}, "", 0.0)
    assert calls == []


def test_round_lands_in_step_ledger_as_execution(monkeypatch):
    """monkeypatch 없이 실제 notify_round 까지 — 에피소드 steps 에 role=execution 으로 남는가.
    DB 쓰기(record_trajectory_event)만 막고 contextvar 에 가짜 에피소드를 건다."""
    import episode_logger as EL
    monkeypatch.setattr(EL, "record_trajectory_event", lambda *a, **k: None)
    fake_ep = SimpleNamespace(steps=[])
    token = EL._current_episode.set(fake_ep)
    try:
        p = _provider()
        p._model_rounds = 0
        p._translate_stream_event(_assistant(model="m"), "", 0.0)
    finally:
        EL._current_episode.reset(token)
    rounds = [s for s in fake_ep.steps if s.get("event") == "round"]
    assert len(rounds) == 1, fake_ep.steps
    assert rounds[0]["role"] == "execution" and rounds[0]["provider"] == p.CLI_DISPLAY
    assert rounds[0]["model"] == "m" and rounds[0]["round"] == 1


def test_turn_init_resets_round_counter():
    """턴 시작 초기화 블록이 계수를 0 으로 돌리는가 — 지난 턴 라운드가 새 턴에 누적되면 안 된다.
    (turn-init 은 stream 진입부라 실행 없이 소스로 잠근다: 초기화 블록 안에 대입이 있어야 한다.)"""
    import inspect
    import providers.cli_provider as CP
    src = inspect.getsource(CP.CliSubprocessProvider)
    head = src.split("self._reset_turn_state()", 1)[0]
    assert "self._model_rounds = 0" in head, "턴 초기화 블록(_reset_turn_state 호출 앞)에 _model_rounds = 0 이 없다"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
