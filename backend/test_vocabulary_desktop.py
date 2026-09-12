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
        for op in ("move", "remove_folder", "rename"):
            with pytest.raises(ValueError, match="고정"):
                edit(op, item=item, name="renamed")
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
