"""수리 주행 6건 검토 수리 (2026-09-05): 증류 중복 저장 관문 · 작명 규칙 · 수리 턴 조각의 손과 기억.

  D1  same_program — 슬롯·값을 비운 서명 열이 같으면 같은 프로그램(관용구 `수리제안적용하기` vs 낱말 `…2` 부류). 문장 수·머리·키가 다르면 다르다.
  D2  distill_experience — 관용구가 저장됐고 대표 code 가 같은 프로그램이면 낱말 add_example 을 부르지 않는다(이름 하나).
  N1  증류 프롬프트가 이름을 "사건이 아니라 모양"으로 짓게 한다(좋은 예·나쁜 예 동반).
  R1  13_repair.md 가 개발 가지 recall·`[fn:]`·등록 스크립트 검증·경로 file_find 를 말한다.
임시 DB·임시 트리만(실 저장소 무접촉). 실행: .venv/bin/python -m pytest backend/test_distill_dedup_naming_2026_09_05.py -q
"""
import json
import os
import sys
import tempfile
import types

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

STATUS = '[self:patch]{op: "status"}'
APPLY = '[self:patch]{op: "apply", proposal_id: "p_20260905_162707"}'


# ---------------------------------------------------------------- D1
def test_d1_same_program_by_blank_signature():
    from ibl_idiom import same_program
    code = STATUS + "\n" + APPLY
    assert same_program(code, [STATUS, '[self:patch]{op: "apply", proposal_id: "$제안번호"}'])
    assert same_program(STATUS + "; " + APPLY, [STATUS, '[self:patch]{op: "apply", proposal_id: "${제안}"}'])
    assert not same_program(code, [STATUS])                                          # 문장 수 다름
    assert not same_program(code, [STATUS, '[self:patch]{op: "discard", proposal_id: "$p"}'])   # op 다름
    assert not same_program("", [STATUS])


# ---------------------------------------------------------------- D2
def test_d2_distill_skips_word_when_same_as_saved_phrase(monkeypatch, tmp_path):
    import ibl_usage_db as mod
    import thread_context
    import hippo_tree
    import ibl_usage_rag as rag
    import ibl_param_vocab
    monkeypatch.setattr(thread_context, "get_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(thread_context, "clear_goal_eval_outcome", lambda: None)
    monkeypatch.setattr(mod.IBLUsageDB, "hippo_disabled", classmethod(lambda cls: False))
    monkeypatch.setattr(hippo_tree, "DOC_DIR", str(tmp_path / "tree"))
    os.makedirs(tmp_path / "tree" / "몸 자기점검·수리")
    (tmp_path / "tree" / "몸 자기점검·수리" / hippo_tree.DOC_NAME).write_text("# x\n", encoding="utf-8")
    code = STATUS + "\n" + APPLY
    reply = {"intent": "제안된 수리안을 적용한다", "code": code, "code_name": "수리제안적용하기", "topic": "몸 자기점검·수리",
             "phrase": [STATUS, '[self:patch]{op: "apply", proposal_id: "${제안번호}"}'], "slots": {"제안번호": "p_20260905_162707"},
             "phrase_name": "수리제안적용하기"}
    fake = types.ModuleType("consciousness_agent")
    fake.oneshot_ai_call = lambda **kw: json.dumps(reply, ensure_ascii=False)
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    monkeypatch.setattr(hippo_tree, "map_text", lambda *a, **k: "- 몸 자기점검·수리 (3)")
    saved = []
    monkeypatch.setattr(mod.IBLUsageDB, "_instance", None)
    monkeypatch.setattr(mod.IBLUsageDB, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "add_example", lambda self, **kw: saved.append(kw) or len(saved))
    monkeypatch.setattr(mod.IBLUsageDB, "_index_single", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.IBLUsageDB, "find_phrase_by_alias", lambda self, n: None)
    monkeypatch.setattr(rag, "_validate_ibl_actions", lambda code: True)
    monkeypatch.setattr(ibl_param_vocab, "check_code_params", lambda code: [])
    import pathlib
    real = pathlib.Path.write_text
    monkeypatch.setattr(pathlib.Path, "write_text", lambda self, *a, **k: None if self.name == "ibl_distilled.json" else real(self, *a, **k))
    calls = [{"tool_name": "execute_ibl", "input": {"code": STATUS}, "success": True},
             {"tool_name": "execute_ibl", "input": {"code": APPLY}, "success": True}]
    assert rag.distill_experience("#repair 적용해줘", calls, top_score=0.3) is True
    cats = [s.get("category") for s in saved]
    assert cats == ["phrase"], cats                    # 관용구 하나만 — 같은 프로그램의 낱말(…2)은 저장하지 않는다
    assert saved[0]["alias"] == "수리제안적용하기"


# ---------------------------------------------------------------- N1 · R1
def test_n1_prompt_names_shapes_not_incidents():
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("u", "  1. " + STATUS, "", "")
    assert "이번 사건이 아니라 되풀이될 모양" in p and "12자" in p


def test_r1_repair_fragment_routes_to_recall_scripts_and_find():
    frag = open(os.path.join(os.path.dirname(BACKEND), "data", "common_prompts", "fragments", "13_repair.md"), encoding="utf-8").read()
    assert 'store: "실행"' in frag and "[fn:이름]" in frag
    assert '[self:script]{op: "list"}' in frag and "pytest" in frag
    assert "[self:file_find]" in frag


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
