"""위치 기반 회상(FOLDER_SURVEY_HANDOFF §3) — 2-gram 매칭·초점 조립·상속·자식 골격·조사 원장 힌트.

실행: .venv/bin/python -m pytest backend/test_forage_location_recall.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401
boot_paths.install()
import forage_memory as FM  # noqa: E402

ROOT = "/x/media"


@pytest.fixture
def fm(monkeypatch, tmp_path):
    monkeypatch.setattr(FM, "_DB_PATH", str(tmp_path / "forage.db"))
    b = "disk:T"
    FM.note_map(body=b, locus=ROOT, kind="identity", claim="미디어 보관 폴더 — 축이 섞임(장르/나라/상태). 주제어: 영화 자막",
                confidence=0.9, territory=True)
    FM.note_map(body=b, locus=ROOT, kind="substrate", claim="외장 디스크, 마운트 필요", confidence=0.8)
    FM.note_map(body=b, locus=ROOT, kind="convention", claim="파일명 = 원제.연도.태그", confidence=0.8, generalizes=True)
    # 같은 (body, locus, kind) 는 upsert 로 합쳐지므로 두 번째 관습은 "/*" 표기(위계상 같은 자리)로
    FM.note_map(body=b, locus=ROOT + "/*", kind="convention", claim="장르 폴더가 나라 폴더를 이긴다", confidence=0.6, prior_class="semantic")
    FM.note_map(body=b, locus=ROOT + "/unseen", kind="identity", claim="상태 축 — 미시청 작품만 여기", confidence=0.7)
    FM.note_map(body=b, locus=ROOT + "/horror", kind="identity", claim="공포 장르", confidence=0.7)
    FM.note_map(body=b, locus=ROOT + "/sf", kind="dead_branch", claim="1편뿐 — 믿지 말 것", confidence=0.9)
    FM.note_map(body=b, locus=ROOT + "/horror/deep", kind="identity", claim="손자 폴더 — 부속 자료", confidence=0.5)
    FM.note_map(body="mac", locus="/y/other", kind="identity", claim="무관한 다른 공간", confidence=0.7)
    FM.record_survey(body=b, locus=ROOT, depth=2, budget={"dirs": 10}, spent={"dirs": 3},
                     item_resolution=True, artifact_dir=str(tmp_path / "art"))
    return FM


def _paths(res, via=None):
    return [m["locus"] for m in res["map"] if via is None or m["via"] == via]


def test_phrase_bridges_spacing(fm):
    """'미 시청' 을 이어붙인 구절 '미시청' 이 그 폴더를 잇는다(낱말 통째 일치 없이)."""
    res = fm.recall(query="미 시청 작품 중에 뭐 볼까", limit=12)
    assert ROOT + "/unseen" in _paths(res, "match")


def test_focus_assembles_own_inherit_child(fm):
    res = fm.recall(query="공포 장르 뭐 있어", limit=12)
    assert ROOT + "/horror" in _paths(res, "match")
    # 조상 상속: generalizes 관습·기질은 오고, 비일반화 semantic 관습은 안 온다
    inherit = [m for m in res["map"] if m["via"] == "inherit"]
    assert {m["claim"] for m in inherit} >= {"파일명 = 원제.연도.태그", "외장 디스크, 마운트 필요"}
    assert all(m["claim"] != "장르 폴더가 나라 폴더를 이긴다" for m in inherit)
    # 자식 골격: 초점(horror)의 직계 자식 한 줄(short)
    child = {m["locus"]: m for m in res["map"] if m["via"] == "child"}
    assert ROOT + "/horror/deep" in child and child[ROOT + "/horror/deep"]["short"]
    # 루트도 초점("장르"가 루트 단언에 있음)이라 루트의 자식 골격도 온다 — 위계 두 층이 한 번에
    assert ROOT + "/sf" in child


def test_root_focus_lists_children_skeleton(fm):
    res = fm.recall(query="영화 폴더 구성이 어떻게 돼", limit=12)
    assert ROOT in _paths(res)
    kids = {m["locus"] for m in res["map"] if m["via"] == "child"}
    assert kids == {ROOT + "/unseen", ROOT + "/horror", ROOT + "/sf"}
    assert ROOT + "/horror/deep" not in kids  # 손자는 골격에 안 올라온다(자기 폴더를 지명해야)


def test_unrelated_query_matches_nothing(fm):
    res = fm.recall(query="오늘 회의 일정", limit=12)
    assert res["map"] == [] and res["surveys"] == []


def test_survey_hint_for_focus(fm):
    res = fm.recall(query="자막 있는 영화", limit=12)
    assert [s["locus"] for s in res["surveys"]] == [ROOT]
    assert res["surveys"][0]["item_resolution"] == 1
    xml = fm.recall_xml(query="자막 있는 영화", limit=12)
    assert '<survey path="/x/media" items="1"' in xml and 'via="' in xml


def test_no_query_keeps_full_listing(fm):
    res = fm.recall(limit=50)
    assert all(m["via"] == "all" for m in res["map"]) and len(res["map"]) >= 8


def test_ascii_terms_need_word_boundary(fm):
    fm.note_map(body="mac", locus="/code/x", kind="identity", claim="returns=items 또는 transform 액션", confidence=0.7)
    res = fm.recall(query="sf 영화", limit=12)
    assert "/code/x" not in _paths(res)


def test_accidental_syllable_overlap_is_not_a_match(fm):
    fm.note_map(body="mac", locus="/code/hook", kind="substrate", claim="훅 목록이 하드코딩돼 있어 이하 생략", confidence=0.7)
    res = fm.recall(query="다이하드 3편", limit=12)
    assert "/code/hook" not in _paths(res)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
