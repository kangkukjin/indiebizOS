"""심층 기억 주제 트리(memory_tree) — 문서 정본·색인 동기화·지도·배치 회귀 시험 (2026-09-03).

전부 tmp_path 안의 DB/트리만 만진다(임베딩 모델 무접촉).
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


@pytest.fixture
def mem(tmp_path, monkeypatch):
    pkg = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools" / "memory"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import memory_db as db
    import memory_tree as tree
    monkeypatch.setattr(db, "_index_one", lambda *a, **k: None)
    monkeypatch.setattr(db, "_delete_vec", lambda *a, **k: None)
    project = tmp_path / "proj"; project.mkdir()
    db_path = str(project / "memory_t.db")
    return db, tree, str(project), "agent_t", db_path


def _read(p):
    return open(p, encoding="utf-8").read()


def test_save_with_node_renders_branch_doc_and_map(mem):
    db, tree, project, agent, db_path = mem
    mid = db.save(project, agent, "어머니는 1940년생이다", "어머니", "사용자정보", node="가족/어머니")
    db.save(project, agent, "딸은 조개를 안 좋아한다", "딸", "사용자정보", node="가족")
    doc = tree.doc_path(db_path, "가족/어머니")
    assert os.path.exists(doc)
    text = _read(doc)
    assert 'node="가족/어머니"' in text and f"‹#{mid}" in text and "1940년생" in text
    assert "조개" not in text                       # 부모 가지의 행은 부모 문서에
    m = tree.map_text(db_path)
    assert "- 가족 (1)" in m and "- 가족/어머니 (1)" in m
    assert "1940년생" not in m                      # 지도는 내용을 싣지 않는다


def test_doc_edit_syncs_back_update_delete_insert(mem):
    db, tree, project, agent, db_path = mem
    a = db.save(project, agent, "옛 사실", "", "사용자정보", node="집")
    b = db.save(project, agent, "지울 사실", "", "작업기록", node="집")
    doc = tree.doc_path(db_path, "집")
    text = _read(doc)
    text = text.replace("옛 사실", "고친 사실")
    text = "\n".join(l for l in text.splitlines() if f"‹#{b}" not in l) + "\n"
    text = text.replace(tree.SECTION_NOTE, tree.SECTION_NOTE + "\n- [사용자선호] 문서에서 직접 적은 새 기억")
    open(doc, "w", encoding="utf-8").write(text)
    os.utime(doc, (os.path.getmtime(doc) + 5, os.path.getmtime(doc) + 5))   # 렌더 도장보다 새롭게
    out = tree.sync_node(db_path, "집")
    assert out["synced"] and out["updated"] == 1 and out["deleted"] == 1 and out["inserted"] == 1
    rows = {r["id"]: r for r in tree.rows_of(db_path, "집")}
    assert rows[a]["content"] == "고친 사실" and b not in rows
    assert any(r["content"] == "문서에서 직접 적은 새 기억" and r["category"] == "사용자선호" for r in rows.values())
    assert "#" in _read(doc).split("문서에서 직접 적은 새 기억")[1][:12]   # 재렌더로 새 줄에 #id 부여
    assert tree.sync_node(db_path, "집")["synced"] is False              # 도장 갱신 → 두 번 돌지 않음


def test_recall_opens_branch_with_children_and_move(mem):
    db, tree, project, agent, db_path = mem
    x = db.save(project, agent, "테슬라 모델 Y 보유", "", "사용자정보", node="물건/차량")
    db.save(project, agent, "갤럭시 A36", "", "사용자정보", node="물건/기기")
    out = tree.recall(db_path, "물건")
    assert out["success"] and out["count"] == 0
    assert sorted(c["node"] for c in out["children"]) == ["물건/기기", "물건/차량"]
    assert tree.recall(db_path, "없는가지")["success"] is False
    mv = tree.move(db_path, x, "물건/기기")
    assert mv["success"] and mv["from"] == "물건/차량"
    assert "모델 Y" in _read(tree.doc_path(db_path, "물건/기기"))
    assert "모델 Y" not in _read(tree.doc_path(db_path, "물건/차량"))


def test_update_node_moves_between_docs_and_delete_refreshes(mem):
    db, tree, project, agent, db_path = mem
    mid = db.save(project, agent, "바흐를 즐긴다", "", "사용자선호", node="취향/음악")
    db.update(project, agent, mid, node="취향")
    assert "바흐" in _read(tree.doc_path(db_path, "취향")) and "바흐" not in _read(tree.doc_path(db_path, "취향/음악"))
    db.delete(project, agent, mid)
    assert "바흐" not in _read(tree.doc_path(db_path, "취향"))


def test_file_unfiled_asks_model_and_places_rows(mem):
    db, tree, project, agent, db_path = mem
    db.save(project, agent, "기존 가지의 기억", "", "사용자정보", node="가족")
    u1 = db.save(project, agent, "어머니 정수기 모델은 X", "", "사용자정보")
    u2 = db.save(project, agent, "판단 불가 조각", "", "기타")
    assert {r["id"] for r in tree.unfiled(db_path)} == {u1, u2}
    seen = {}

    def fake_ai(prompt, system_prompt):
        seen["prompt"] = prompt
        return json.dumps({str(u1): "가족/어머니", str(u2): ""})
    out = tree.file_unfiled(db_path, fake_ai)
    assert "- 가족 (1)" in seen["prompt"] and str(u1) in seen["prompt"]
    assert out["filed"] == 1 and out["skipped"] == 1 and out["new_nodes"] == ["가족/어머니"]
    assert "정수기" in _read(tree.doc_path(db_path, "가족/어머니"))
    assert [r["id"] for r in tree.unfiled(db_path)] == [u2]


def test_norm_node_and_gist(mem, tmp_path):
    db, tree, project, agent, db_path = mem
    assert tree.norm_node(" 가족 / 어머니 /") == "가족/어머니"
    assert tree.norm_node("../a/b/c/d/e") == "a/b/c/d"
    db.save(project, agent, "x", "", "기타", node="주제")
    p = tree.doc_path(db_path, "주제")
    assert tree.gist_of(p) == ""                    # 자리표는 요약이 아니다
    text = _read(p).replace(tree.GIST_PLACEHOLDER, "이 가지의 한 줄 요약")
    open(p, "w", encoding="utf-8").write(text)
    assert tree.gist_of(p) == "이 가지의 한 줄 요약"
    assert "— 이 가지의 한 줄 요약" in tree.map_text(db_path)


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
