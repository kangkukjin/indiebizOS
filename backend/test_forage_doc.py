"""정본=문서(forage_doc) — 렌더/파싱 왕복 · note→문서 절 재렌더 · 문서 편집→색인 동기화 · 이관.

실행: .venv/bin/python -m pytest backend/test_forage_doc.py -q
"""
import os
import sys
import time

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
    p = os.path.join(FD.DOC_DIR, "mac/x/media/memory.md")   # 경로 문서는 몸 표기와 무관하게 트리
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


def test_path_loci_share_one_tree_regardless_of_body(env):
    """절대 경로 단언은 몸 표기(code:*·disk:*)와 무관하게 mac 트리 문서 하나에 모인다(2026-09-03 사용자 판정)."""
    FM.note_map(body="mac", locus="/Users/u/Desktop/a", kind="identity", claim="맥 것", confidence=0.7)
    FM.note_map(body="code:Repo", locus="/Users/u/Desktop/a/backend", kind="identity", claim="증류가 코드 라벨을 붙인 경로", confidence=0.7)
    FM.note_map(body="code:Repo", locus="module.x", kind="convention", claim="경로 없는 코드 관습", confidence=0.7)
    docs = {(b, r): p for p, b, r in FD._scan_docs()}
    assert set(docs) == {("mac", "/Users/u/Desktop"), ("code:Repo", "code:Repo")}, docs
    tree = open(docs[("mac", "/Users/u/Desktop")], encoding="utf-8").read()
    code = open(docs[("code:Repo", "code:Repo")], encoding="utf-8").read()
    assert "맥 것" in tree and "코드 라벨을 붙인 경로" in tree and "경로 없는 코드 관습" not in tree
    assert "경로 없는 코드 관습" in code and "코드 라벨을 붙인 경로" not in code
    # 회상도 트리 문서를 집는다(몸을 code 로 물어도)
    out = FM.recall(locus="/Users/u/Desktop/a/backend", body="code:Repo", limit=10)
    assert out["doc"] == docs[("mac", "/Users/u/Desktop")]


def test_migrate_layout_moves_body_folder_path_docs_into_tree(env):
    """옛 배치(disk_X/…경로…/memory.md)의 경로 문서는 한 번의 migrate_layout 으로 mac 트리로 옮겨지고, 산문이 긴 쪽이 남는다."""
    FM.note_map(body="disk:X", locus="/Volumes/X/movies", kind="identity", claim="영상 폴더", confidence=0.8, territory=True)
    tree_doc = FD.doc_path_at("mac", "/Volumes/X/movies")
    assert os.path.exists(tree_doc)
    old_dir = os.path.join(FD.DOC_DIR, "disk_X", "Volumes", "X", "movies"); os.makedirs(old_dir)
    old_doc = os.path.join(old_dir, FD.DOC_NAME)
    open(old_doc, "w", encoding="utf-8").write('<!-- forage-doc body="disk:X" root="/Volumes/X/movies" -->\n# 폴더 조사\n\n## 정체\n- AI 가 길게 쓴 산문 ' + "이야기 " * 40 + '\n')
    out = FD.migrate_layout()
    assert any(m["to"].startswith("mac/Volumes/X/movies") for m in out["moved"]), out
    assert not os.path.exists(old_doc) and not os.path.isdir(os.path.join(FD.DOC_DIR, "disk_X"))
    text = open(tree_doc, encoding="utf-8").read()
    assert "AI 가 길게 쓴 산문" in text and "영상 폴더" in text and 'body="mac"' in text


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
    d.mkdir(parents=True, exist_ok=True)
    for c in children:
        (d / c).mkdir(parents=True, exist_ok=True)
    return str(d)


def test_reconcile_tombstones_missing_and_skips_unmounted(env):
    """폴더가 없어지면 그 노드(와 밑)의 문서를 _gone 으로 접고 부모에 한 줄, 단언은 표식만. 안 꽂힌 볼륨은 건너뜀. 이사 감지는 하지 않는다(사용자 판정)."""
    real = env / "real"
    parent = _mk_real(real, "Desktop", [])
    gone = _mk_real(real, "Desktop/temp", ["x"])
    FM.note_map(body="mac", locus=parent, kind="identity", claim="바탕화면", confidence=0.8, territory=True)
    FM.note_map(body="mac", locus=gone, kind="identity", claim="임시", confidence=0.7, territory=True)
    FM.note_map(body="mac", locus=gone + "/x", kind="identity", claim="임시 x", confidence=0.6, territory=True)
    FM.note_map(body="disk:Q", locus="/Volumes/NotMounted-zz/stuff", kind="identity", claim="외장", confidence=0.7, territory=True)
    import shutil; shutil.rmtree(gone)
    rep = FD.reconcile()
    assert [g["root"] for g in rep["gone"]] == [gone]            # 밑의 x 는 통째로 같이 접힌다
    assert "/Volumes/NotMounted-zz/stuff" in rep["unmounted"]
    assert not os.path.exists(FD.doc_path_at("mac", gone))
    archived = os.path.join(FD.DOC_DIR, "mac", FD.GONE_DIR, *[p for p in gone.split("/") if p])
    assert os.path.exists(os.path.join(archived, "memory.md")) and os.path.exists(os.path.join(archived, "x", "memory.md"))
    ptext = open(FD.doc_path_at("mac", parent), encoding="utf-8").read()
    assert "사라짐" in ptext and "temp" in ptext
    res = FM.recall(locus=gone, limit=10)
    assert any(m["claim"] == "임시" and m.get("surface_flag") for m in res["map"])
    assert FD.docs_below("mac", parent) == []


def test_purge_gone_after_a_week(env):
    real = env / "real"
    gone = _mk_real(real, "Desktop/old", [])
    FM.note_map(body="mac", locus=gone, kind="identity", claim="옛것", confidence=0.7, territory=True)
    import shutil; shutil.rmtree(gone)
    FD.reconcile("mac")
    archived = os.path.join(FD.DOC_DIR, "mac", FD.GONE_DIR, *[p for p in gone.split("/") if p], "memory.md")
    assert os.path.exists(archived)
    assert FD.purge_gone(days=7)["removed"] == []                 # 아직 일주일 안 됨
    old = time.time() - 8 * 86400; os.utime(archived, (old, old))
    assert FD.purge_gone(days=7)["removed"]
    assert not os.path.exists(archived)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ----------------------------------------------------------------- 웹 트리 (2026-09-03: URL locus 는 host/path 트리)
def test_web_url_loci_land_in_host_path_tree_regardless_of_scheme_and_body(env):
    FM.note_map(body="web", locus="https://github.com/acme/harness", kind="identity", claim="하네스 저장소", confidence=0.9)
    FM.note_map(body="web", locus="github.com/acme/harness/docs", kind="convention", claim="문서는 docs/ 아래", confidence=0.8)
    FM.note_map(body="web:https://github.com/acme", locus="https://github.com/acme?tab=repos", kind="identity", claim="acme 조직", confidence=0.7)
    FM.note_map(body="web", locus="Nature", kind="identity", claim="학술지", confidence=0.6)
    tree = FD.doc_path_at("web", "github.com/acme")
    assert os.path.exists(tree) and tree.endswith(os.path.join("web", "github.com", "acme", "memory.md"))
    text = open(tree, encoding="utf-8").read()
    assert "### https://github.com/acme/harness" in text and "### github.com/acme/harness/docs" in text
    assert "### https://github.com/acme?tab=repos" in text
    assert FD._read_marker(tree) == ("web", "github.com/acme")
    # 주제 라벨은 웹 몸 뿌리 문서에, URL 은 거기 없다
    root_doc = FD.doc_path_at("web", "web")
    root_text = open(root_doc, encoding="utf-8").read()
    assert "### Nature" in root_text and "github.com" not in root_text
    assert not os.path.isdir(os.path.join(FD.DOC_DIR, "web_https__github.com_acme"))


def test_host_like_locus_in_non_web_body_stays_in_body_doc(env):
    FM.note_map(body="code:site", locus="README.md", kind="identity", claim="저장소 소개", confidence=0.9)
    FM.note_map(body="book:x", locus="irepublic.brain", kind="identity", claim="책 속 상표", confidence=0.9)
    assert not os.path.isdir(os.path.join(FD.DOC_DIR, "web"))
    assert "### README.md" in open(FD.doc_path_at("code:site", "code:site"), encoding="utf-8").read()
    assert "### irepublic.brain" in open(FD.doc_path_at("book:x", "book:x"), encoding="utf-8").read()


def test_web_recall_walks_ancestor_chain_and_child_skeleton(env):
    FM.note_map(body="web", locus="https://claude.ai", kind="substrate", claim="SPA, 로그인 필요", confidence=0.9, generalizes=True)
    FM.note_map(body="web", locus="claude.ai/design", kind="identity", claim="디자인 캔버스", confidence=0.9)
    FM.note_map(body="web", locus="claude.ai/design/canvas", kind="identity", claim="아트보드 편집기", confidence=0.8)
    res = FM.recall(locus="https://claude.ai/design/", limit=20)
    via = {(m["via"], m["kind"]) for m in res["map"]}
    assert ("own", "identity") in via and ("inherit", "substrate") in via and ("child", "identity") in via
    assert res["doc"] == FD.doc_path_at("web", "claude.ai")   # 호스트 문서가 먼저 생겼으니 하위 URL 은 그 조상 문서에(디스크와 같은 규칙)
    assert res["docs_below"] == []
    # 사람이 호스트 문서를 고치면 색인이 따라온다(정본=문서)
    p = res["doc"]
    text = open(p, encoding="utf-8").read().replace("### claude.ai/design\n", "### claude.ai/design\n- [dead_branch] 옛 베타 경로 없음\n")
    open(p, "w", encoding="utf-8").write(text); os.utime(p, None)
    res2 = FM.recall(locus="claude.ai/design", limit=20)
    assert ("dead_branch", "옛 베타 경로 없음") in {(m["kind"], m["claim"]) for m in res2["map"]}


def test_migrate_layout_moves_web_url_body_doc_into_tree(env):
    FM.note_map(body="web:https://platform.example.com/usage", locus="https://platform.example.com/usage", kind="identity", claim="사용량 대시보드", confidence=0.9)
    # 옛 배치: 몸 라벨 폴더의 문서(표식은 옛 몸·옛 뿌리) — 사람이 쓴 산문이 있다
    old_dir = os.path.join(FD.DOC_DIR, FD.slug("web:https://platform.example.com/usage"))
    os.makedirs(old_dir, exist_ok=True)
    old = os.path.join(old_dir, "memory.md")
    open(old, "w", encoding="utf-8").write('<!-- forage-doc body="web:https://platform.example.com/usage" root="web:https://platform.example.com/usage" -->\n# 포식 기억\n\n주간 그래프는 월요일에 갱신된다는 걸 여러 번 확인했다.\n\n## 단언\n')
    out = FD.migrate_layout()
    dst = FD.doc_path_at("web", "platform.example.com/usage")
    assert any(m["to"] == os.path.relpath(dst, FD.DOC_DIR) for m in out["moved"])
    assert not os.path.exists(old)
    text = open(dst, encoding="utf-8").read()
    assert FD._read_marker(dst) == ("web", "platform.example.com/usage")
    assert "월요일에 갱신" in text and "### https://platform.example.com/usage" in text
