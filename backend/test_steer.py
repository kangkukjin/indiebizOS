"""턴 중 조향(steer) + 역할 해상도 + dict 부록 회귀 테스트 (2026-08-15)

재현하는 갭들 (indiebizOS 감사 3차 보고):
  A. 개입 수단이 중단(cancel)뿐 — 돌고 있는 작업에 지시를 밀어 넣을 길이 없음.
     → steer_inbox 코어 + 배달 어댑터 둘(직결=execute_tool / CC=/ibl/execute MCP 호출)
       + 입구 둘(HTTP /system-ai/steer + WS 실행 중 메시지 자동 조향 전환).
  B. 원샷 호출(무의식·의식·평가)이 전부 role=execution 으로 원장에 뭉개짐(에피소드
     1083 실측) → 태그를 스왑 이음매가 아닌 호출 이음매로 (oneshot:<role>/consciousness).
  C. 반복 조언이 str 결과에만 붙어 dict 반환 도구에서 조용히 소실 → content 필드 부록.

실행: python3 backend/test_steer.py
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def test_inbox_core():
    import steer_inbox as SI
    SI.clear("t1")
    assert SI.post("t1", "  ") == 0          # 빈 조향 거부
    assert SI.post("t1", "부동산 말고 주식으로") == 1
    assert SI.post("t1", "그리고 표로 정리해") == 2
    texts = SI.drain("t1")
    assert len(texts) == 2 and "주식" in texts[0]
    assert SI.drain("t1") == []              # drain 은 비운다
    for i in range(9):
        SI.post("t1", f"m{i}")
    assert len(SI.drain("t1")) == SI._MAX_PER_KEY  # 키당 상한
    SI.post("t1", "stale")
    assert SI.clear("t1") == 1 and SI.drain("t1") == []  # 턴 종료 폐기
    r = SI.render(["a", "b"])
    assert "[사용자 조향]" in r and "- a" in r and SI.render([]) == ""
    print("OK 인박스 코어 (post/drain/clear/render/상한)")


def test_direct_delivery_via_execute_tool():
    """직결 어댑터: 조향이 다음 도구 결과에 부록으로 실린다 (반복 조언과 같은 채널)."""
    import steer_inbox as SI
    import repeat_guard
    from system_tools import execute_tool
    repeat_guard.reset_all()
    SI.clear("steer_agent")
    SI.post("steer_agent", "지금부터는 요약만 해")
    r = execute_tool("no_such_tool_st", {"a": 1}, "/tmp", agent_id="steer_agent")
    assert "[사용자 조향]" in r and "요약만" in r
    r2 = execute_tool("no_such_tool_st", {"a": 1}, "/tmp", agent_id="steer_agent")
    assert "[사용자 조향]" not in r2  # drain 이라 1회만 배달
    repeat_guard.reset_all()
    print("OK 직결 배달 (1회 배달·재배달 없음)")


def test_cc_delivery_attach():
    """CC 어댑터: 명시적 agent_id(MCP 호출)만 봉투에 동봉 — 앱/수동 모드 무오염."""
    import steer_inbox as SI
    from api_ibl import _attach_steer
    SI.post("cc_agent", "링크도 같이 줘")
    env = _attach_steer({"result": "x"}, "cc_agent")
    assert "steer_notice" in env and "링크도" in env["steer_notice"]
    env2 = _attach_steer({"result": "x"}, "cc_agent")
    assert "steer_notice" not in env2          # drain — 1회만
    SI.post("cc_agent", "y")
    assert "steer_notice" not in _attach_steer({"result": "x"}, "")  # 앱/수동(무신원) 게이트
    SI.clear("cc_agent")
    print("OK CC 배달 (agent_id 게이트·1회 배달)")


def test_dict_advisory_appendix():
    """C: dict 결과({content,...})에도 반복 조언·조향이 content 부록으로 붙는다."""
    import steer_inbox as SI
    import repeat_guard
    import system_tools as ST
    repeat_guard.reset_all()
    orig = ST._execute_tool_inner
    try:
        ST._execute_tool_inner = lambda *a, **k: {"content": "본문", "images": [{"base64": "x"}]}
        for _ in range(2):
            ST.execute_tool("dict_tool", {"q": 1}, "/tmp", agent_id="dt")
        r3 = ST.execute_tool("dict_tool", {"q": 1}, "/tmp", agent_id="dt")
        assert isinstance(r3, dict) and "[반복 감지]" in r3["content"], r3
        SI.post("dt", "조향도 dict 로")
        r4 = ST.execute_tool("dict_tool", {"q": 2}, "/tmp", agent_id="dt")
        assert "[사용자 조향]" in r4["content"]
    finally:
        ST._execute_tool_inner = orig
        repeat_guard.reset_all()
        SI.clear("dt")
    print("OK dict 부록 (조언·조향 모두 content 에)")


def test_role_tags_oneshot():
    """B: 원샷 헬퍼가 호출 이음매에서 역할 태그를 걸고 원복한다 → 원장 해상도."""
    import episode_logger as EL
    import consciousness_agent as CA

    class FakeProvider:
        system_prompt = ""
        def process_message(self, message, history=None, images=None, execute_tool=None):
            # 원샷 호출 중의 라운드가 어떤 role 로 찍히는지 재현
            EL.notify_round("Fake", "fake-model", 1, 30)
            return "ok"

    EL.EpisodeLogger.start_episode("test_role_tags", "역할 태그 테스트")
    ep = EL.EpisodeLogger.current()
    try:
        # system_ai_call 경로 (evaluate 등) — 리졸버를 우회해 가짜 프로바이더 주입
        orig = CA._resolve_oneshot_provider
        CA._resolve_oneshot_provider = lambda role: FakeProvider()
        try:
            CA.system_ai_call("p", system_prompt="s", role="evaluate")
            CA.oneshot_ai_call("p", system_prompt="s", role="classify")
        finally:
            CA._resolve_oneshot_provider = orig
        # 태그 원복 후의 일반 라운드는 execution
        EL.notify_round("Anthropic", "claude-x", 1, 30)
        roles = [s.get("role") for s in ep.steps if s.get("event") == "round"]
        assert roles == ["oneshot:evaluate", "oneshot:classify", "execution"], roles
    finally:
        # ★"라이브 DB 무접촉"은 2026-08-18 부로 거짓이 됐다(B18-2): start_episode 가
        # 그때부터 START 시점에 행을 먼저 연다(죽는 턴도 기록이 남게). 그래서 이 배터리는
        # ended_at NULL 인 고아를 매 실행마다 라이브 원장에 쌓아 왔다(실측 ep1423 외 다수).
        # 컨텍스트만 비우지 말고 연 행도 되돌린다 — 배터리의 원상복구 원칙.
        eid = getattr(ep, "episode_id", None)
        EL._current_episode.set(None)
        if eid:
            conn = EL._get_db()
            conn.execute("DELETE FROM episode_log WHERE id=?", (eid,))
            conn.commit()
            conn.close()
    print("OK 원샷 역할 태그 (evaluate/classify 구분 + 원복)")


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
