"""노트북 포식 기억 — 등록 방아쇠(디바운스·출처 제외)·몸 추론 회상·소스 좁히기 회귀 시험 (2026-09-03).

전부 tmp_path 안(노트북 DB·문서 폴더·forage DB)만 만진다 — 실 저장소·모델 무접촉.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


@pytest.fixture
def nb(tmp_path, monkeypatch):
    pkg = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools" / "notebook"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import notebook_core as core
    import handler as H
    monkeypatch.setattr(core, "NOTEBOOK_DIR", tmp_path / "nb")
    monkeypatch.setattr(core, "DB_PATH", tmp_path / "nb" / "notebooks.db")
    (tmp_path / "nb").mkdir()
    monkeypatch.setattr(core, "semantic_available", lambda: False)   # FTS 만 — 모델 무접촉
    return core, H


@pytest.fixture
def forage(tmp_path, monkeypatch):
    import forage_memory as FM
    import forage_doc as FD
    monkeypatch.setattr(FM, "_DB_PATH", str(tmp_path / "forage.db"))
    monkeypatch.setattr(FD, "DOC_DIR", str(tmp_path / "docs"))
    monkeypatch.setattr(FD, "reconcile_lazy", lambda *a, **k: None)
    return FM, FD


class _Ctx:
    def __init__(self, origin=""):
        self.origin = origin
        self.project_path = ""
        self.agent_id = "agent_t"


def test_registration_triggers_survey_once_per_window(nb, monkeypatch):
    core, H = nb
    import routing_system
    calls = []
    monkeypatch.setattr(routing_system, "_delegate_unified",
                        lambda params, project_path: (calls.append(params) or {"success": True, "queued": True}))
    out = json.loads(H._op_create({"name": "독서", "note": "책 3권"}, _Ctx()))
    assert out["success"] and out["memory_survey"]["queued"] is True
    assert len(calls) == 1 and calls[0]["scope"] == "system" and "notebook:독서" in calls[0]["message"]
    out2 = json.loads(H._op_add({"name": "독서", "text": "본문 " * 50, "title": "서론"}, _Ctx()))
    assert out2["success"] and out2["memory_survey"]["queued"] is False and out2["memory_survey"]["reason"] == "debounced"
    assert len(calls) == 1
    # 시험·훈련 출처는 위임하지 않는다
    r = H._schedule_survey("독서2", _Ctx(origin="test"), "x")
    assert r["queued"] is False and "test" in r["reason"] and len(calls) == 1


def test_ask_reads_notebook_memory_doc_as_map(nb, forage, monkeypatch):
    core, H = nb
    FM, FD = forage
    FM.note_map(body="notebook:독서", locus="notebook:독서", kind="identity", claim="세 권의 서평 모음", confidence=0.9, territory=True)
    p = FD.doc_path_at("notebook:독서", "notebook:독서")
    assert os.path.exists(p)
    open(p, "a", encoding="utf-8").write("\n## 소스\n- 서론.pdf = 1장 요약\n")
    text = H._notebook_memory_text("독서")
    assert "세 권의 서평 모음" in text and "서론.pdf = 1장 요약" in text
    assert H._notebook_memory_text("없는노트북") == ""
    # 회상은 몸을 안 줘도 접두로 몸을 찾는다
    chain = FD._covering_docs("notebook:독서/서론.pdf", None)
    assert chain == [p]


def test_search_source_filter(nb):
    core, H = nb
    core.create_notebook("계약", "두 계약서")
    core.add_source("계약", text="위약금 조항: 갑은 계약금의 두 배를 낸다. " * 5, title="A사 계약서")
    core.add_source("계약", text="위약금 조항: 을은 언제든 해지할 수 있다. " * 5, title="B사 계약서")
    for _ in range(50):
        src = core.list_sources("계약")["sources"]
        if all(s.get("chunk_count", 0) > 0 for s in src):
            break
        time.sleep(0.1)
    all_hits = core.search_chunks("계약", "위약금", top_k=8)
    assert {r["source"] for r in all_hits["results"]} == {"A사 계약서", "B사 계약서"}
    only_b = core.search_chunks("계약", "위약금", top_k=8, source="B사")
    assert only_b["results"] and {r["source"] for r in only_b["results"]} == {"B사 계약서"}
    assert only_b["source_filter"] == "B사"


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
