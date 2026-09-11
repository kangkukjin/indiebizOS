"""Reproduce drift at memory, approval, counts, execution reuse and IO boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from memory_evidence import source_units, grounded_fact
from supervision_store import TurnStore
from supervisor_content import discover, validate, reconcile
from test_conscious_supervisor import supervisor, verdict, finish, manager_tool  # noqa: F401


def test_memory_retains_tail_and_never_stores_generated_claim():
    tail = "한은은 저가 모델 확산이 가격 하방압력을 높인다고 전망했다."
    units = source_units("보고서를 작성해줘", "앞부분 " * 200 + "\n\n" + tail)
    fact = grounded_fact({"source_ids": [3], "content": "한은이 저가 모델을 발표했다",
                          "category": "의사결정"}, units, '{"utterance":"보고서 요청"}')
    assert fact["content"] == tail
    assert fact["category"] == "작업기록"
    assert json.loads(fact["source_ref"])["evidence"][0]["text"] == tail
    assert grounded_fact({"content": tail}, units, "{}") is None


@pytest.mark.parametrize("ids", [[True], [0], [4], [2, 1], [1, 1], "1"])
def test_memory_bad_source_selection_is_not_guessed(ids):
    assert grounded_fact({"source_ids": ids}, source_units("선호", "응답"), "{}") is None


def test_dedup_model_cannot_rewrite_source(monkeypatch, tmp_path):
    import sys
    from cognitive_distill import CognitiveDistillMixin
    import consciousness_agent
    old = {"id": 1, "content": "이전 작업", "keywords": "전망", "source_ref": "old"}
    stored = []
    monkeypatch.setitem(sys.modules, "memory_db", SimpleNamespace(
        _get_db_path=lambda *a: "fixture", body_noun_leak=lambda *a: None,
        search=lambda **k: [old], read=lambda *a: old,
        update=lambda *a, **kw: stored.append(kw)))
    monkeypatch.setitem(sys.modules, "memory_tree", SimpleNamespace(map_text=lambda *a: "보고서", norm_node=lambda x: x))
    replies = iter(['[{"source_ids":[2],"keywords":"전망","category":"작업기록"}]',
                    '{"verdicts":[{"action":"UPDATE","content":"한은이 모델을 발표함"}]}'])
    monkeypatch.setattr(consciousness_agent, "oneshot_ai_call", lambda **kw: next(replies))
    runner = CognitiveDistillMixin()
    runner.project_path, runner.agent_id = tmp_path, "worker"
    runner._distill_deep_memory("보고서 작성", "한은은 투자 증가율 둔화를 전망했다.")
    assert stored[0]["content"] == "이전 작업\n[보충] 한은은 투자 증가율 둔화를 전망했다."


def test_consolidation_selects_original_and_keeps_relative_time(monkeypatch):
    import consciousness_agent
    from memory_consolidation import _compact_record_llm, _merge_cluster_llm
    replies = iter(['{"source_ids":[1],"content":"2026년 9월 12일 발표"}',
                    '{"merges":[{"keep_id":1,"drop_ids":[2],"source_ids":[1],"content":"거짓"}]}'])
    monkeypatch.setattr(consciousness_agent, "oneshot_ai_call", lambda **kw: next(replies))
    source = "내일 발표한다."
    result = _compact_record_llm({"content": source + "\n[보충] " + source}, "2026-09-11")
    assert result["content"] == source
    merged = _merge_cluster_llm([{"id": 1, "content": source}, {"id": 2, "content": source}], "2026-09-11")
    assert merged[0]["content"] == source


def test_primary_distill_selects_component_before_file_tail(monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [{
        "intent": "뉴스 후보 수집", "source_ids": [2], "scope": "component",
        "code": "...url...", "topic": "시험"}])
    source = ('$x = [sense:search]{query:"AI"}\n'
              '$x >> [table:take]{n:3}\n'
              '[self:write]{path:"/tmp/report.md",content:"$file:0"}')
    assert rag.distill_experience("보고서 작성", [{"tool_name": "execute_ibl",
        "input": {"code": source}, "success": True}], 0.0)
    assert len(asked) == 1 and len(saved) == 1
    assert saved[0]["ibl_code"] == source.split('\n[self:write]')[0]
    assert saved[0]["source"] == "distilled_component" and saved[0]["alias"] == ""
    assert saved[0]["avg_tokens"] == -1


def test_counts_use_verified_unique_final_rows(tmp_path):
    store = TurnStore(tmp_path)
    rows = [{"event":"policy", "status":"NEW", "verified":True},
            {"event":"policy", "status":"NEW", "verified":True},
            {"event":"moon", "status":"NEW", "verified":False},
            {"event":"model", "status":"CHANGED", "verified":True}]
    ref = store.evidence({"items": rows})
    calc = {"id":ref["id"], "where":{"status":"NEW", "verified":True},
            "identity":["event"], "expected":1}
    assert not reconcile(store, [calc])  # Unread evidence is not approval.
    store.read_evidence(ref["id"], mark=True)
    assert reconcile(store, [calc])
    assert not reconcile(store, [{**calc, "expected":3}])
    assert not reconcile(store, [{**calc, "identity":["unknown"]}])


def test_coverage_only_approval_cannot_pass_content(supervisor, tmp_path):
    path = tmp_path / "report.md"
    path.write_text("투자 증가율은 둔화할 전망이다.")
    supervisor.store.put_response(f"보고서: {path}")
    supervisor.content_artifacts = discover(supervisor, supervisor.store.text, [])
    assert validate(supervisor, {"status":"APPROVED", "checks":[{"path":str(path),"coverage":"읽음"}]})


def test_content_approval_binds_read_sources_and_current_bytes(supervisor, tmp_path):
    path = tmp_path / "report.md"
    path.write_text("투자 증가율은 둔화할 전망이다.")
    supervisor.store.put_response(f"보고서: {path}")
    supervisor.content_artifacts = discover(supervisor, supervisor.store.text, [])
    art = supervisor.content_artifacts[0]
    source = supervisor.store.evidence("원문: 투자 증가율 79%, 38%, 16% 전망")
    record = {"path":str(path),"hash":art["hash"],
        "meaning":{"status":"passed","reason":"수준 아닌 증가율임을 보존", "evidence":[{"id":art["hash"],"quote":"투자 증가율"}]},
        "sources":{"status":"passed","reason":"원문 대조", "evidence":[{"id":source["id"],"quote":"증가율 79%, 38%, 16% 전망"}]},
        "counts":{"status":"not_applicable","reason":"항목 계수 없음"}}
    decision = {"status":"APPROVED", "content_checks":[record]}
    assert validate(supervisor, decision)
    supervisor.store.read_evidence(art["hash"], mark=True)
    supervisor.store.read_evidence(source["id"], mark=True)
    assert validate(supervisor, decision) is None
    record["sources"]["evidence"][0]["quote"] = "투자가 감소한다"
    assert validate(supervisor, decision)
    path.write_text("투자가 감소한다.")
    assert "바뀌었" in validate(supervisor, decision)


def test_auto_each_preserves_mutation_order_and_explicit_preferences(monkeypatch):
    from ibl_exec_each import _each_parallel
    monkeypatch.setattr("ibl_safety.load_safety_map", lambda: {
        ("sense","crawl"): True, ("table","brief"): True, ("self","write"):False})
    code = "[sense:crawl] >> [table:brief]"
    assert _each_parallel({"do":code}) == 4
    assert _each_parallel({"do":code,"parallel":1}) == 1
    assert _each_parallel({"do":code,"on_error":"stop"}) == 1
    assert _each_parallel({"do":code+" >> [self:write]"}) == 1
    assert _each_parallel({"do":"[fn:unknown]"}) == 1


def test_transformed_rows_cannot_inherit_old_criteria_and_counters():
    from common.pkg_utils import load_sibling
    path = Path(__file__).resolve().parents[1]/"data/packages/installed/tools/data-ops/handler.py"
    module = load_sibling(str(path), "envelope_scope")
    out = {"criteria_verdict":"pass", "rows_out":53}
    module.invalidate_derived_checks(out, [[{"status":"NEW"}]], [{"status":"UNVERIFIED"}])
    assert "criteria_verdict" not in out and "rows_out" not in out
    assert out["_upstream_check"]["checks"]["criteria_verdict"] == "pass"


def test_write_receipt_counts_utf8_bytes(tmp_path):
    from common.pkg_utils import load_sibling
    path = Path(__file__).resolve().parents[1]/"data/packages/installed/tools/system_essentials/handler.py"
    module = load_sibling(str(path), "sink_ops")
    target = tmp_path/"report.md"
    text = "한글 🙂\n"
    receipt = json.loads(module.write_sink({"content":text}, str(target), str(target), False,
        _red_write_prepare=lambda *a:None, _red_write_finalize=lambda *a:None, _vocab_enforce=lambda *a:None))
    assert receipt["size"] == target.stat().st_size == len(text.encode())
    assert receipt["chars"] == len(text)


def test_merge_and_update_keep_evidence_and_reject_stale_snapshot(monkeypatch, tmp_path):
    import sqlite3
    from common.pkg_utils import load_sibling
    handler = Path(__file__).resolve().parents[1]/"data/packages/installed/tools/memory/handler.py"
    module = load_sibling(str(handler), "memory_db")
    path = tmp_path/"memory.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memories(id INTEGER PRIMARY KEY,content TEXT, keywords TEXT, category TEXT, created_at TEXT, source_ref TEXT, node TEXT, used_at TEXT)")
    conn.executemany("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)", [
        (1,"원문 A","k","작업기록","2026-01-01",'source A',"주제",None),
        (2,"원문 B","k","작업기록","2026-01-02",'source B',"주제",None)])
    conn.commit()
    for name in ("_index_one", "_delete_vec", "_tree_refresh_all", "_tree_refresh"):
        monkeypatch.setattr(module, name, lambda *a:None)
    monkeypatch.setattr(module, "_get_db_path", lambda *a:str(path))
    monkeypatch.setattr(module, "get_db", lambda *a:sqlite3.connect(path))
    assert not module.apply_merge(str(path),1,"원문 A","k","작업기록",[2],expected_contents={1:"옛 원문",2:"원문 B"})
    assert not module.update("p","a",1,content="새 원문",expected_content="옛 원문")
    assert conn.execute("SELECT count(*) FROM memories").fetchone()[0] == 2
    assert module.apply_merge(str(path),1,"원문 A\n원문 B","k","작업기록",[2],expected_contents={1:"원문 A",2:"원문 B"})
    ref = json.loads(conn.execute("SELECT source_ref FROM memories").fetchone()[0])
    assert [r["source_ref"] for r in ref["merged_sources"]] == ["source A","source B"]
    assert conn.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    conn.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
