"""Codex 토큰 회계 관문 — 누적 합계를 컨텍스트로 오인하지 않는지 본다.

★사고(실측 2026-08-31, ep2442~2485): Codex `turn.completed` 의 `usage.input_tokens` 는
그 턴의 컨텍스트가 아니라 스레드가 살아온 **모든 라운드의 입력 합계**다
(`total_token_usage`). 이걸 세션 크기로 읽던 탓에 도구를 몇 번만 써도 임계를 넘어
19턴 중 7턴에서 멀쩡한 세션이 끊겼고(읽은 값 3,195,716 / 실제 마지막 라운드 144,266),
같은 값이 [턴비용] → avg_tokens(토큰 선택압)까지 5~40배로 부풀렸다.

진짜 컨텍스트는 Codex 자신의 롤아웃 `token_count` 이벤트의 `last_token_usage` 에 있다.
"""
import json

import boot_paths  # noqa: F401


def _rollout(tmp_path, thread_id, rounds, window=258_400, turns=1):
    """token_count 이벤트가 있는 최소 롤아웃 파일. rounds = [(last_in, total_in), ...]"""
    day = tmp_path / "sessions" / "2026" / "08" / "31"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-08-31T00-00-00-{thread_id}.jsonl"
    lines = []
    for last_in, total_in in rounds:
        lines.append(json.dumps({"type": "event_msg", "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {"input_tokens": total_in, "output_tokens": 1},
                "last_token_usage": {"input_tokens": last_in, "output_tokens": 1},
                "model_context_window": window,
            }}}, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _provider():
    from providers import get_provider
    return get_provider("codex", api_key="", model="gpt-5.6-sol:high",
                        system_prompt="지침", agent_id="ag")


def test_context_is_last_round_not_thread_total(tmp_path, monkeypatch):
    """실측 ep2485 재현: 누적 667,906 이 아니라 마지막 라운드 94,064 를 세션 크기로 본다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _rollout(tmp_path, "thread-a", [(66_562, 66_562), (71_240, 137_802), (94_064, 667_906)])

    p = _provider()
    assert p._measure_context_size("thread-a") == 94_064
    # 같은 읽기가 이 턴의 비용 기준선도 잡는다
    assert p._turn_base_total == 667_906


def test_turn_cost_is_delta_not_thread_total(tmp_path, monkeypatch):
    """resume 턴의 [턴비용] 은 지난 턴들까지 합산한 누적이 아니라 이 턴의 몫이다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _rollout(tmp_path, "thread-b", [(94_064, 667_906)])

    p = _provider()
    p._reset_turn_state()
    p._measure_context_size("thread-b")          # 기준선 667,906
    p._translate_stream_event(
        {"type": "turn.completed",
         "usage": {"input_tokens": 760_000, "output_tokens": 500,
                   "cached_input_tokens": 700_000}},
        "", 0.0)
    assert p.metrics.total_input_tokens == 760_000 - 667_906
    # 누적을 컨텍스트로 남기지 않는다 — 상위 record_size 가 실측값을 덮어쓰면 안 된다
    assert p._last_context_size == 0


def test_fresh_turn_cost_is_full_usage(tmp_path, monkeypatch):
    """fresh 턴은 기준선이 없으므로 누적 = 이 턴의 몫이다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    p = _provider()
    p._reset_turn_state()
    p._translate_stream_event(
        {"type": "turn.completed",
         "usage": {"input_tokens": 66_036, "output_tokens": 10}}, "", 0.0)
    assert p.metrics.total_input_tokens == 66_036


def test_unreadable_rollout_measures_nothing(tmp_path, monkeypatch):
    """롤아웃을 못 읽으면 추정하지 않는다 — None(=저장값 사용)."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert _provider()._measure_context_size("없는스레드") is None


def test_reset_threshold_derives_from_model_window(tmp_path, monkeypatch):
    """임계는 상속받은 500K(창 1M Claude 기준)가 아니라 Codex 창에서 파생된다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-5.6-sol", "context_window": 272_000,
         "effective_context_window_percent": 95}]}), encoding="utf-8")

    p = _provider()
    assert p.SESSION_RESET_TOKEN_THRESHOLD == 129_200      # 258,400 의 절반
    # 롤아웃이 보고한 창이 있으면 그쪽이 이긴다 (카탈로그가 낡아도 실측이 산다)
    _rollout(tmp_path, "thread-c", [(1_000, 1_000)], window=100_000)
    p._measure_context_size("thread-c")
    assert p.SESSION_RESET_TOKEN_THRESHOLD == 50_000


def test_measured_size_beats_stored_size(monkeypatch):
    """상위 관문: 벤더 실측이 있으면 지난 턴 저장값 대신 그 값으로 리셋을 판정한다."""
    from providers.cli_provider import CliSubprocessProvider
    import inspect

    src = inspect.getsource(CliSubprocessProvider.process_message_stream)
    assert "_measure_context_size(resume_session_id)" in src, (
        "세션 크기 판정이 실측 훅을 거치지 않는다 — 벤더 누적값이 다시 새어든다")


if __name__ == "__main__":
    import sys

    import pytest

    raise SystemExit(pytest.main([__file__, "-v"] + sys.argv[1:]))
