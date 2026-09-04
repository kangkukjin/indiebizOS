"""노트북 ask 근거 판정 회귀 (2026-09-04 실측 — 사용자 신고 "소스에 넣어도 답이 없다고만 한다").

재현: 'AI 동향' 노트북(65소스·1,879청크)에 "가장 유용한 AI 응용사례는?" → 검색은 관련 발췌 12개(0.66~0.70)를
냈는데 경량 판정기가 "발췌는 사례를 나열하지만 순위는 없다 … NOT_IN_SOURCES" 로 거절. 규칙 3이 '소스가
주제를 안 다룸'과 '확정 판단이 없음'을 한 낱말로 뭉갰고, 후처리는 표식이 어디든 있으면 통째로 버렸다.

계약:
  N1  표식이 답을 대신할 때만 '없음'(표식 + 유효 인용 0). 인용 달린 답에 표식이 섞이면 답을 살린다.
  N2  살린 답에서 표식 줄은 걷어낸다.
  N3  판정 프롬프트는 '주제를 전혀 다루지 않을 때만' 없음이라 말하고 한계 진술을 요구한다.
  N4  맨 표식인데 검색 최고점이 COVERAGE_SCORE 이상이면 검색 사실을 실어 한 번 되묻는다(점수 낮으면 안 되묻는다).

실행: .venv/bin/python -m pytest backend/test_notebook_grounding.py -q
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401
sys.path.insert(0, os.path.join(ROOT, "data", "packages", "installed", "tools", "notebook"))


def test_n1_mark_only_or_uncited_is_not_in_sources():
    import handler as H
    assert H._is_not_in_sources("NOT_IN_SOURCES", 12)
    assert H._is_not_in_sources("발췌는 사례를 나열하지만 순위는 없습니다. 따라서 답할 수 없습니다.\n\nNOT_IN_SOURCES", 12)
    assert H._is_not_in_sources("근거 [99] 로 답합니다. NOT_IN_SOURCES", 12)      # 범위 밖 인용은 무효
    assert not H._is_not_in_sources("보고서는 코사이언티스트 제도화를 꼽는다 [2]. 순위는 소스에 없다.\nNOT_IN_SOURCES", 12)
    assert not H._is_not_in_sources("보고서는 코사이언티스트 제도화를 꼽는다 [2].", 12)


def test_n2_strip_mark_keeps_answer():
    import handler as H
    out = H._strip_mark("답 [1][3].\nNOT_IN_SOURCES\n한계: 순위는 없다 [2].")
    assert "NOT_IN_SOURCES" not in out and out.startswith("답 [1][3].") and out.endswith("[2].")


def test_n3_prompt_contract():
    import inspect
    import handler as H
    src = inspect.getsource(H._grounded_generate)
    assert "주제를 전혀 다루지 않을 때만" in src and "한계를 밝혀라" in src


def test_n4_reask_only_when_search_covered_the_topic():
    import handler as H
    hi = [{"score": 0.70, "text": "x"}, {"score": 0.66, "text": "y"}]
    lo = [{"score": 0.31, "text": "x"}]
    assert H._should_reask("NOT_IN_SOURCES", hi)
    assert not H._should_reask("NOT_IN_SOURCES", lo)
    assert not H._should_reask("답 [1].", hi)                       # 답이 있으면 되묻지 않는다
    assert H._top_score([]) == 0.0 and not H._should_reask("NOT_IN_SOURCES", [])


# ---------------------------------------------------------------- N5·N6 전체 소개(digest)
def test_n5_windows_keep_order_and_do_not_split_chunks():
    import handler as H
    chunks = [{"id": i, "loc": f"[{i}:00]", "text": "x" * 1200} for i in range(10)]
    wins = H._windows(chunks, limit=5000)
    assert [len(w) for w in wins] == [4, 4, 2] and wins[0][0]["id"] == 0 and wins[-1][-1]["id"] == 9


def test_n6_ask_hands_overview_to_digest(monkeypatch):
    import types
    import handler as H
    import notebook_core as core
    monkeypatch.setattr(core, "search_chunks", lambda name, q, top_k=8, source=None: {
        "success": True, "notebook": name, "note": "", "search_type": "hybrid",
        "results": [{"id": 1, "loc": "[0:00]", "text": "t", "source": "s", "source_id": 7, "score": 0.7}]})
    monkeypatch.setattr(H, "_notebook_memory_text", lambda name: "")
    monkeypatch.setattr(H, "_resolve_source", lambda core_, name, source=None: {"success": True, "source": {"id": 7, "title": "강의", "kind": "youtube"}})
    monkeypatch.setattr(H, "_source_chunks", lambda core_, sid: [{"id": i, "loc": f"[{i}:00]", "text": "본문 " * 300} for i in range(6)])
    calls = []
    def fake_oneshot(prompt, system_prompt="", role="classify"):
        calls.append(role)
        if "DIGEST" in system_prompt or "근거 고정(grounded) 조수" in system_prompt:
            return "DIGEST_NEEDED"
        return "요지" if role == "classify" else "소개문 [구간 1][구간 2]"
    fake = types.ModuleType("consciousness_agent"); fake.oneshot_ai_call = fake_oneshot
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    import json
    out = json.loads(H._op_ask({"name": "nb", "query": "이 강의의 내용을 한국어로 자세히 소개해줘"}, None))
    assert out["success"] and out.get("mode") == "digest" and out["answer"].startswith("소개문")
    assert out["windows"] >= 1 and len(out["items"]) == out["windows"] and calls[-1] == "evaluate"


# ---------------------------------------------------------------- N7·N8 소스 카드·지도
def test_n7_card_written_and_map_reads_gist(monkeypatch, tmp_path):
    import types, json
    import handler as H
    import notebook_core as core
    monkeypatch.setattr(core, "NOTEBOOK_DIR", tmp_path)
    src = {"id": 7, "title": "강의", "kind": "youtube", "status": "ready", "char_count": 1200}
    monkeypatch.setattr(H, "_source_chunks", lambda core_, sid: [{"id": 1, "loc": "[0:00]", "text": "본문 " * 100}, {"id": 2, "loc": "[1:00]", "text": "본문 " * 100}])
    fake = types.ModuleType("consciousness_agent")
    fake.oneshot_ai_call = lambda prompt, system_prompt="", role="classify": "> 트랜스포머 강의의 한 줄 요약\n\n## 무엇인가\n강의다.\n\n## 구조\n- [0:00] 서론\n\n## 핵심 주장·수치·이름\n- 어텐션\n\n## 답할 수 있는 물음\n- 트랜스포머란?"
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    r = H._write_card(core, "nb", src)
    assert r["success"] and r["gist"] == "트랜스포머 강의의 한 줄 요약" and r["via"] == "direct"
    p = H._card_path(core, "nb", 7); text = open(p, encoding="utf-8").read()
    assert text.startswith('<!-- notebook-card notebook="nb" source_id="7"') and "## 답할 수 있는 물음" in text
    assert H._write_card(core, "nb", src).get("skipped") == "exists"          # 있으면 다시 안 쓴다
    # 사람이 카드의 한 줄을 고치면 지도가 따라온다
    open(p, "w", encoding="utf-8").write(text.replace("> 트랜스포머 강의의 한 줄 요약", "> 사람이 고친 요약"))
    monkeypatch.setattr(core, "list_sources", lambda name: {"success": True, "notebook": name, "note": "", "sources": [src, {**src, "id": 8, "title": "카드 없음"}]})
    m = json.loads(H._op_map({"name": "nb"}, None))
    assert m["success"] and m["count"] == 2 and m["missing_cards"] == 1
    assert "#7 강의 (youtube · 1,200자) — 사람이 고친 요약" in m["text"] and "(카드 없음 — op:card)" in m["text"]


def test_n8_big_source_goes_through_gists(monkeypatch, tmp_path):
    import types
    import handler as H
    import notebook_core as core
    monkeypatch.setattr(core, "NOTEBOOK_DIR", tmp_path)
    monkeypatch.setattr(H, "CARD_DIRECT_MAX", 500)
    monkeypatch.setattr(H, "_source_chunks", lambda core_, sid: [{"id": i, "loc": f"[{i}:00]", "text": "x" * 400} for i in range(4)])
    calls = []
    fake = types.ModuleType("consciousness_agent")
    fake.oneshot_ai_call = lambda prompt, system_prompt="", role="classify": (calls.append(system_prompt) or ("> 큰 문서 요약\n\n## 무엇인가\n." if "카드" in system_prompt else "요지"))
    monkeypatch.setitem(sys.modules, "consciousness_agent", fake)
    r = H._write_card(core, "nb", {"id": 9, "title": "big", "kind": "file", "status": "ready"})
    assert r["success"] and r["via"] == "gists" and r["gist"] == "큰 문서 요약"
    assert sum(c.startswith("너는 문서 구간") for c in calls) >= 1 and calls[-1].startswith("너는 문서 카드")


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
