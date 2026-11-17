"""규정 계승을 없앤 뒤의 고정물(2026-11-17, 사용자 판정) — 외부 호출 없음.

있던 것: 같은 문장의 정기 실행이나 '같은 과제의 후속'이면 의식을 깨우지 않고 경량 모델이 직전 규정을
고쳐 썼다(2026-10-07). 에피소드 6192 에서 시제품 제작 요청이 후속으로 판정돼 경량 모델이 92분짜리 과제의
규정을 새로 썼고, 사용자가 주문한 심층실행 단계가 빠졌다.

1) THINK 는 어떤 경우에도 의식이 새로 규정한다 — 같은 문장을 되풀이해도, 직전 과제에 이어지는 말이어도.
   경량 모델은 한 번도 불리지 않는다.
2) 계승 함수는 모듈에 없다(되살아나면 이 검사가 잡는다).
3) 직전 규정의 기록은 남는다 — 권한·과제 연결은 벗기고, 문장별 기록 수는 묶인다.
4) `[task:…] 완료.` 는 CONTEXT_UPDATE 결정론 단서. "[task:…] 주간 재조사" 는 아니다.
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
            set_goal_eval_outcome(achieved, 0, status="ACHIEVED" if achieved else "UNKNOWN",
                                  goal_status="ACHIEVED" if achieved else "UNKNOWN")
        rec = fi.remember(runner, message, dict(FRAMING))
    if at:
        data = fi._load("agent_t")
        data["last"]["at"] = at
        for v in data["repeat"].values():
            v["at"] = at
        fi._save("agent_t", data)
    return rec


@pytest.mark.parametrize("message,history,achieved", [
    ("AI 동향 보고서 써줘", [], True),                                              # 같은 문장의 정기 실행
    ("AI 동향 보고서 써줘.", [], False),
    ("찾을 수 있는 소스를 다 찾은 건가?", [{"role": "user", "content": "x"}], True),      # 직전 결과에 대한 되물음
    ("그것도 해줘", [{"role": "user", "content": "x"}], True),                        # 이어 하기
    ("서울시의회 AI 의정비서 시제품을 만들어 봐. 10단계 심층실행을 해.", [{"role": "user", "content": "x"}], True),
])
def test_think_always_wakes_consciousness(monkeypatch, message, history, achieved):
    r = Runner()
    _remember(r, "AI 동향 보고서 써줘.", achieved=achieved)
    seen = _calls(monkeypatch)
    with actor_context(agent_id="agent_t", task_id="t1"):
        out = r._run_consciousness_or_reuse(message, history, "")
    assert r.calls == 1 and seen == []                    # 의식이 불리고, 경량 모델은 불리지 않는다
    assert out["task_framing"] == "새 규정" and out["_framing_source"] == "fresh_consciousness"
    assert "_inherited_from" not in out


def test_inheritance_is_gone_from_the_module():
    for name in ("inherit", "_inherit", "_candidate", "_patch", "_parse_patch", "PATCHABLE"):
        assert not hasattr(fi, name), name
    from pathlib import Path
    prompts = Path(fi.__file__).resolve().parents[2] / "data" / "common_prompts"
    assert not (prompts / "framing_patch_prompt.md").exists()


def test_remember_keeps_only_framing_and_is_bounded(monkeypatch):
    r = Runner()
    rec = _remember(r, "주간 보고")
    assert not {"scope", "pursuit_id", "title", "goal_criteria"} & rec["framing"].keys()
    assert "pursuit_id" not in rec and rec["achieved"] is True
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
