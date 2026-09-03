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
    names = sorted(w["doc"] for w in out["written"])
    assert names == sorted(["Users_u_Desktop.md", "code_repo.md", "web.md"])
    desk = open(os.path.join(FD.DOC_DIR, "Users_u_Desktop.md"), encoding="utf-8").read()
    assert "### /Users/u/Desktop" in desk and "### /Users/u/Desktop/AI/x" in desk


def test_existing_ai_document_keeps_prose_and_gains_section(env):
    os.makedirs(FD.DOC_DIR, exist_ok=True)
    p = os.path.join(FD.DOC_DIR, "x_media.md")
    open(p, "w", encoding="utf-8").write("# 폴더 조사 — /x/media\n\n## 정체\n- 사람이 쓴 산문\n\n## 갱신 기록\n- 2026-09-03 처음\n")
    # 표식이 없으면 기본 뿌리 문서(x_media.md = slug(/x/media))로 간다
    FM.note_map(body="disk:T", locus=ROOT, kind="identity", claim="정체 한 줄", confidence=0.9, territory=True)
    text = open(p, encoding="utf-8").read()
    assert text.startswith('<!-- forage-doc body="disk:T" root="/x/media" -->')
    assert "- 사람이 쓴 산문" in text and FD.SECTION in text and text.index(FD.SECTION) < text.index("## 갱신 기록")


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
    assert docs["mac"] != docs["disk:X"]
    assert "맥 것" in open(docs["mac"], encoding="utf-8").read() and "맥 것" not in open(docs["disk:X"], encoding="utf-8").read()


def test_nonpath_root_doc_never_covers_path_loci(env):
    """재발 방지(2026-09-03 사고): 디스크 몸의 경로 없는 locus 문서(root=mac)가 경로 locus 를 덮으면 동기화가 경로 단언을 지운다."""
    FM.note_map(body="mac", locus="__substrate__", kind="substrate", claim="EXIF 없음", confidence=0.7)
    FM.note_map(body="mac", locus="/Users/u/Desktop", kind="identity", claim="바탕화면", confidence=0.7)
    docs = {os.path.basename(p): (b, r) for p, b, r in FD._scan_docs()}
    assert "mac.md" in docs and "Users_u_Desktop.md" in docs
    assert not FD._covers("mac", "mac", "/Users/u/Desktop")
    assert [x["claim"] for x in FD.rows_for_doc("mac", "mac")] == ["EXIF 없음"]
    # mac.md 를 통째로 비워도(사고 재현) 경로 단언은 살아남는다
    p = os.path.join(FD.DOC_DIR, "mac.md")
    open(p, "w", encoding="utf-8").write(open(p, encoding="utf-8").read().split(FD.SECTION)[0] + FD.SECTION + "\n")
    FD.sync_doc_to_db(p)
    res = FM.recall(locus="/Users/u/Desktop", limit=10)
    assert any(m["claim"] == "바탕화면" for m in res["map"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
