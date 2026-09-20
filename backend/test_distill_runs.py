"""증류의 주행 기록 훅 회귀 (2026-09-04, 사용자 판정 "제안대로 집행").

계약(2026-09-20): 학습 가치가 없어 대표 절차를 선택하지 않은 턴은 실행 원장에만
남긴다. 선택·검증된 절차만 가지에 기록하고 탐색 전체를 복제하지 않는다.

실행: .venv/bin/python -m pytest backend/test_distill_runs.py -q
"""
import json
import os
import sys
import types

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401


def _arm(monkeypatch, reply):
    import ibl_usage_db as mod
    import thread_context
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: {"achieved": True, "severity": 0})
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    fake = types.ModuleType("consciousness_agent")
    fake.oneshot_ai_call = lambda **kw: json.dumps(reply, ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    import hippo_tree
    calls = []
    monkeypatch.setattr(hippo_tree, "note_run", lambda topic, intent, sentences, ok=True, **kw: calls.append((topic, intent, list(sentences), ok)) or {"success": True, "sentences": len(sentences)})
    monkeypatch.setattr(hippo_tree, "map_text", lambda *a, **k: "- 보고서/부동산 발굴 (3)")
    return calls


CALLS = [{"tool_name": "execute_ibl", "input": {"code": '[self:memory]{op: "recall", node: "보고서/부동산 발굴"}'}, "success": True},
         {"tool_name": "execute_ibl", "input": {"code": '[sense:realty]{region: "의정부"} >> [table:take]{n: 5}'}, "success": True},
         {"tool_name": "execute_ibl", "input": {"code": '[self:write]{path: "x.md", content: "y"}'}, "success": False},
         {"tool_name": "Bash", "input": {"command": "ls"}, "success": True}]


def test_skip_does_not_duplicate_execution_log_into_recall(monkeypatch):
    import ibl_usage_rag as rag
    calls = _arm(monkeypatch, {"intent": "부동산 보고서 작성", "code": "", "topic": "보고서/부동산 발굴"})
    assert rag.distill_experience("부동산 발굴 보고서 써줘", CALLS, top_score=0.3) is False
    assert calls == []  # 학습 가치 없는 원문은 실행 원장에만 남긴다.


def test_run_not_noted_for_single_sentence_or_no_topic(monkeypatch):
    import ibl_usage_rag as rag
    calls = _arm(monkeypatch, {"intent": "x", "code": "", "topic": ""})
    rag.distill_experience("x", CALLS, top_score=0.3)
    assert calls == []
    calls = _arm(monkeypatch, {"intent": "x", "code": "", "topic": "보고서/부동산 발굴"})
    rag.distill_experience("x", CALLS[:1], top_score=0.3)
    assert calls == []


def test_prompt_prefers_executed_composition():
    import ibl_usage_rag as rag
    p = " ".join(rag._build_distill_prompt("u", "  1. [a:b] & [c:d]", "", "").split())
    assert "합성문" in p and "그 문장을 대표로" in p
    assert "단일 액션으로 줄이지 마라" in p


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
