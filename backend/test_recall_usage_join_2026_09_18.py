"""제시→사용 결합(2026-09-18, 공통 흐름 2단계 ①) — 형식은 공통(recall.used 사건), 해석은 기억별.

무엇을 고정하나:
  ① 공급원마다 제시 id 와 결합 키(join)가 payload 로 나오고, 사건에는 id·건수만 실린다(4KB 절단에 안전).
  ② 해마: 제시 용례의 [node:action] 쌍이 실행에 등장해야 '사용'(record_recall_outcome 과 같은 규칙), 관용구는 [fn:이름].
  ③ 세계 지도(두 채널): 이름·별칭이 응답이나 코드에 나타나면 'mentioned' — 약한 증거로 종류가 남는다.
  ④ 심층: 명시 조회(node 아래·expand #id)=expanded, 증류가 used_at 을 올림=confirmed. 자동 회상은 사용이 아니다.
  ⑤ 점수·성공률은 여기서 고치지 않는다 — 사용 해석기는 DB 를 쓰지 않는다.
"""
import json
import sqlite3

import pytest
import boot_paths  # noqa: F401

import associative_recall as AR


def _tc(code, ok=True):
    return {"tool_name": "execute_ibl", "input": {"code": code}, "success": ok}


def test_hippocampus_usage_is_executed_pairs_or_fn_call():
    join = {"items": [
        {"id": "1", "code": '[sense:price]{query: "x"}', "kind": "word", "alias": ""},
        {"id": "2", "code": '[self:read]{path: "a"} >> [table:take]{n: 3}', "kind": "word", "alias": ""},
        {"id": "3", "code": '[self:blog]{op: "posts"}', "kind": "phrase", "alias": "블로그정리"},
    ]}
    ev = {"ibl_codes": ['[sense:price]{query: "y"}', '[fn:블로그정리]{}'], "response": "", "deep_touched": []}
    r = AR._used_hippocampus(["1", "2", "3"], join, ev)
    assert r["used"] == ["1", "3"] and r["evidence"] == "executed" and r["ibl_calls"] == 2
    assert AR._used_hippocampus(["1"], join, {"ibl_codes": [], "response": "x"})["used"] == []


def test_world_names_usage_is_mention_in_response_or_code():
    join = {"names": {"ortools": ["OR-Tools", "제약 프로그래밍"], "blender": ["Blender"], "x": ["a"]}}
    ev = {"ibl_codes": ['[self:script]{op: "run", id: "blender_render"}'], "response": "제약 프로그래밍으로 짜겠습니다.", "deep_touched": []}
    r = AR._used_names(["ortools", "blender", "x"], join, ev)
    assert r["used"] == ["ortools", "blender"] and r["evidence"] == "mentioned"   # 한 글자 별칭 'a' 는 증거가 아니다


def test_deep_usage_expanded_by_recall_op_or_confirmed_by_distill():
    join = {"paths": {"7": "여행/속초", "8": "가족/어머니", "9": "블로그"}, "db": ""}
    ev = {"ibl_codes": ['[self:memory]{op: "recall", node: "여행"}', '[self:memory]{op: "recall", store: "실행", node: "블로그"}'],
          "response": "", "deep_touched": ["8"]}
    r = AR._used_deep(["7", "8", "9"], join, ev)
    assert r["used"] == ["7", "8"] and r["evidence"] == "confirmed+expanded" and r["opened"] == ["여행"]
    r2 = AR._used_deep(["9"], join, {"ibl_codes": ['[self:memory]{op: "recall", expand: "#9"}'], "deep_touched": []})
    assert r2["used"] == ["9"] and r2["evidence"] == "expanded"
    assert AR._used_deep(["9"], join, {"ibl_codes": [], "deep_touched": []})["used"] == []


def test_record_usage_emits_one_event_and_touches_no_store(monkeypatch):
    events = []
    import episode_logger
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda kind, data=None: events.append((kind, data)))
    presented = [
        {"source": "hippocampus", "ids": ["1"], "join": {"items": [{"id": "1", "code": "[sense:price]{}", "kind": "word", "alias": ""}]}},
        {"source": "world_memory", "ids": ["ortools"], "join": {"names": {"ortools": ["OR-Tools"]}}},
        {"source": "guide_map", "ids": ["x"], "join": {}},          # 해석기 없는 공급원은 사건에 실리지 않는다
    ]
    out = AR.record_usage(presented, tool_calls=[_tc("[sense:price]{}")], response="OR-Tools 로 풉니다")
    assert [o["source"] for o in out] == ["hippocampus", "world_memory"]
    assert out[0]["used"] == ["1"] and out[1]["used"] == ["ortools"]
    assert events and events[-1][0] == "recall.used" and len(json.dumps(events[-1][1], ensure_ascii=False)) < 4096
    assert AR.record_usage([], tool_calls=[], response="x") == []


def test_usage_payload_carries_join_but_event_carries_ids_only():
    r = AR.Recall(AR.RecallRequest(None, "m", [], "pipeline"))
    r.blocks.append(AR.Block("hippocampus", "execution_memory", "<x/>", ids=["1", "2"],
                             join={"items": [{"id": "1", "code": "c"}]}))
    r.blocks.append(AR.Block("guide_map", "guide_map", "<g/>"))
    r.routed = True
    payload = r.usage_payload()
    assert payload == [{"source": "hippocampus", "ids": ["1", "2"], "join": {"items": [{"id": "1", "code": "c"}]}}]
    assert all("join" not in p for p in r.presented())


def test_deep_used_at_snapshot(tmp_path):
    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, used_at TEXT)")
    conn.executemany("INSERT INTO memories VALUES (?, ?)", [(1, None), (2, "2026-09-18T10:00:00")])
    conn.commit(); conn.close()
    assert AR.deep_used_at(str(db), ["1", "2"]) == {"1": None, "2": "2026-09-18T10:00:00"}
    assert AR.deep_used_at("", ["1"]) == {} and AR.deep_used_at(str(db), []) == {}


def test_hippocampus_detail_presents_selected_examples(monkeypatch):
    """상세 판은 XML 에 실린 용례와 같은 목록을 제시로 돌려주고, 튜플 판은 종전 계약 그대로다."""
    import ibl_usage_rag as rag
    from types import SimpleNamespace
    ex = [SimpleNamespace(id=11, intent="가격", ibl_code='[sense:price]{query: "x"}', score=0.9, success_rate=-1.0,
                          avg_ms=-1.0, avg_tokens=-1.0, topic="", source="", alias="")]
    monkeypatch.setattr(rag, "_search_active", lambda db, **kw: ex)
    monkeypatch.setattr(rag, "_own_only", lambda r: r)
    monkeypatch.setattr(rag, "_principal_allows_recall", lambda: True)
    monkeypatch.setattr(rag.IBLUsageRAG, "_is_ibl_relevant", lambda self, q: True)
    monkeypatch.setattr(rag.IBLUsageRAG, "search_phrases", lambda self, q, a=None: [])
    monkeypatch.setattr(rag, "_extract_implementations_from_refs", lambda xml: "")
    monkeypatch.setattr("hippo_tree.reference_needs_expansion", lambda body: False)
    d = rag.build_execution_memory_detail("가격 알려줘", None)
    assert d["presented"] == [{"id": "11", "code": '[sense:price]{query: "x"}', "kind": "word", "alias": ""}]
    assert d["top_code"] == '[sense:price]{query: "x"}' and "<execution_memory" in d["xml"]
    assert rag.build_execution_memory("가격 알려줘", None) == (d["xml"], d["top_score"], d["top_code"])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
