"""세션 리셋의 작업 경계 + 턴 원장의 캐시 사각지대 (2026-09-06).

실측(backend_runtime.log 08-22~09-06): Claude Code 876턴이 캐시 읽기 13.99억 토큰인데
[턴비용] 원장엔 캐시가 0 으로 남았다 — claude_code result 분기가 record_request 에
cache_read 를 안 넘겼다. 토큰 선택압(해마 avg_tokens·turn_budget 고정물)이 가장 큰 비용을
못 본 채 돌았다. 같은 날 사용자 결정으로 리셋 임계 500K→300K, 단 리셋은 **작업 경계**를
존중한다(ep718: 태스크 도중 리셋이 뿌리였지 임계값이 아니었다).

실행: .venv/bin/python -m pytest backend/test_session_reset_boundary_2026_09_06.py -q
"""
import boot_paths  # noqa: F401


def _provider():
    from providers import get_provider
    return get_provider("claude_code", api_key="", model="opus", system_prompt="")


# ── 원장: result 이벤트의 캐시분이 턴 원장에 든다 ──

def test_result_event_feeds_cache_into_turn_ledger():
    from providers.base import (begin_turn_token_ledger, read_turn_tokens,
                                read_turn_cache_read_tokens)
    begin_turn_token_ledger()
    p = _provider()
    p._translate_stream_event(
        {"type": "result", "result": "끝",
         "usage": {"input_tokens": 100, "output_tokens": 50,
                   "cache_read_input_tokens": 9_000, "cache_creation_input_tokens": 850}},
        "", 0.0)
    # input 은 전체 프롬프트(input+cache_read+cache_create) — anthropic.py 와 같은 규약
    assert read_turn_tokens() == 100 + 9_000 + 850 + 50
    assert read_turn_cache_read_tokens() == 9_000


def test_result_event_without_cache_fields_still_records():
    from providers.base import begin_turn_token_ledger, read_turn_tokens, read_turn_cache_read_tokens
    begin_turn_token_ledger()
    p = _provider()
    p._translate_stream_event({"type": "result", "result": "끝",
                               "usage": {"input_tokens": 7, "output_tokens": 3}}, "", 0.0)
    assert read_turn_tokens() == 10 and read_turn_cache_read_tokens() == 0


# ── 실행 호출 서수: 파이프라인 밖(원장 없음)=0, 턴 안에서는 0·1·2… ──

def test_execution_call_ordinal_counts_within_turn():
    from providers.base import begin_turn_token_ledger, note_execution_call, _turn_token_ledger
    _turn_token_ledger.set(None)
    assert note_execution_call() == 0 and note_execution_call() == 0   # 원장 없음 = 늘 첫 호출
    begin_turn_token_ledger()
    assert [note_execution_call() for _ in range(3)] == [0, 1, 2]
    begin_turn_token_ledger()                                         # 다음 턴 — 다시 0
    assert note_execution_call() == 0


# ── 리셋 판정 ──

def test_threshold_is_300k():
    p = _provider()
    assert p.SESSION_RESET_TOKEN_THRESHOLD == 300_000


def test_under_threshold_is_silent():
    p = _provider()
    p._execution_call_ordinal, p._prev_turn_incomplete = 0, False
    assert p._should_reset_session(300_000) == (False, "")


def test_first_call_over_threshold_resets():
    p = _provider()
    p._execution_call_ordinal, p._prev_turn_incomplete = 0, False
    do, why = p._should_reset_session(300_001)
    assert do and "fresh" in why


def test_rerun_in_same_turn_never_resets():
    """goal 재실행·자기반성·약속 재시도(서수≥1) — 크기와 무관하게 끊지 않는다(ep718 부류)."""
    p = _provider()
    p._execution_call_ordinal, p._prev_turn_incomplete = 1, False
    for size in (300_001, 5_000_000):
        do, why = p._should_reset_session(size)
        assert not do and "재호출" in why


def test_incomplete_previous_turn_gets_one_turn_grace_until_cap():
    """직전 턴 절단·마감 실패 → 한 턴 유예. 단 임계×배수를 넘으면 무조건 끊는다."""
    p = _provider()
    p._execution_call_ordinal, p._prev_turn_incomplete = 0, True
    do, why = p._should_reset_session(450_000)
    assert not do and "유예" in why
    do, why = p._should_reset_session(600_001)      # 300K × 2 초과
    assert do


def test_turn_head_snapshots_previous_incompleteness_before_clearing():
    """턴 머리는 직전 턴의 stop_reason/failure 를 초기화하기 *전에* 스냅샷한다 —
    순서가 뒤집히면 유예 조건이 영원히 False 다."""
    from providers.base import begin_turn_token_ledger
    begin_turn_token_ledger()
    p = _provider()
    p._last_stop_reason = "max_tokens"
    p._client = None                                   # 초기화 직후 조기 반환 경로로 헤드만 실행
    list(p.process_message_stream("x", history=[]))
    assert p._prev_turn_incomplete is True
    assert p.last_failure_kind is None
    assert p._execution_call_ordinal == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
