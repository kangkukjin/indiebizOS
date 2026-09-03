"""실행기억 주제 트리(hippo_tree) — 문서 정본·색인 동기화·지도·배치 회귀 시험 (2026-09-03).

임시 DB(같은 스키마)와 임시 문서 폴더만 만진다 — 실 해마·임베딩 무접촉.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _mk_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ibl_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, intent TEXT NOT NULL, ibl_code TEXT NOT NULL,
            nodes TEXT DEFAULT '', category TEXT DEFAULT 'single', difficulty INTEGER DEFAULT 1,
            source TEXT DEFAULT 'synthetic', success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            avg_ms REAL DEFAULT -1.0, avg_tokens REAL DEFAULT -1.0, tags TEXT DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    """)
    conn.commit(); conn.close()


def _add(db, intent, code, topic="", ok=0):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db)
    try:
        conn.execute("SELECT topic FROM ibl_examples LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE ibl_examples ADD COLUMN topic TEXT DEFAULT ''")
    cur = conn.execute("INSERT INTO ibl_examples (intent, ibl_code, success_count, created_at, updated_at, topic) VALUES (?,?,?,?,?,?)",
                       (intent, code, ok, now, now, topic))
    conn.commit(); conn.close()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path, monkeypatch):
    import hippo_tree as HT
    db = str(tmp_path / "usage.db"); _mk_db(db)
    monkeypatch.setattr(HT, "DOC_DIR", str(tmp_path / "tree"))
    monkeypatch.setattr(HT, "GUIDE_DB_PATH", str(tmp_path / "guide_db.json"))   # 기본=씨앗 없음
    monkeypatch.setattr(HT, "_default_db_path", lambda: db)
    return HT, db


def test_guide_seed_from_guide_db_when_doc_has_no_line(env, tmp_path):
    """씨앗(2026-09-03): 가지 문서는 몸-사적이라 빈 몸의 지도에 가이드가 없다 — guide_db.json 의
    topic 이 껍데기·지도·회상의 guide 를 채우고, 문서의 guide: 줄이 있으면 그것이 이긴다."""
    HT, db = env
    (tmp_path / "guide_db.json").write_text(json.dumps({"guides": [
        {"id": "a", "name": "A", "file": "a.md", "topic": "부동산"},
        {"id": "b", "name": "B", "file": "b.md", "topic": "부동산"},
        {"id": "c", "name": "C", "file": "c.md", "topic": "표 다루기"},
    ]}, ensure_ascii=False))
    _add(db, "실거래가 조회", '[sense:realty]{source: "molit"}', "부동산", ok=1)
    _add(db, "가격순 정렬", '[table:sort]{by: "price"}', "표 다루기")
    HT.refresh_all(db)
    assert HT.guide_of(HT.doc_path("부동산")) == "a.md, b.md", "껍데기 guide: 줄 = 씨앗"
    assert "부동산 (1)" in HT.map_text(db) and "guide: a.md, b.md" in HT.map_text(db)
    # 문서의 guide: 줄이 정본 — 사람이 고치면 씨앗보다 이긴다
    p = HT.doc_path("표 다루기"); t = _read(p).replace("guide: c.md", "guide: mine.md"); open(p, "w").write(t)
    assert HT.recall("표 다루기", db)["guide"] == "mine.md"
    # 문서에 줄이 아예 없어도 지도·회상은 씨앗으로 채운다
    p2 = HT.doc_path("부동산"); open(p2, "w").write(_read(p2).replace("guide: a.md, b.md\n", ""))
    assert HT.guide_of(p2) == "" and HT.recall("부동산", db)["guide"] == "a.md, b.md"
    assert "guide: a.md, b.md" in HT.map_text(db)


def _read(p):
    return open(p, encoding="utf-8").read()


def test_refresh_renders_topic_doc_and_map(env):
    HT, db = env
    a = _add(db, "부동산 실거래가를 조회", '[sense:realty]{source: "molit", region: "오송"}', "부동산", ok=3)
    _add(db, "결과를 가격순 정렬", '[table:sort]{by: "price"}', "표 다루기")
    HT.refresh_all(db)
    doc = HT.doc_path("부동산")
    text = _read(doc)
    assert 'topic="부동산"' in text and f"‹#{a} · ✓3/✗0" in text and "[sense:realty]" in text
    assert "table:sort" not in text
    m = HT.map_text(db)
    assert "- 부동산 (1)" in m and "- 표 다루기 (1)" in m and "sense:realty" not in m


def test_doc_edit_syncs_update_delete_insert_with_syntax_gate(env):
    HT, db = env
    a = _add(db, "옛 의도", '[self:memory]{op: "search", query: "x"}', "기억")
    b = _add(db, "지울 용례", '[self:memory]{op: "read", memory_id: 1}', "기억")
    HT.refresh_topic("기억", db)
    doc = HT.doc_path("기억")
    text = _read(doc).replace("옛 의도", "고친 의도")
    text = "\n".join(l for l in text.splitlines() if f"‹#{b}" not in l) + "\n"
    text = text.replace(HT.SECTION_NOTE, HT.SECTION_NOTE
                        + "\n- 새로 적은 용례 → `[self:memory]{op: \"recall\", node: \"가족\"}`"
                        + "\n- 깨진 용례 → `[self:memory{op: recall`")
    open(doc, "w", encoding="utf-8").write(text)
    os.utime(doc, (os.path.getmtime(doc) + 5, os.path.getmtime(doc) + 5))
    out = HT.sync_topic("기억", db)
    assert out["synced"] and out["updated"] == 1 and out["deleted"] == 1 and out["inserted"] == 1
    assert out.get("rejected"), out
    rows = {r["id"]: r for r in HT.rows_of("기억", db)}
    assert rows[a]["intent"] == "고친 의도" and b not in rows
    assert any(r["intent"] == "새로 적은 용례" and r["nodes"] == "self" for r in rows.values())
    assert HT.sync_topic("기억", db)["synced"] is False


def test_recall_children_move_and_unfiled(env):
    HT, db = env
    x = _add(db, "AI 동향 보고서 발행", '[self:report]{op: "new", type: "ai_trend"}', "보고서/AI 동향")
    _add(db, "부동산 발굴 보고서", '[self:report]{op: "new", type: "housing"}', "보고서/부동산")
    u = _add(db, "미배치 용례", '[sense:search]{query: "x"}')
    out = HT.recall("보고서", db)
    assert out["success"] and out["count"] == 0 and sorted(c["topic"] for c in out["children"]) == ["보고서/AI 동향", "보고서/부동산"]
    assert HT.recall("없는가지", db)["success"] is False
    mv = HT.move(x, "보고서/부동산", db)
    assert mv["success"] and "ai_trend" in _read(HT.doc_path("보고서/부동산"))
    assert [r["id"] for r in HT.unfiled(db)] == [u]
    assert "(뿌리 — 아직 가지가 없는 용례) (1)" in HT.map_text(db)


def test_file_unfiled_places_by_model_verdict(env):
    HT, db = env
    _add(db, "기존", '[sense:realty]{source: "molit"}', "부동산")
    u1 = _add(db, "실거래가 조회", '[sense:realty]{source: "molit", region: "평택"}')
    u2 = _add(db, "모름", '[self:ask]{prompt: "x"}')
    seen = {}

    def fake_ai(prompt, system_prompt):
        seen["prompt"] = prompt
        return json.dumps({str(u1): "부동산", str(u2): ""})
    out = HT.file_unfiled(fake_ai, db_path=db)
    assert "- 부동산 (1)" in seen["prompt"] and str(u1) in seen["prompt"]
    assert out["filed"] == 1 and out["skipped"] == 1 and out["new_topics"] == []
    assert "평택" in _read(HT.doc_path("부동산"))


def test_gist_and_guide_lines_reach_the_map(env):
    HT, db = env
    _add(db, "x", '[self:report]{op: "list"}', "보고서")
    p = HT.refresh_topic("보고서", db, guide="ai_trend_report.md")
    text = _read(p).replace(HT.GIST_PLACEHOLDER, "정기 보고서 발행 문장들")
    open(p, "w", encoding="utf-8").write(text)
    assert HT.gist_of(p) == "정기 보고서 발행 문장들" and HT.guide_of(p) == "ai_trend_report.md"
    assert "— 정기 보고서 발행 문장들 · guide: ai_trend_report.md" in HT.map_text(db)


if __name__ == "__main__":                      # 러너는 하나 — pytest
    sys.exit(pytest.main([__file__, "-q"]))
