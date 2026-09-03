"""정본=문서(forage_doc) — 렌더/파싱 왕복 · note→문서 절 재렌더 · 문서 편집→색인 동기화 · 이관.

실행: .venv/bin/python -m pytest backend/test_forage_doc.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401
boot_paths.install()
import forage_memory as FM  # noqa: E402
import forage_doc as FD  # noqa: E402

ROOT = "/x/media"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(FM, "_DB_PATH", str(tmp_path / "forage.db"))
    monkeypatch.setattr(FD, "DOC_DIR", str(tmp_path / "docs"))
    monkeypatch.setattr(FD, "reconcile_lazy", lambda *a, **k: None)   # 시험의 가짜 경로는 실재하지 않는다 — 대조는 전용 시험에서만
    return tmp_path


def test_note_renders_section_and_roundtrips(env):
    FM.note_map(body="disk:T", locus=ROOT, kind="identity", claim="미디어 폴더 — 축이 섞임", confidence=0.9, territory=True)
    FM.note_map(body="disk:T", locus=ROOT, kind="convention", claim="파일명 = 원제.연도", confidence=0.8, generalizes=True)
    FM.note_map(body="disk:T", locus=ROOT + "/sf", kind="dead_branch", claim="1편뿐", confidence=0.9, prune_reason="폴더가 비었음")
    path = FD.doc_path_for("disk:T", ROOT, create_default=False)
    assert path and os.path.exists(path)
    text = open(path, encoding="utf-8").read()
    assert FD.SECTION in text and "### /x/media" in text and "### /x/media/sf" in text
    parsed = FD.parse_section(text)
    assert {(p["locus"], p["kind"]) for p in parsed} == {(ROOT, "identity"), (ROOT, "convention"), (ROOT + "/sf", "dead_branch")}
    root_id = next(p for p in parsed if p["kind"] == "identity")
    assert root_id["territory"] and not root_id["generalizes"]
    assert next(p for p in parsed if p["kind"] == "convention")["generalizes"]
    assert next(p for p in parsed if p["kind"] == "dead_branch")["prune_reason"] == "폴더가 비었음"


def test_doc_edit_syncs_index_via_recall(env):
    FM.note_map(body="disk:T", locus=ROOT, kind="identity", claim="옛 정체", confidence=0.7, territory=True)
    path = FD.doc_path_for("disk:T", ROOT, create_default=False)
    text = open(path, encoding="utf-8").read()
    # 사람이 편집기에서 줄을 고치고 한 줄을 더한다
    text = text.replace("- [identity] ⚑ 옛 정체", "- [identity] ⚑ 새 정체(주인이 고침)")
    text = text.replace("### /x/media\n", "### /x/media\n- [dead_branch] 여긴 자막 없음\n")
    os.utime  # noqa
    open(path, "w", encoding="utf-8").write(text)
    os.utime(path, None)
    res = FM.recall(locus=ROOT, limit=20)   # 회상이 문서 시각을 보고 색인을 맞춘다
    claims = {(m["kind"], m["claim"]) for m in res["map"] if m["via"] == "own"}
    assert ("identity", "새 정체(주인이 고침)") in claims and ("dead_branch", "여긴 자막 없음") in claims
    assert ("identity", "옛 정체") not in claims
    assert res["doc"] == path


def test_forget_removes_line_from_doc(env):
    r = FM.note_map(body="disk:T", locus=ROOT, kind="substrate", claim="외장 디스크", confidence=0.8)
    FM.forget(entry_id=r["id"])
    text = open(FD.doc_path_for("disk:T", ROOT, create_default=False), encoding="utf-8").read()
    assert "외장 디스크" not in text


def test_migrate_groups_by_root_and_body(env):
    FM.note_map(body="mac", locus="/Users/u/Desktop/AI/x", kind="identity", claim="AI 하위", confidence=0.7)
    FM.note_map(body="mac", locus="/Users/u/Desktop", kind="identity", claim="바탕화면", confidence=0.7)
    FM.note_map(body="web", locus="arXiv", kind="identity", claim="논문 출처", confidence=0.7)
    FM.note_map(body="code:repo", locus="backend/x.py", kind="convention", claim="층 규칙", confidence=0.7)
    out = FD.migrate_all()
    rel = sorted(os.path.relpath(os.path.join(FD.DOC_DIR, w["doc"]), FD.DOC_DIR) for w in out["written"])
    docs = sorted(os.path.relpath(p, FD.DOC_DIR) for p, _b, _r in FD._scan_docs())
    assert docs == ["code_repo/memory.md", "mac/Users/u/Desktop/memory.md", "web/memory.md"], docs
    desk = open(os.path.join(FD.DOC_DIR, "mac/Users/u/Desktop/memory.md"), encoding="utf-8").read()
    assert "### /Users/u/Desktop" in desk and "### /Users/u/Desktop/AI/x" in desk


def test_existing_ai_document_keeps_prose_and_gains_section(env):
    """옛 평평한 문서(표식 있음)는 migrate_layout 이 트리 자리로 옮기고, 산문은 보존되며 절이 붙는다."""
    os.makedirs(FD.DOC_DIR, exist_ok=True)
    flat = os.path.join(FD.DOC_DIR, "x_media.md")
    open(flat, "w", encoding="utf-8").write('<!-- forage-doc body="disk:T" root="/x/media" -->\n# 폴더 조사 — /x/media\n\n## 정체\n- 사람이 쓴 산문\n\n## 갱신 기록\n- 2026-09-03 처음\n')
    FM.note_map(body="disk:T", locus=ROOT, kind="identity", claim="정체 한 줄", confidence=0.9, territory=True)
    moved = FD.migrate_layout()
    p = os.path.join(FD.DOC_DIR, "disk_T/x/media/memory.md")
    assert os.path.exists(p) and not os.path.exists(flat) and moved["moved"]
    FD.refresh_doc_for("disk:T", ROOT)
    text = open(p, encoding="utf-8").read()
    assert "- 사람이 쓴 산문" in text and FD.SECTION in text and text.index(FD.SECTION) < text.index("## 갱신 기록")
    assert "정체 한 줄" in text


def test_two_lines_of_same_kind_coexist(env):
    FM.note_map(body="disk:T", locus=ROOT, kind="convention", claim="장르가 나라를 이긴다", confidence=0.7)
    FM.note_map(body="disk:T", locus=ROOT, kind="convention", claim="시리즈는 시리즈 폴더로", confidence=0.7)
    res = FM.recall(locus=ROOT, limit=20)
    assert {m["claim"] for m in res["map"] if m["kind"] == "convention"} == {"장르가 나라를 이긴다", "시리즈는 시리즈 폴더로"}
    text = open(FD.doc_path_for("disk:T", ROOT, create_default=False), encoding="utf-8").read()
    assert text.count("- [convention]") == 2


def test_bodies_sharing_a_root_get_separate_docs(env):
    FM.note_map(body="mac", locus="/Users/u/Desktop/a", kind="identity", claim="맥 것", confidence=0.7)
    FM.note_map(body="disk:X", locus="/Users/u/Desktop/b", kind="identity", claim="외장 것", confidence=0.7)
    docs = {b: p for p, b, r in FD._scan_docs()}
    assert docs["mac"] != docs["disk:X"] and "/mac/Users/u/Desktop/" in docs["mac"] and "/disk_X/Users/u/Desktop/" in docs["disk:X"]
    assert "맥 것" in open(docs["mac"], encoding="utf-8").read() and "맥 것" not in open(docs["disk:X"], encoding="utf-8").read()


def test_nonpath_root_doc_never_covers_path_loci(env):
    """재발 방지(2026-09-03 사고): 디스크 몸의 경로 없는 locus 문서(root=mac)가 경로 locus 를 덮으면 동기화가 경로 단언을 지운다."""
    FM.note_map(body="mac", locus="__substrate__", kind="substrate", claim="EXIF 없음", confidence=0.7)
    FM.note_map(body="mac", locus="/Users/u/Desktop", kind="identity", claim="바탕화면", confidence=0.7)
    docs = {os.path.relpath(p, FD.DOC_DIR): (b, r) for p, b, r in FD._scan_docs()}
    assert "mac/memory.md" in docs and "mac/Users/u/Desktop/memory.md" in docs
    assert not FD._covers("mac", "mac", "/Users/u/Desktop")
    assert [x["claim"] for x in FD.rows_for_doc("mac", "mac")] == ["EXIF 없음"]
    # mac.md 를 통째로 비워도(사고 재현) 경로 단언은 살아남는다
    p = os.path.join(FD.DOC_DIR, "mac", "memory.md")
    open(p, "w", encoding="utf-8").write(open(p, encoding="utf-8").read().split(FD.SECTION)[0] + FD.SECTION + "\n")
    FD.sync_doc_to_db(p)
    res = FM.recall(locus="/Users/u/Desktop", limit=10)
    assert any(m["claim"] == "바탕화면" for m in res["map"])


def test_territory_makes_own_node_and_ancestors_see_it(env):
    """영토 앵커를 찍은 하위 폴더는 자기 노드 문서를 얻고, 상위 문서의 절에서 그 아래 행이 빠지며, docs_below 로 드러난다."""
    FM.note_map(body="mac", locus="/Users/u/Desktop", kind="identity", claim="바탕화면", confidence=0.8, territory=True)
    FM.note_map(body="mac", locus="/Users/u/Desktop/AI/x", kind="identity", claim="AI 하위 x", confidence=0.7)
    desk = os.path.join(FD.DOC_DIR, "mac/Users/u/Desktop/memory.md")
    assert "AI 하위 x" in open(desk, encoding="utf-8").read()
    FM.note_map(body="mac", locus="/Users/u/Desktop/AI", kind="identity", claim="AI 폴더 — 따로 조사됨", confidence=0.9, territory=True)
    ai = os.path.join(FD.DOC_DIR, "mac/Users/u/Desktop/AI/memory.md")
    assert os.path.exists(ai)
    assert "AI 하위 x" in open(ai, encoding="utf-8").read() and "AI 하위 x" not in open(desk, encoding="utf-8").read()
    assert [os.path.relpath(p, FD.DOC_DIR) for p in FD.docs_below("mac", "/Users/u/Desktop")] == ["mac/Users/u/Desktop/AI/memory.md"]
    assert FD._ancestor_chain("mac", "/Users/u/Desktop/AI/x/y") == [ai, desk]
    assert FM.recall(locus="/Users/u/Desktop/AI/x", limit=5)["doc"] == ai


def _mk_real(tmp, rel, children):
    d = tmp / rel
    for c in children:
        (d / c).mkdir(parents=True, exist_ok=True)
    return str(d)


def test_reconcile_moves_when_one_strong_candidate(env, monkeypatch):
    real = env / "real"
    old = _mk_real(real, "Desktop/photos", ["2019", "2020", "misc"])
    FM.note_map(body="mac", locus=old, kind="identity", claim="사진 모음", confidence=0.8, territory=True)
    FM.note_map(body="mac", locus=old + "/2019", kind="identity", claim="2019년", confidence=0.7)
    FM.note_map(body="mac", locus=old + "/2020", kind="identity", claim="2020년", confidence=0.7)
    new = str(real / "Archive/photos"); os.makedirs(os.path.dirname(new), exist_ok=True); os.rename(old, new)
    decoy = _mk_real(real, "Other/photos", ["a", "b"])   # 이름만 같은 폴더
    monkeypatch.setattr(FD, "_search_dirs_by_name", lambda name: [new, decoy])
    rep = FD.reconcile("mac")
    assert rep["moved"] and rep["moved"][0]["from"] == old and rep["moved"][0]["to"] == new and rep["moved"][0]["rows"] == 3
    assert os.path.exists(FD.doc_path_at("mac", new)) and not os.path.exists(FD.doc_path_at("mac", old))
    res = FM.recall(locus=new, limit=10)
    assert {m["claim"] for m in res["map"] if m["via"] in ("own", "child")} >= {"사진 모음"}
    assert "이사" in open(FD.doc_path_at("mac", new), encoding="utf-8").read()


def test_reconcile_tombstones_when_no_candidate(env, monkeypatch):
    real = env / "real"
    parent = _mk_real(real, "Desktop", [])
    gone = _mk_real(real, "Desktop/temp", ["x"])
    FM.note_map(body="mac", locus=parent, kind="identity", claim="바탕화면", confidence=0.8, territory=True)
    FM.note_map(body="mac", locus=gone, kind="identity", claim="임시", confidence=0.7, territory=True)
    import shutil; shutil.rmtree(gone)
    monkeypatch.setattr(FD, "_search_dirs_by_name", lambda name: [])
    rep = FD.reconcile("mac")
    assert rep["gone"] and rep["gone"][0]["root"] == gone
    assert not os.path.exists(FD.doc_path_at("mac", gone))
    assert os.path.exists(os.path.join(FD.DOC_DIR, "mac", FD.GONE_DIR, *[p for p in gone.split("/") if p], "memory.md"))
    ptext = open(FD.doc_path_at("mac", parent), encoding="utf-8").read()
    assert "사라짐" in ptext and "temp" in ptext
    res = FM.recall(locus=gone, limit=10)   # 단언은 남되 표식이 붙는다
    assert any(m["claim"] == "임시" and m.get("surface_flag") for m in res["map"])
    assert FD.docs_below("mac", parent) == []


def test_reconcile_holds_when_ambiguous_and_skips_unmounted(env, monkeypatch):
    real = env / "real"
    gone = _mk_real(real, "Desktop/notes", ["a", "b"])
    FM.note_map(body="mac", locus=gone, kind="identity", claim="메모", confidence=0.7, territory=True)
    FM.note_map(body="mac", locus=gone + "/a", kind="identity", claim="a", confidence=0.6)
    c1 = _mk_real(real, "X/notes", ["a", "b"]); c2 = _mk_real(real, "Y/notes", ["a", "b"])
    import shutil; shutil.rmtree(gone)
    monkeypatch.setattr(FD, "_search_dirs_by_name", lambda name: [c1, c2])
    FM.note_map(body="disk:Q", locus="/Volumes/NotMounted-zz/stuff", kind="identity", claim="외장", confidence=0.7, territory=True)
    rep = FD.reconcile()
    assert rep["ambiguous"] and rep["ambiguous"][0]["root"] == gone and len(rep["ambiguous"][0]["candidates"]) == 2
    assert os.path.exists(FD.doc_path_at("mac", gone)) and "이사 후보" in open(FD.doc_path_at("mac", gone), encoding="utf-8").read()
    assert "/Volumes/NotMounted-zz/stuff" in rep["unmounted"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
