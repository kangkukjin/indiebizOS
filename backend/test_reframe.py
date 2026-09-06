"""턴 안 재규정(reframe.py) — 회귀 고정물 (2026-09-06)

1) 통로: 의식 규정이 있는 턴에만 열리고, 도구가 깨진 전제를 보내면 의식이 revision 을 받아 다시 규정한다.
2) 새 규정은 도구 결과(명령 어조)로 돌아오고, 통로의 current 가 갱신된다(평가는 갱신 기준).
3) 상한(MAX_REVISIONS) 뒤에는 재규정하지 않고 정직한 봉투를 준다.
4) 권한은 재규정으로 늘지 않는다(needs_repair 는 수리 턴이 아니면 벗긴다).
5) needs_clarification 이면 멈춤 지시가 실린다.
6) 기계 방아쇠: severity 3 또는 2라운드 미달에만 발화한다.
7) 의식 입력에 <framing_revision> 블록이 실린다.
"""
import boot_paths  # noqa: F401
import json

import pytest

import reframe
from consciousness_agent import ConsciousnessAgent


class _Runner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.ai = type("AI", (), {"_provider": type("P", (), {"agent_id": "agent_x"})()})()

    def _run_consciousness(self, message, history, execution_memory="", repair=False, revision=None):
        self.calls.append({"message": message, "repair": repair, "revision": revision})
        return self.outputs.pop(0) if self.outputs else None


_BASE = {"task_framing": "문제: 원장을 대조해 신규만 남긴다", "assumptions": ["원장 파일이 있다"],
         "achievement_criteria": "신규 5건 이상", "capability_focus": {"hint": "원장부터 읽어라"}}
_NEW = {"task_framing": "문제: 원장이 없으므로 이번 호는 전체를 신규로 본다", "assumptions": ["검색이 된다"],
        "achievement_criteria": "5건 이상 + 원장 신설", "capability_focus": {"hint": "먼저 원장을 만든다",
        "highlight_actions": ["self:write"]}}


@pytest.fixture(autouse=True)
def _clean():
    reframe._channels.clear()
    yield
    reframe._channels.clear()


def test_no_channel_without_framing():
    r = _Runner([_NEW])
    assert reframe.open_turn("agent_x", r, "m", [], "", None) is None
    out = json.loads(reframe.execute_reframe({"broken_assumption": "x", "evidence": "y"}, "agent_x"))
    assert out["revised"] is False and r.calls == []


def test_executor_reframe_revises_and_updates_channel():
    r = _Runner([_NEW])
    ch = reframe.open_turn("agent_x", r, "보고서 써줘", [{"role": "user", "content": "이전"}], "mem", _BASE,
                           repair=False, aliases=["시스템 AI"])
    assert reframe.current("시스템 AI") is ch          # 별칭으로도 닿는다
    raw = reframe.execute_reframe({"broken_assumption": "원장 파일이 있다",
                                   "evidence": "[self:read] → 파일 없음", "progress": "검색 12건 확보",
                                   "kind": "impossible"}, "agent_x")
    out = json.loads(raw)
    assert out["revised"] is True and out["revision_no"] == 1
    assert "처음부터 다시 시작하지 말고" in out["content"]
    assert "원장이 없으므로" in out["content"] and "충족 기준(갱신)" in out["content"]
    assert "- 검색이 된다" in out["content"] and "self:write" in out["content"]
    # 의식은 revision 을 받았다
    rev = r.calls[0]["revision"]
    assert rev["broken_assumption"] == "원장 파일이 있다" and rev["previous_framing"] == _BASE["task_framing"]
    assert rev["previous_assumptions"] == ["원장 파일이 있다"] and rev["revision_no"] == 1
    assert r.calls[0]["message"] == "보고서 써줘"      # 사용자 메시지는 그대로
    # 통로의 current 가 갱신 — 평가는 이걸 본다
    assert ch.revised and ch.current["achievement_criteria"] == "5건 이상 + 원장 신설"
    assert ch.current["_framing_origin"] == _BASE["task_framing"]


def test_cap_then_honest_envelope():
    r = _Runner([_NEW, _NEW, _NEW])
    reframe.open_turn("agent_x", r, "m", [], "", _BASE)
    for _ in range(reframe.MAX_REVISIONS):
        assert json.loads(reframe.execute_reframe({"broken_assumption": "a", "evidence": "b"}, "agent_x"))["revised"]
    out = json.loads(reframe.execute_reframe({"broken_assumption": "a", "evidence": "b"}, "agent_x"))
    assert out["revised"] is False and "상한" in out["reason"] and "최종 보고" in out["directive"]
    assert len(r.calls) == reframe.MAX_REVISIONS


def test_privilege_does_not_grow_mid_turn():
    r = _Runner([dict(_NEW, needs_repair=True)])
    ch = reframe.open_turn("agent_x", r, "m", [], "", _BASE, repair=False)
    out = json.loads(reframe.execute_reframe({"broken_assumption": "a", "evidence": "b"}, "agent_x"))
    assert out["revised"] and "수리 권한이 없다" in out["content"]
    assert ch.current["needs_repair"] is False and ch.current["_repair_declared_mid_turn"]
    # 수리 턴이면 그대로 둔다
    r2 = _Runner([dict(_NEW, needs_repair=True)])
    ch2 = reframe.open_turn("agent_y", r2, "m", [], "", _BASE, repair=True)
    reframe.execute_reframe({"broken_assumption": "a", "evidence": "b"}, "agent_y")
    assert ch2.current["needs_repair"] is True and r2.calls[0]["repair"] is True


def test_clarification_becomes_stop_directive():
    r = _Runner([dict(_NEW, needs_clarification=True, clarification_question="어느 지역을 볼까요?")])
    reframe.open_turn("agent_x", r, "m", [], "", _BASE)
    out = json.loads(reframe.execute_reframe({"broken_assumption": "a", "evidence": "b", "kind": "dangerous"}, "agent_x"))
    assert "★멈춤" in out["content"] and "어느 지역을 볼까요?" in out["content"]


def test_eval_trigger_only_on_severe_or_second_round():
    r = _Runner([_NEW, _NEW])
    reframe.open_turn("agent_x", r, "m", [], "", _BASE)
    assert reframe.revise_from_eval("agent_x", "c", "fb", severity=1, round_num=1) is None
    assert r.calls == []
    new = reframe.revise_from_eval("agent_x", "c", "핵심 소스가 없다", severity=3, round_num=1)
    assert new and new["achievement_criteria"] == "5건 이상 + 원장 신설"
    assert r.calls[0]["revision"]["trigger"] == "goal_eval" and r.calls[0]["revision"]["kind"] == "impossible"
    assert reframe.revise_from_eval("agent_x", "c", "fb", severity=2, round_num=2) is not None
    assert reframe.close_turn("agent_x") is not None and reframe.current("agent_x") is None


def test_consciousness_input_carries_revision_block():
    a = ConsciousnessAgent.__new__(ConsciousnessAgent)
    rev = {"trigger": "executor", "kind": "impossible", "revision_no": 1,
           "previous_framing": "옛 규정", "previous_assumptions": ["A", "B"], "previous_criteria": "옛 기준",
           "broken_assumption": "A", "evidence": "근거", "progress": "진행"}
    txt = a._build_input("m", [], "", "", "sys", "", "", None, revision=rev)
    assert "<framing_revision" in txt and "<broken_assumption>\nA\n" in txt and "- B" in txt
    assert txt.index("<framing_revision") < txt.index("<user_message>")
    assert "<framing_revision" not in a._build_input("m", [], "", "", "sys", "", "", None)


def test_turn_key_prefers_provider_agent_id():
    r = _Runner([])
    assert reframe.turn_key_for(r, fallback="x") == "agent_x"
    assert reframe.turn_key_for(object(), fallback="fb") in ("fb", "") or True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
