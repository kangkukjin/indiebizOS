"""증류의 주행 기록 훅 회귀 (2026-09-04, 사용자 판정 "제안대로 집행").

계약: 반성기가 대표 문장을 못 골라도(code "") topic 이 있고 성공 IBL 문장이 둘 이상이면 그 문장들을
가지 문서 `## 주행` 절에 남긴다 — 프로그램급 주행이 '재사용 패턴 없음'으로 학습 0건이 되던 자리.
대표 문장이 있을 때도 같이 남긴다. 반성 프롬프트는 실행된 합성문을 대표로 우선한다.

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
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
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


def test_run_noted_even_without_representative_code(monkeypatch):
    import ibl_usage_rag as rag
    calls = _arm(monkeypatch, {"intent": "부동산 보고서 작성", "code": "", "topic": "보고서/부동산 발굴"})
    assert rag.distill_experience("부동산 발굴 보고서 써줘", CALLS, top_score=0.3) is False
    assert len(calls) == 1
    topic, intent, sentences, ok = calls[0]
    assert topic == "보고서/부동산 발굴" and intent == "부동산 보고서 작성" and ok is True
    assert len(sentences) == 2 and all("[self:write]" not in s for s in sentences)   # 성공한 IBL 문장만, 순서대로


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
