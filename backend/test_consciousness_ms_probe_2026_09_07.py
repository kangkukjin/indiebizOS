"""의식 소요시간(consciousness_ms) 관측 결박 수리 회귀 테스트 (2026-09-07)

재현하는 결함:
  옛 추출은 정규식 latency=(숫자)ms 하나만 봤다 — 그건 Gemini 산문 방언이라 2026-07-12
  프로바이더 전환과 함께 조용히 끊겼다. 실측: 그 뒤 THINK 턴 161건 전부
  consciousness_ms NULL, x-ray 의 avg_consciousness_ms 는 두 달 내내 None.
  "의식 에이전트가 느린가"를 물어도 시스템이 제 수치로 답할 수 없었다.
  execution_rounds 가 2026-08-14 에 같은 병으로 수리된 자리 — 처방도 같다:
  구조화 원장(notify_usage)이 1차, 산문은 옛 로그 폴백.

실행: python3 -m pytest backend/test_consciousness_ms_probe_2026_09_07.py
★live world_pulse.db 에 테스트 행을 쓰고 반드시 지운다(원상복구 원칙).
"""
import sys
from datetime import datetime

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _summary_row(agent):
    import episode_logger as EL
    conn = EL._get_db()
    try:
        return conn.execute(
            "SELECT id, consciousness_ms FROM episode_summary WHERE agent=? "
            "ORDER BY id DESC LIMIT 1", (agent,)).fetchone()
    finally:
        conn.close()


def _cleanup(rid):
    import episode_logger as EL
    conn = EL._get_db()
    conn.execute("DELETE FROM episode_summary WHERE id = ?", (rid,))
    conn.commit()
    conn.close()


def test_ledger_is_primary():
    """원장에 role=consciousness usage 스텝이 있으면 프로바이더 이름과 무관하게 잡힌다."""
    import episode_logger as EL
    EL._ensure_episode_tables()
    steps = [
        {"event": "usage", "role": "oneshot:classify", "latency_ms": 830},
        {"event": "usage", "role": "consciousness", "latency_ms": 79290,
         "input": 59471, "output": 9680, "cache_read": 0},
        {"event": "round", "provider": "DeepSeek", "model": "v4", "round": 1,
         "budget": 100, "role": "execution"},
        {"event": "usage", "role": "execution", "latency_ms": 9266},
    ]
    EL._extract_and_save_summary(None, datetime.now(), "test_cms_ledger", "m",
                                 "[무의식] 분류: THINK\n", 229212, steps=steps)
    row = _summary_row("test_cms_ledger")
    try:
        assert row and row[1] == 79290, f"원장에서 의식 지연을 못 읽음: {row}"
    finally:
        if row:
            _cleanup(row[0])
    print("OK 구조화 원장이 1차 (프로바이더 이름 무관)")


def test_retry_is_summed():
    """빈 응답 재시도가 붙은 의식 호출은 턴이 실제로 기다린 총합이어야 한다."""
    import episode_logger as EL
    EL._ensure_episode_tables()
    steps = [
        {"event": "usage", "role": "consciousness", "latency_ms": 12000},
        {"event": "usage", "role": "consciousness", "latency_ms": 45000},
    ]
    EL._extract_and_save_summary(None, datetime.now(), "test_cms_retry", "m", "", 90000,
                                 steps=steps)
    row = _summary_row("test_cms_retry")
    try:
        assert row and row[1] == 57000, f"재시도 합산 실패: {row}"
    finally:
        if row:
            _cleanup(row[0])
    print("OK 재시도 합산")


def test_prose_dialects_fallback():
    """★결박 재발 가드: 원장 없는 옛 로그도 방언 3종이 모두 읽혀야 한다.
    옛 코드는 이 중 latency= 하나만 알아서, 나머지 둘에서 조용히 NULL 이 됐다."""
    import episode_logger as EL
    EL._ensure_episode_tables()
    dialects = {
        "gemini": ("[Gemini] 최종 응답 생성 (iteration=1, len=3661, latency=45100ms)", 45100),
        "record_usage": ("[OpenAI] 토큰: 입력=59471, 출력=9680, 추론=8329, "
                         "캐시적중=0, 지연=79290ms", 79290),
        "claude_code": ("[ClaudeCode/에이전트] result 93895ms in=2 out=5883 "
                        "cache_read=7043 cache_create=97121", 93895),
    }
    for name, (line, expect) in dialects.items():
        log = ("[ConsciousnessAgent] AI 호출 시작 (입력 9326자)\n"
               f"{line}\n[ConsciousnessAgent] AI 응답 수신 (2366자)\n")
        agent = f"test_cms_prose_{name}"
        EL._extract_and_save_summary(None, datetime.now(), agent, "m", log, 200000,
                                     steps=None)
        row = _summary_row(agent)
        try:
            assert row and row[1] == expect, f"방언 '{name}' 미인식: {row} (기대 {expect})"
        finally:
            if row:
                _cleanup(row[0])
    print(f"OK 산문 방언 폴백 {len(dialects)}종")


def test_no_consciousness_stays_null():
    """의식을 안 탄 턴(EXECUTE)은 NULL 이어야 한다 — 다른 호출의 지연을 사칭 금지."""
    import episode_logger as EL
    EL._ensure_episode_tables()
    steps = [{"event": "usage", "role": "execution", "latency_ms": 7776}]
    EL._extract_and_save_summary(None, datetime.now(), "test_cms_null", "m",
                                 "[무의식] 분류: EXECUTE\n"
                                 "[OpenAI] 토큰: 입력=33107, 출력=1074, 캐시적중=0, 지연=7776ms\n",
                                 2487273, steps=steps)
    row = _summary_row("test_cms_null")
    try:
        assert row and row[1] is None, f"EXECUTE 턴이 의식 지연을 사칭: {row}"
    finally:
        if row:
            _cleanup(row[0])
    print("OK 의식 없는 턴은 NULL (사칭 없음)")


def test_provider_entry_point_is_wired():
    """★뿌리 가드: 프로바이더 공통 진입점(record_usage)이 원장을 부르는가.
    이 한 줄이 빠지면 새 프로바이더가 붙을 때마다 관측이 다시 조용히 끊긴다."""
    import inspect
    from providers.base import ProviderMetrics
    src = inspect.getsource(ProviderMetrics.record_usage)
    assert "notify_usage" in src, "record_usage 가 스텝 원장을 안 부른다 — 관측 결박 재발"
    print("OK record_usage → notify_usage 배선")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
