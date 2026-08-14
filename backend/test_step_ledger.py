"""구조화 스텝 원장 + 역할 전환 원자화 + 직결 반복 가드 회귀 테스트 (2026-08-14, 2탄)

재현하는 결함들:
  A. execution_rounds 가 `[Gemini] 라운드` 정규식에 결박 — 프로바이더 전환(gemini→
     anthropic/claude_code)만으로 관측이 조용히 끊김(최근 200 에피소드 0건 실측).
     → 프로바이더 무관 구조화 원장(notify_round) + 정규식은 이름-무관 폴백.
  B. 역할 전환이 4+1 필드 개별 대입 — 과거 agent_id 누락이 identity 유실을 실제로 냄.
     → _CONTEXT_FIELDS 단일 진실 + _carry_context 원자 복사 + 전환의 구조화 기록.
  C. 반복 호출 가드가 gemini 프로바이더에만(별개 정책) — 직결 경로 공통 가드 부재.
     → repeat_guard 공용 코어 + execute_tool 어댑터 (CC 어댑터와 코어 공유).

실행: python3 backend/test_step_ledger.py
★live world_pulse.db 에 테스트 에피소드를 쓰고 반드시 지운다(원상복구 원칙).
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def test_class_method_snapshot():
    """★메서드 삼킴 가드 (2026-08-15 실측 회귀의 재발 방지): 클래스 본문 중간에 모듈
    함수를 끼우면 뒤의 메서드가 마지막 함수의 중첩 지역 함수로 조용히 삼켜진다 —
    py_compile 통과·기존 테스트 통과·런타임 AttributeError. 공개 계약 집합을 스냅샷으로
    고정해 다음번엔 소리가 나게 한다."""
    import episode_logger as EL
    expected = {"install", "start_episode", "end_episode", "current", "refresh_episode"}
    have = {m for m in dir(EL.EpisodeLogger) if not m.startswith("_")}
    assert expected <= have, f"EpisodeLogger 메서드 삼킴/누락: {expected - have}"
    # 모듈 함수 셋도 모듈 레벨에 실재해야 (클래스 안으로 끌려 들어가지 않았는지)
    for fn in ("set_step_role", "notify_round", "record_role_switch"):
        assert callable(getattr(EL, fn)), fn
    print("OK 메서드 집합 스냅샷 (삼킴 가드)")


def test_step_ledger_roundtrip():
    import episode_logger as EL
    ids = []
    try:
        EL.EpisodeLogger.start_episode("test_step_ledger", "스텝 원장 테스트")
        ep = EL.EpisodeLogger.current()
        assert ep is not None and ep.steps == []
        # 프로바이더 무관 기록 + 역할 태그
        EL.notify_round("Anthropic", "claude-x", 1, 30)
        EL.notify_round("Anthropic", "claude-x", 2, 30)
        EL.set_step_role("forage")
        EL.record_role_switch("forage", "DeepSeekHTTP", "v4-flash")
        EL.notify_round("DeepSeekHTTP", "v4-flash", 1, 70)
        EL.set_step_role("")
        EL.notify_round("Anthropic", "claude-x", 3, 30)
        # 원샷 라운드는 execution_rounds 산정에서 제외되어야 (CC 턴에서 "실행 1라운드"
        # 사칭 방지 — 2026-08-15 라이브 실측). 원장에는 남는다(해상도용).
        EL.set_step_role("oneshot:classify")
        EL.notify_round("DeepSeek", "v4-flash", 1, 30)
        EL.set_step_role("")
        assert len(ep.steps) == 6
        assert ep.steps[2]["event"] == "switch" and ep.steps[3]["role"] == "forage"
        EL.EpisodeLogger.end_episode()

        conn = EL._get_db()
        row = conn.execute(
            "SELECT id, episode_id, execution_rounds, steps FROM episode_summary "
            "WHERE agent='test_step_ledger' ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None, "summary 미저장"
        ids = [("episode_summary", row[0]), ("episode_log", row[1])]
        assert row[2] == 3, f"execution_rounds={row[2]} (max round 여야)"
        steps = json.loads(row[3])
        assert len(steps) == 6 and steps[0]["provider"] == "Anthropic"
        conn.close()
        print("OK 스텝 원장 왕복 (기록→저장→execution_rounds)")
    finally:
        conn = EL._get_db()
        for table, rid in ids:
            if rid:
                conn.execute(f"DELETE FROM {table} WHERE id = ?", (rid,))
        conn.commit()
        conn.close()


def test_pure_oneshot_turn_is_null():
    """★폴백 사칭 가드 (4라운드 감사 실측): 원장에 원샷 라운드만 있는 턴(claude_code
    실행)은 execution_rounds=NULL 이어야 한다 — 로그에 원샷 라운드 print 가 있어도
    폴백 정규식을 타면 안 된다(원장 분기에서 걷어낸 사칭이 폴백에서 되살아나던 구멍).
    주 경로만 테스트하고 폴백은 안 하던 패턴의 재발 방지."""
    import episode_logger as EL
    from datetime import datetime
    steps = [
        {"event": "round", "provider": "DeepSeek", "model": "v4-flash", "round": 1,
         "budget": 30, "role": "oneshot:classify"},
        {"event": "switch", "role": "system_repair", "provider": "ClaudeCode", "model": "opus"},
    ]
    log = "…\n[DeepSeek] 라운드 1/30 시작 (role=oneshot:classify)\n…"
    EL._extract_and_save_summary(None, datetime.now(), "test_oneshot_null", "m", log, 1,
                                 steps=steps)
    conn = EL._get_db()
    try:
        row = conn.execute(
            "SELECT id, execution_rounds FROM episode_summary WHERE agent='test_oneshot_null' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row and row[1] is None, f"원샷-만 턴이 NULL 이 아님(사칭): {row}"
        conn.execute("DELETE FROM episode_summary WHERE id = ?", (row[0],))
        conn.commit()
    finally:
        conn.close()
    print("OK 순수 원샷 턴 → NULL (폴백 사칭 가드)")


def test_regex_fallback_provider_agnostic():
    """원장이 없을 때(claude_code 등)의 폴백 정규식 — 프로바이더 이름 무관."""
    import episode_logger as EL
    from datetime import datetime
    log = "…\n[Anthropic] 라운드 4/30 시작\n…\n[Anthropic] 라운드 7/30 시작\n…"
    EL._extract_and_save_summary(None, datetime.now(), "test_regex_fb", "m", log, 1, steps=None)
    conn = EL._get_db()
    try:
        row = conn.execute(
            "SELECT id, execution_rounds FROM episode_summary WHERE agent='test_regex_fb' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row and row[1] == 7, f"폴백 정규식이 [Anthropic] 을 못 잡음: {row}"
        conn.execute("DELETE FROM episode_summary WHERE id = ?", (row[0],))
        conn.commit()
    finally:
        conn.close()
    print("OK 폴백 정규식 — 프로바이더 이름 무관")


def test_carry_context_atomic():
    from system_ai_core import _carry_context, _CONTEXT_FIELDS
    src = SimpleNamespace(system_prompt="P", tools=[{"name": "t"}], agent_id="system_ai",
                          project_path="/p", agent_name="비서")
    dst = SimpleNamespace(system_prompt="", tools=None, agent_id="", project_path="",
                          agent_name="")
    _carry_context(dst, src)
    for f in _CONTEXT_FIELDS:
        assert getattr(dst, f) == getattr(src, f), f
    print("OK 역할 전환 원자 복사 (5필드 단일 진실)")


def test_direct_adapter_via_execute_tool():
    """직결 어댑터: execute_tool 이 공용 코어로 카운트하고 str 결과에 조언을 부록."""
    import repeat_guard
    from system_tools import execute_tool
    repeat_guard.reset_all()
    r1 = execute_tool("no_such_tool_xyz", {"a": 1}, "/tmp", agent_id="test_agent")
    r2 = execute_tool("no_such_tool_xyz", {"a": 1}, "/tmp", agent_id="test_agent")
    r3 = execute_tool("no_such_tool_xyz", {"a": 1}, "/tmp", agent_id="test_agent")
    assert "[반복 감지]" not in r1 and "[반복 감지]" not in r2
    assert "[반복 감지]" in r3, r3[-200:]  # 오류 결과도 카운트 (설계)
    r4 = execute_tool("no_such_tool_xyz", {"a": 2}, "/tmp", agent_id="test_agent")
    assert "[반복 감지]" not in r4  # 다른 인자 → 리셋
    repeat_guard.reset_all()
    print("OK 직결 어댑터 (3연타 조언·오류 카운트·리셋)")


if __name__ == '__main__':
    test_class_method_snapshot()
    test_step_ledger_roundtrip()
    test_pure_oneshot_turn_is_null()
    test_regex_fallback_provider_agnostic()
    test_carry_context_atomic()
    test_direct_adapter_via_execute_tool()
    print("ALL PASS")
