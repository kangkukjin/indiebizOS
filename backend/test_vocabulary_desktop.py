"""아이콘 공간과 활성 선택의 일치, 보존, 보호, 폴더 순환을 검증한다."""
import boot_paths  # 직접 실행에서도 층 모듈 경로를 준비한다.
import copy

import pytest
import vocabulary_state as state
from test_vocabulary_state import box
from vocabulary_desktop import CORE, ROOT, STORE, TRASH, edit_desktop, get_desktop, package_words
from vocabulary_lifecycle import HUMAN_AUTHORITY, set_package_active


@pytest.fixture(autouse=True)
def reset_caches(monkeypatch):
    import ibl_routing
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: [])


def edit(op, **kwargs):
    return edit_desktop(op, authority=HUMAN_AUTHORITY, **kwargs)


def test_initial_layout_and_sleep_wake_preserve_files(box):
    before = {p: p.read_bytes() for p in box.rglob('*') if p.is_file()}
    layout = get_desktop()
    assert layout["placements"]["base"]["parent"] == CORE
    assert layout["placements"]["asleep"]["parent"] == STORE
    edit("move", item="awake", parent=STORE)
    assert not state.is_active("awake")
    layout = edit("move", item="awake", parent=ROOT, x=351, y=217)
    assert state.is_active("awake")
    assert layout["placements"]["awake"] == {"parent": ROOT, "x": 351, "y": 217}
    assert get_desktop() == layout
    assert all(p.read_bytes() == content for p, content in before.items())


def test_required_and_special_folders_protected_server_side(box):
    for destination in (ROOT, STORE, TRASH):
        with pytest.raises(ValueError, match="필수"):
            edit("move", item="base", parent=destination)
    for item in (CORE, STORE, TRASH):
        for op in ("remove_folder", "rename"):
            with pytest.raises(ValueError, match="특수"):
                edit(op, item=item, name="renamed")
    for item in (CORE, STORE):
        with pytest.raises(ValueError, match="고정"):
            edit("move", item=item, parent=ROOT)
    with pytest.raises(ValueError):
        edit("move", item="awake", parent=CORE)
    with pytest.raises(ValueError, match="화면"):
        edit_desktop("move", item="awake", parent=STORE)


def test_trash_restore_and_folder_removal(box):
    original = get_desktop()["placements"]["awake"]["parent"]
    edit("move", item="awake", parent=TRASH)
    assert not state.is_active("awake")
    assert edit("restore", item="awake")["placements"]["awake"]["parent"] == original
    assert state.is_active("awake")
    edit("move", item="asleep", parent=TRASH)
    assert edit("restore", item="asleep")["placements"]["asleep"]["parent"] == STORE
    assert not state.is_active("asleep")
    layout = edit("create_folder", name="My folder")
    fid = next(k for k, v in layout["folders"].items() if v["name"] == "My folder")
    edit("move", item="awake", parent=fid)
    with pytest.raises(ValueError, match="자기"):
        edit("move", item=fid, parent=fid)
    layout = edit("create_folder", name="Child", parent=fid)
    child = next(k for k, v in layout["folders"].items() if v["name"] == "Child")
    with pytest.raises(ValueError, match="자기"):
        edit("move", item=fid, parent=child)
    layout = edit("remove_folder", item=fid)
    assert layout["placements"]["awake"]["parent"] == ROOT
    assert layout["folders"][child]["parent"] == ROOT
    assert state.is_active("awake")


def test_failed_activation_keeps_placement_and_state(box, monkeypatch):
    import ibl_routing
    before = copy.deepcopy(get_desktop())
    calls = iter([["failed"], []])
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: next(calls))
    with pytest.raises(RuntimeError):
        edit("move", item="awake", parent=STORE)
    assert get_desktop() == before
    assert state.is_active("awake")


def test_external_lifecycle_changes_and_new_import_appear(box):
    get_desktop()
    set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    assert get_desktop()["placements"]["awake"]["parent"] == STORE
    assert state.read_state()["desktop"]["placements"]["awake"]["parent"] == STORE
    edit("move", item="awake", parent=TRASH)
    set_package_active("awake", True, authority=HUMAN_AUTHORITY)
    assert get_desktop()["placements"]["awake"]["parent"] == ROOT
    (box / "data/packages/installed/tools/new").mkdir()
    assert get_desktop()["placements"]["new"]["parent"] == STORE


def test_words_are_visible_without_loading_sleeping_handler(box):
    assert package_words("asleep")[0]["name"] == "[sense:asleep]"
    assert not state.is_active("asleep")


def test_arrange_leaves_special_folders_fixed_and_rejects_bad_position(box):
    before = get_desktop()
    after = edit("arrange", parent=ROOT, columns=3)
    assert all(before["folders"][key] == after["folders"][key] for key in (CORE, STORE, TRASH))
    with pytest.raises(ValueError, match="위치"):
        edit("move", item="awake", parent=ROOT, x=float('nan'))


def test_trash_moves_on_desktop_preserving_contents_and_sleep(box):
    edit("move", item="awake", parent=TRASH)
    layout = edit("move", item=TRASH, parent=ROOT, x=820, y=480)
    assert get_desktop()["folders"][TRASH] == layout["folders"][TRASH]
    assert layout["folders"][TRASH]["x"] == 820
    assert layout["folders"][TRASH]["y"] == 480
    assert layout["placements"]["awake"]["parent"] == TRASH
    assert not state.is_active("awake")
    assert edit("arrange")["folders"][TRASH] == layout["folders"][TRASH]
    for parent in (CORE, STORE, TRASH):
        with pytest.raises(ValueError, match="바탕"):
            edit("move", item=TRASH, parent=parent)
    edit("restore", item="awake")
    assert state.is_active("awake")


def test_arrange_snaps_near_current_position_instead_of_packing_by_id(box):
    # 같은 폴더에서 왼쪽 아래/오른쪽 위의 배치 의미와 빈 공간을 유지한다.
    layout = edit("create_folder", name="공간")
    parent = next(k for k, f in layout["folders"].items() if f["name"] == "공간")
    edit("create_folder", name="아래", parent=parent, x=35, y=380)
    edit("move", item="awake", parent=parent, x=370, y=30)
    before_active = copy.deepcopy(state.read_state()["active"])
    after = edit("arrange", parent=parent, columns=4)
    lower = next(f for f in after["folders"].values() if f["name"] == "아래")
    assert (lower["x"], lower["y"]) == (24, 372)
    assert after["placements"]["awake"] == {"parent": parent, "x": 372, "y": 24}
    assert edit("arrange", parent=parent, columns=4) == after
    assert get_desktop() == after
    assert state.read_state()["active"] == before_active


def test_arrange_preserves_occupied_grid_and_avoids_off_grid_trash(box):
    layout = edit("create_folder", name="공간")
    parent = next(k for k, f in layout["folders"].items() if f["name"] == "공간")
    edit("create_folder", name="제자리", parent=parent, x=140, y=140)
    edit("move", item="awake", parent=parent, x=139, y=139)
    layout = edit("arrange", parent=parent, columns=3)
    fixed = next(f for f in layout["folders"].values() if f["name"] == "제자리")
    pos = layout["placements"]["awake"]
    assert (fixed["x"], fixed["y"]) == (140, 140)
    assert (pos["x"], pos["y"]) != (140, 140)
    assert (pos["x"] - 24) % 116 == (pos["y"] - 24) % 116 == 0

    edit("move", item=TRASH, x=600, y=485)
    edit("move", item="awake", x=604, y=487)
    layout = edit("arrange", columns=8)
    trash, pos = layout["folders"][TRASH], layout["placements"]["awake"]
    assert (trash["x"], trash["y"]) == (600, 485)
    assert abs(trash["x"] - pos["x"]) >= 116 or abs(trash["y"] - pos["y"]) >= 116
    assert edit("arrange", columns=8) == layout


def test_arrange_narrow_folder_keeps_rows_and_resolves_collisions(box):
    edit("move", item="base", parent=CORE, x=900, y=374)
    layout = edit("arrange", parent=CORE, columns=1)
    assert layout["placements"]["base"] == {"parent": CORE, "x": 24, "y": 372}
    # 저장고 바로 아래 칸은 큰 아이콘·두 줄 이름과 겹치므로 비워 둔다.
    edit("move", item="awake", x=24, y=140)
    layout = edit("arrange", columns=4)
    pos = layout["placements"]["awake"]
    assert (pos["x"], pos["y"]) != (24, 140)
    assert (pos["x"] - 24) % 116 == (pos["y"] - 24) % 116 == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
