"""상상훈련 78회차 포식 기억 잔여 — B78-4·B78-5·F78-1·F78-3(forage) 회귀 시험 (2026-09-29).

뿌리: 같은 사실("그 장소가 있나"·"그 장소의 이름")을 층마다 따로 번역했다 —
  - 존재: recall 의 root_missing 은 경로 문서 뿌리만, reconcile 은 경로 노드만, 노트북 삭제는 기억을 모른다 → 확인기 한 벌(place_exists)
  - 이름: 입구는 book:·notebook: 을 정규화 면제, 회상은 행 locus 를 문자 그대로 비교 → 정규형 한 벌(own_space_label·own_space_address)
전부 tmp_path 안(forage DB·문서 폴더·노트북 DB)만 만진다 — 실 저장소·모델 무접촉.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401
boot_paths.install()
import forage_memory as FM  # noqa: E402
import forage_doc as FD  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _pkg_handler(pkg: str):
    import importlib.util
    pkg_dir = str(ROOT / "data" / "packages" / "installed" / "tools" / pkg)
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    name = f"tool_handler_{pkg.replace('-', '_')}_under_test"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, os.path.join(pkg_dir, "handler.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def _all_places(_q):
    """장소 찾기의 의미 채널(인코더) 대신 — 기억에 있는 모든 장소 이름을 place_id 그대로(같은 이름 함수) 준다."""
    from forage_recall_store import ForageStore, _cache
    _cache.clear()
    return [it.id for it in ForageStore().items()]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(FM, "_DB_PATH", str(tmp_path / "forage.db"))
    monkeypatch.setattr(FD, "DOC_DIR", str(tmp_path / "docs"))
    monkeypatch.setattr(FM, "_NOTEBOOK_DB", str(tmp_path / "nb" / "notebooks.db"))
    monkeypatch.setattr(FM, "_trail", lambda *a, **k: None)          # 되먹임 원장(실 경로) 무접촉
    monkeypatch.setattr(FM, "_place_order", lambda q: [])
    FM._nb_cache.clear()
    return tmp_path


@pytest.fixture
def nb(env, monkeypatch):
    pkg = str(ROOT / "data" / "packages" / "installed" / "tools" / "notebook")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    import notebook_core as core
    H = _pkg_handler("notebook")
    monkeypatch.setattr(core, "NOTEBOOK_DIR", env / "nb")
    monkeypatch.setattr(core, "DB_PATH", env / "nb" / "notebooks.db")
    (env / "nb").mkdir()
    monkeypatch.setattr(core, "semantic_available", lambda: False)
    monkeypatch.setattr(H, "_card_after_index", lambda *args: None)
    return core, H


def _legacy_row(body, locus, kind="identity", claim="옛 단언"):
    """수리 전에 쌓인 행(괄호 몸·주제 이름 locus) — 입구를 거치지 않고 색인에 직접. 데이터는 개명하지 않는다."""
    conn = FM._connect()
    try:
        conn.execute("INSERT INTO forage_map (body, locus, kind, claim, confidence, provenance, last_seen) VALUES (?,?,?,?,?,?,?)",
                     (body, locus, kind, claim, 0.8, "{}", "2026-09-01"))
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────── F78-1 없는(오타) 장소의 정직 칸
def test_typo_folder_says_no_memory_and_no_place(env):
    real = env / "projects"
    (real / "부동산").mkdir(parents=True)
    FM.note_map(body="mac", locus=str(real), kind="convention", claim="폴더 이름 = 주제", confidence=0.9, generalizes=True)
    FM.note_map(body="mac", locus=str(real / "부동산"), kind="identity", claim="부동산 분석 작업장", confidence=0.9)

    typo = FM.recall(locus=str(real / "부동삼"))
    assert typo["success"] and typo["map"] and all(m["via"] == "inherit" for m in typo["map"])
    assert typo["own_count"] == 0                     # 그 장소의 기억은 없다 — inherit 는 조상의 것
    assert typo["locus_exists"] is False              # 그 장소 자체가 없다
    assert typo["doc_is_ancestor"] is True and typo["root_missing"] is False
    xml = FM.recall_xml(locus=str(real / "부동삼"))
    assert 'exists="false"' in xml and 'own_count="0"' in xml

    ok = FM.recall(locus=str(real / "부동산"))
    assert ok["own_count"] == 1 and ok["locus_exists"] is True


# ─────────────────────────────── B78-5 책·노트북 몸의 이름 정규형
def test_own_space_label_is_one_function_for_write_and_read():
    assert FM.own_space_label("book:<하네스: 부제>") == "book:하네스: 부제"
    assert FM.own_space_label("notebook: <AI  동향> / <소스 제목> ") == "notebook:AI 동향/소스 제목"
    assert FM.own_space_address("book:<책 A>", "<책 A>") == "book:책 A"
    assert FM.own_space_address("book:책 A", "3장") == "book:책 A/3장"
    assert FM.own_space_address("book:책 A", "책 A/3장") == "book:책 A/3장"
    assert FM.own_space_address("book:책 A", "book:<책 A>/3장") == "book:책 A/3장"
    assert FM.own_space_address("book:책 A", "book:책 B/1장") is None      # 다른 몸의 주소
    assert FM.place_id("book:<책 A>", "아무 하위") == "book:책 A"


def test_entrance_writes_normal_form_and_rejects_other_body(env):
    r = FM.note_map(body="book:<책 A>", locus="<책 A>", kind="identity", claim="책 전체", confidence=0.9)
    assert r["success"]
    FM.note_map(body="book:책 A", locus="3장", kind="convention", claim="장마다 요약", confidence=0.8)
    bad = FM.note_map(body="book:책 A", locus="book:책 B/1장", kind="identity", claim="x", confidence=0.7)
    assert bad["success"] is False and bad["rejected"] == "locus_not_address"
    conn = FM._connect()
    try:
        rows = {(x["body"], x["locus"]) for x in conn.execute("SELECT body, locus FROM forage_map")}
    finally:
        conn.close()
    assert rows == {("book:책 A", "book:책 A"), ("book:책 A", "book:책 A/3장")}
    assert os.path.exists(FD.doc_path_at("book:책 A", "book:책 A"))
    assert not os.path.isdir(os.path.join(FD.DOC_DIR, FD.slug("book:<책 A>")))


def test_every_place_reopens_as_locus_including_legacy_rows(env, monkeypatch):
    """가드(78회차 B78-5): query 가 places 로 준 모든 장소 → locus 재호출 map_count ≥ 1."""
    _legacy_row("book:<하네스: 부제>", "하네스: 부제", claim="책 전체의 정체")          # 괄호 몸 + 제목 locus
    _legacy_row("book:<방법론 원문>", "전체", claim="방법론 정리")                        # 괄호 몸 + 주제 이름 locus
    _legacy_row("book:<방법론 원문>", "① 계층 요약 / RAPTOR", kind="convention", claim="계층 요약")
    FM.note_map(body="book:하네스", locus="book:하네스/conceptual_framework", kind="identity", claim="개념 틀", confidence=0.8)
    monkeypatch.setattr(FM, "_place_order", _all_places)
    res = FM.recall(query="하네스 방법론 개념")
    places = [p["place"] for p in res["places"]]
    assert set(places) == {"book:하네스: 부제", "book:방법론 원문", "book:하네스"}
    for p in places:
        again = FM.recall(locus=p)
        assert again["map_count"] >= 1 and again["own_count"] >= 1, p
        assert again["locus_exists"] is None               # 책은 바깥 세계 — 확인 대상 아님(거짓 false 금지)
    whole = FM.recall(locus="book:<방법론 원문>")           # 괄호 표기로 불러도 같은 장소
    assert whole["own_count"] == 2 and {m["claim"] for m in whole["map"]} == {"방법론 정리", "계층 요약"}
    assert whole["doc"] is None or "방법론" in whole["doc"]
    assert len(FM.recall(body="book:<방법론 원문>")["map"]) == 2   # 몸 거르기도 정규형으로


def test_unknown_own_space_locus_gets_no_foreign_doc(env):
    FM.note_map(body="notebook:독서", locus="notebook:독서", kind="identity", claim="서평 모음", confidence=0.9)
    res = FM.recall(locus="notebook:없는노트북")
    assert res["map_count"] == 0 and res["doc"] is None and res["own_count"] == 0


# ─────────────────────────────── B78-4 지운 노트북의 기억
def test_notebook_store_path_matches_package():
    """존재 확인기가 읽는 노트북 저장소 = notebook 패키지의 저장소(두 경로가 갈리면 모든 노트북이 '없음'이 된다)."""
    pkg = str(ROOT / "data" / "packages" / "installed" / "tools" / "notebook")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    import importlib
    core = importlib.import_module("notebook_core")
    assert os.path.realpath(FM._NOTEBOOK_DB) == os.path.realpath(str(core.DB_PATH))


def test_notebook_delete_folds_its_forage_memory(nb):
    core, H = nb
    assert core.create_notebook("스크래치")["success"]
    FM._nb_cache.clear()
    FM.note_map(body="notebook:스크래치", locus="notebook:스크래치", kind="identity", claim="훈련용 더미", confidence=0.9, territory=True)
    FM.note_map(body="notebook:스크래치", locus="notebook:스크래치/소스1", kind="identity", claim="소스 하나", confidence=0.8)
    live = FM.recall(locus="notebook:스크래치")
    assert live["locus_exists"] is True and live["root_missing"] is False
    assert all(m["freshness"] == "" for m in live["map"])
    doc = FD.doc_path_at("notebook:스크래치", "notebook:스크래치")
    assert os.path.exists(doc)

    out = json.loads(H._op_delete({"name": "스크래치"}, None))
    assert out["success"] and out["forage_memory"]["folded"]
    assert not os.path.exists(doc)
    gone = os.path.join(FD.DOC_DIR, FD.GONE_DIR, FD.slug("notebook:스크래치"), FD.DOC_NAME)
    assert os.path.exists(gone)
    after = FM.recall(locus="notebook:스크래치")
    assert after["locus_exists"] is False and after["doc"] is None
    assert after["map"] and all(m["freshness"] == "missing" and m["surface_flag"] for m in after["map"])
    assert all(str(m["prune_reason"]).startswith("장소 사라짐") for m in after["map"])
    # 유예는 접은 날부터 — 일주일 정리가 바로 지우지 않고, 기한이 지나면 맨 위 `_gone` 도 지운다
    assert FD.purge_gone()["removed"] == []
    assert FD.purge_gone(days=-1)["removed"] and not os.path.exists(gone)


def test_orphan_before_repair_is_marked_not_folded(nb):
    """수리 전에 지운 노트북의 기억(고아)은 지우지 않는다 — 회상이 정직하게 알리고, 전체 대조는 held 로만."""
    core, _H = nb
    assert core.create_notebook("남은것")["success"]
    FM._nb_cache.clear()
    FM.note_map(body="notebook:지운것", locus="notebook:지운것", kind="identity", claim="옛 더미", confidence=0.9)
    FM.note_map(body="notebook:남은것", locus="notebook:남은것", kind="identity", claim="살아 있는 더미", confidence=0.9)
    res = FM.recall(locus="notebook:지운것")
    assert res["locus_exists"] is False and res["root_missing"] is True and res["own_count"] == 1
    assert res["map"][0]["freshness"] == "missing"
    q = FM.recall(query="더미")
    fresh = {m["claim"]: m["freshness"] for m in q["map"]}
    assert fresh == {"옛 더미": "missing", "살아 있는 더미": ""}
    rep = FD.reconcile()
    assert rep["held"] == ["notebook:지운것"] and rep["gone"] == []
    assert os.path.exists(FD.doc_path_at("notebook:지운것", "notebook:지운것"))


# ─────────────────────────────── F78-3 교재·계약 드리프트(forage) · 증류 프롬프트 자리표
def test_forage_contract_has_no_retired_args_and_no_pipe_denial():
    tool = json.loads((ROOT / "data/packages/installed/tools/pc-manager/tool.json").read_text(encoding="utf-8"))
    schema = next(t for t in tool["tools"] if t["name"] == "forage_op")["input_schema"]["properties"]
    assert "layer" not in schema and "table" not in schema
    decl = (ROOT / "data/packages/installed/tools/pc-manager/ibl_actions.yaml").read_text(encoding="utf-8")
    assert "table 파이프 대상 아님" not in decl


def test_distill_prompt_teaches_no_copyable_form_placeholders():
    src = (ROOT / "backend/cognition/cognitive_distill.py").read_text(encoding="utf-8")
    start = src.index('extract_prompt = f"""')
    prompt = src[start:src.index('"""', start + 25)]
    for bad in ("book:<", "code:<", "disk:<", "notebook:<"):
        assert bad not in prompt, bad


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
