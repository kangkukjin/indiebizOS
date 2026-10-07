"""규정 계승(framing_inheritance, 2026-10-07) — 회귀 고정물. 외부 호출 없음.

1) 정기: 같은 문장 + 직전 ACHIEVED → 의식을 깨우지 않고 경량 패치로 계승(inherited_repeat).
2) 정기: 직전이 ACHIEVED 가 아니면 계승하지 않는다.
3) 후속: 관계 판정 NEW → 의식 각성 / CONTINUE → 계승(inherited_followup), 초안·히스토리 요약은 안 잇는다.
4) 후속: 24시간 지난 직전 규정·히스토리 없는 턴은 판정 호출조차 없이 각성.
5) 권한은 계승되지 않는다(needs_repair·_repair_policy 벗김). 과제 연결은 행 id 로 정규화.
6) 패치가 허용 밖 필드·깨진 JSON 이면 계승 포기 → 각성.
7) `[task:…] 완료.` 는 CONTEXT_UPDATE 결정론 단서. "[task:…] 주간 재조사" 는 아니다.
"""
import json
from datetime import datetime, timedelta

import boot_paths  # noqa: F401
import pytest

import consciousness_agent
import framing_inheritance as fi
from cognitive_consciousness import CognitiveConsciousnessMixin
from thread_context import actor_context, set_goal_eval_outcome, clear_goal_eval_outcome


class Runner(CognitiveConsciousnessMixin):
    def __init__(self):
        self.config = {"id": "agent_t"}
        self.calls = 0

    def _run_consciousness(self, *a, **kw):
        self.calls += 1
        return {"task_framing": "새 규정", "achievement_criteria": "새 기준"}


FRAMING = {"task_framing": "문제: 2026-10-06 기준 직전 호 이후 변화를 조사한다", "achievement_criteria": "NEW 5건",
           "assumptions": ["원장이 있다"], "expert_choice": "편집자는 원장부터 본다", "history_summary": "옛 요약",
           "imagined_ibl": "[self:read]{path:\"x\"}", "needs_repair": True, "_repair_policy": 2,
           "scope": "pursuit", "title": "보고서", "goal_criteria": "매일", "pursuit_id": None}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "_store_root", lambda: tmp_path / "fi")
    clear_goal_eval_outcome()
    yield
    clear_goal_eval_outcome()


def _calls(monkeypatch, relation="CONTINUE", patch='{"task_framing": "문제: 2026-10-07 기준으로 고침"}'):
    seen = []

    def fake(prompt, system_prompt=None, images=None, role="classify"):
        seen.append(role)
        return relation if role == "classify" else patch
    monkeypatch.setattr(consciousness_agent, "oneshot_ai_call", fake)
    return seen


def _remember(runner, message, achieved=True, at=None):
    with actor_context(agent_id="agent_t", task_id="t0"):
        if achieved is not None:
            set_goal_eval_outcome(achieved, 0, status="ACHIEVED" if achieved else "UNKNOWN")
        rec = fi.remember(runner, message, dict(FRAMING))
    if at:
        data = fi._load("agent_t")
        data["last"]["at"] = at
        for v in data["repeat"].values():
            v["at"] = at
        fi._save("agent_t", data)
    return rec


def test_repeat_inherits_without_waking_consciousness(monkeypatch):
    r = Runner()
    _remember(r, "AI 동향 보고서 써줘.")
    seen = _calls(monkeypatch)
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse("AI 동향 보고서 써줘", [], "")
    assert r.calls == 0 and seen == ["background"]          # 관계 판정 없이 패치만
    assert out["_framing_source"] == "inherited_repeat"
    assert out["task_framing"].startswith("문제: 2026-10-07")
    assert out["achievement_criteria"] == "NEW 5건" and out["imagined_ibl"]   # 정기는 초안을 잇는다
    assert "history_summary" not in out
    assert "needs_repair" not in out and "_repair_policy" not in out       # 권한 미계승
    assert out["scope"] == "turn" and out["pursuit_id"] is None and "title" not in out


def test_repeat_requires_previous_achieved(monkeypatch):
    r = Runner()
    _remember(r, "AI 동향 보고서 써줘.", achieved=False)
    seen = _calls(monkeypatch)
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse("AI 동향 보고서 써줘.", [], "")
    assert r.calls == 1 and seen == [] and out["task_framing"] == "새 규정"


def test_followup_new_wakes_and_continue_inherits(monkeypatch):
    r = Runner()
    _remember(r, "오송 전세 매물 찾아줘")
    seen = _calls(monkeypatch, relation="NEW")
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse("프랑스 국채 위기 원인이 뭐야?", [{"role": "user", "content": "x"}], "")
    assert r.calls == 1 and seen == ["classify"] and out["task_framing"] == "새 규정"

    r2 = Runner()
    seen2 = _calls(monkeypatch, relation="CONTINUE",
                   patch='{"patch": {"task_framing": "문제: 직전 결과의 빈틈 확인", "assumptions": []}}')
    with actor_context(agent_id="agent_t", task_id="t2"):
        out2 = r2._run_consciousness_or_reuse("찾을 수 있는 소스를 다 찾은 건가?", [{"role": "user", "content": "x"}], "")
    assert r2.calls == 0 and seen2 == ["classify", "background"]
    assert out2["_framing_source"] == "inherited_followup" and out2["assumptions"] == []
    assert "imagined_ibl" not in out2 and "history_summary" not in out2
    assert out2["_inherited_from"]["task_id"] == "t0"


def test_followup_needs_history_and_freshness(monkeypatch):
    r = Runner()
    _remember(r, "오송 전세 매물 찾아줘")
    seen = _calls(monkeypatch)
    with actor_context(agent_id="agent_t", task_id="t1"):
        assert r._run_consciousness_or_reuse("그것도 해줘", [], "")["task_framing"] == "새 규정"
    assert seen == [] and r.calls == 1
    stale = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
    _remember(r, "오송 전세 매물 찾아줘", at=stale)
    with actor_context(agent_id="agent_t", task_id="t2"):
        r._run_consciousness_or_reuse("그것도 해줘", [{"role": "user", "content": "x"}], "")
    assert seen == [] and r.calls == 2


def test_patch_keeps_only_action_names_in_highlight(monkeypatch):
    r = Runner()
    _remember(r, "AI 동향 보고서 써줘.")
    _calls(monkeypatch, patch='{"capability_focus": {"hint": "원장부터", "highlight_actions": '
                              '["sense:search", "해당 섹션 재작성", "fn:주소마다읽기", " self:read "]}}')
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse("AI 동향 보고서 써줘.", [], "")
    assert r.calls == 0
    assert out["capability_focus"]["highlight_actions"] == ["sense:search", "fn:주소마다읽기", "self:read"]


@pytest.mark.parametrize("patch", ['{"needs_repair": true}', '{"scope": "pursuit", "title": "x"}', 'not json', '[]'])
def test_bad_patch_declines_inheritance(monkeypatch, patch):
    r = Runner()
    _remember(r, "AI 동향 보고서 써줘.")
    _calls(monkeypatch, patch=patch)
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse("AI 동향 보고서 써줘.", [], "")
    assert r.calls == 1 and out["task_framing"] == "새 규정"


def test_remember_normalizes_pursuit_row_and_keeps_bounded(monkeypatch):
    import pursuit_bind as pb
    r = Runner()
    binding = type("B", (), {"row": {"id": "pursuit_" + "a" * 32}})()
    monkeypatch.setattr(pb, "current", lambda: binding)
    rec = _remember(r, "주간 보고")
    assert rec["framing"]["scope"] == "pursuit" and rec["framing"]["pursuit_id"] == binding.row["id"]
    assert rec["pursuit_id"] == binding.row["id"] and rec["achieved"] is True
    monkeypatch.setattr(pb, "current", lambda: None)
    for i in range(fi.REPEAT_KEEP + 5):
        _remember(r, f"문장 {i}")
    assert len(fi._load("agent_t")["repeat"]) == fi.REPEAT_KEEP


def test_delegation_report_is_context_update():
    r = Runner()
    assert fi.is_delegation_report("[task:task_sysai_df5005c0] 완료.\n`/x/task_receipts.md`를 읽었고")
    assert fi.is_delegation_report("[task:task_1] 완료")
    assert not fi.is_delegation_report("[task:task_8de006c2] 주간 재조사: 지난 조사 뒤 바뀐 파일")
    assert not fi.is_delegation_report("완료. 다음은?")
    assert r._decide_request_type("[task:task_sysai_df5005c0] 완료.\n결과입니다", 0.0, "") == ("CONTEXT_UPDATE", None)


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
