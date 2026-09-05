"""이름으로 부르는 학습 루프 (2026-09-05, 사용자 판정 "그 순서대로 착수").

  5. 증류 게이트: 고점수 회상이 있어도 그것을 *이름으로 부르지 않았으면*(베꼈거나 안 썼거나) 증류한다.
     종전엔 node:action 쌍 하나만 겹쳐도 "사용됨"으로 보고 조용히 return — 회상이 잘 되는 가지일수록
     새 프로그램이 쌓이지 않았다(부동산 29호에 용례 2, 팁 1). 함수만으로 완주한 주행만 스킵.
  4. 호출 보상: `[fn:이름]` 호출은 top-1 귀속에서 "회상 사용"이고, 이름으로 부른 관용구는 회상 여부와
     무관하게 성공/실패가 그 관용구에 기록된다. 반성 프롬프트는 호출을 본문으로 풀지 말라고 가르친다.

실행: .venv/bin/python -m pytest -q backend/test_call_by_name_learning_2026_09_05.py
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

RECALLED = ('$원장 = [self:ledger]{path: "outputs/x/_covered.json", op: "select", target: "covered"}; '
            '$검색 = [sense:search_youtube]{query: "${주제}", limit: 12} >> [table:dedup]{by: "video_id"}')
COPY_RUN = ['$원장 = [self:ledger]{path: "outputs/x/_covered.json", op: "select", target: "covered"}',
            '$검색 = [sense:search_youtube]{query: "AI 데이터 분석", limit: 12} >> [table:dedup]{by: "video_id"}',
            '[self:write]{path: "outputs/x/report.md", content: "…"}']
CALL_ONLY_RUN = ['[fn:팁영상수집]{주제: "AI 데이터 분석"}']
CALL_PLUS_RUN = ['$후보 = [fn:팁영상수집]{주제: "AI 데이터 분석"}',
                 '$후보 >> [table:take]{n: 4} >> [self:write]{path: "outputs/x/report.md"}']


def _calls(codes):
    return [{"tool_name": "execute_ibl", "input": {"code": c}, "success": True} for c in codes]


def _arm(monkeypatch, alias="팁영상수집", reply=None):
    """증류·귀속의 바깥(모델·DB·트리)을 가짜로 — 게이트 판정만 본다."""
    import ibl_usage_db as mod
    import thread_context
    import hippo_tree
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    thread_context.set_phrase_recall([])
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    fake = types.ModuleType("consciousness_agent")
    calls = {"n": 0}

    def _oneshot(**kw):
        calls["n"] += 1
        return json.dumps(reply or {"intent": "x", "code": "", "topic": "보고서/유튜브 AI 팁", "phrase": []}, ensure_ascii=False)
    fake.oneshot_ai_call = _oneshot
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    monkeypatch.setattr(hippo_tree, "note_run", lambda *a, **k: {"success": True, "sentences": 0})
    monkeypatch.setattr(hippo_tree, "map_text", lambda *a, **k: "- 보고서/유튜브 AI 팁 (1)")
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "alias_of_code", lambda self, code: alias if code == RECALLED else "")
    recorded = []
    monkeypatch.setattr(mod.IBLUsageDB, "update_success_by_code",
                        lambda self, code, ok, **kw: recorded.append((code, ok)) or True)
    monkeypatch.setattr(mod.IBLUsageDB, "find_phrase_by_alias",
                        lambda self, name: {"id": 1, "ibl_code": RECALLED, "alias": name} if name == alias else None)
    monkeypatch.setattr(mod.IBLUsageDB, "add_example", lambda self, **kw: 1)
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda self, *a, **k: None)
    import ibl_usage_rag as rag
    monkeypatch.setattr(rag.IBLUsageRAG, "clear_cache", lambda self: None)
    return calls, recorded


# ── 5. 증류 게이트 ──
def test_g5_copied_high_score_recall_still_distills(monkeypatch, capsys):
    import ibl_usage_rag as rag
    calls, _ = _arm(monkeypatch)
    rag.distill_experience("유튜브 AI 팁 보고서 써줘", _calls(COPY_RUN), top_score=0.81, top_code=RECALLED)
    assert calls["n"] == 1, "베낀 주행(쌍 겹침)이 종전처럼 조용히 스킵됐다"
    assert "이름으로 부르지 않음" in capsys.readouterr().out


def test_g5_call_only_run_is_skipped_but_call_plus_new_distills(monkeypatch, capsys):
    import ibl_usage_rag as rag
    calls, _ = _arm(monkeypatch)
    assert rag.distill_experience("x", _calls(CALL_ONLY_RUN), top_score=0.81, top_code=RECALLED) is False
    assert calls["n"] == 0 and "새 문장 없음" in capsys.readouterr().out
    rag.distill_experience("x", _calls(CALL_PLUS_RUN), top_score=0.81, top_code=RECALLED)
    assert calls["n"] == 1 and "부른 뒤 더한" in capsys.readouterr().out


def test_g5_low_score_and_no_top_code_unchanged(monkeypatch):
    import ibl_usage_rag as rag
    calls, _ = _arm(monkeypatch)
    rag.distill_experience("x", _calls(COPY_RUN), top_score=0.3, top_code=RECALLED)
    assert calls["n"] == 1
    assert rag.distill_experience("x", _calls(COPY_RUN), top_score=0.81, top_code=None) is False   # 조종실 경로: 점수 게이트 그대로


# ── 4. 호출 보상 ──
def test_g4_fn_call_counts_as_recall_used(monkeypatch, capsys):
    import ibl_usage_rag as rag
    _, recorded = _arm(monkeypatch)
    # 베낀 주행: 종전 규약대로 쌍 겹침 = 사용(귀속) — 불변
    assert rag.record_recall_outcome(RECALLED, 0.9, _calls(COPY_RUN)) is True
    # 부른 주행: 쌍은 안 겹쳐도 [fn:] 호출이 곧 사용
    recorded.clear()
    assert rag.record_recall_outcome(RECALLED, 0.9, _calls(CALL_PLUS_RUN)) is True
    assert recorded and recorded[-1] == (RECALLED, True)
    assert "함수 호출" in capsys.readouterr().out


def test_g4_named_phrase_call_is_attributed_without_recall(monkeypatch, capsys):
    import ibl_usage_rag as rag
    _, recorded = _arm(monkeypatch)
    n = rag._record_phrase_recall_outcome(CALL_PLUS_RUN, True, _calls(CALL_PLUS_RUN))
    assert n == 1 and recorded == [(RECALLED, True)]
    assert "[fn:팁영상수집]" in capsys.readouterr().out
    # 실패한 주행은 실패로 귀속
    recorded.clear()
    rag._record_phrase_recall_outcome(CALL_PLUS_RUN, False, _calls(CALL_PLUS_RUN))
    assert recorded == [(RECALLED, False)]


def test_g4_distill_prompt_teaches_calls_by_name():
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("m", "1. [fn:팁영상수집]{주제: \"x\"}", "", "")
    assert "[fn:" in p and "본문으로 풀" in p


def test_helpers():
    import ibl_usage_rag as rag
    assert rag._fn_called("팁영상수집", CALL_PLUS_RUN) and not rag._fn_called("팁영상수집", COPY_RUN)
    assert rag._fn_called("팁영상수집", ['[fn: 팁영상수집 ]{}'])
    assert rag._beyond_fn_calls(CALL_ONLY_RUN, "팁영상수집") == []
    assert len(rag._beyond_fn_calls(CALL_PLUS_RUN, "팁영상수집")) == 1


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
