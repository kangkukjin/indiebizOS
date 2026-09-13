"""분리된 실제 묶음의 독립 배포와 선택·기억 계약 회귀."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import vocabulary_state as state
from vocabulary_archive import export_directory, unpack
from test_vocabulary_archive import runtime  # noqa: F401 — 임시 사전·시딩 DB

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "data/packages/installed/tools"
SPLITS = {
    "entity-lookup": ("study", ["sense:entity"]),
    "world-statistics": ("study", ["sense:world_bank"]),
    "books": ("culture", ["sense:book", "sense:classic"]),
    "freelance-services": ("shopping-assistant", ["sense:freelance"]),
}


def load_handler(pid):
    path = PACKAGES / pid / "handler.py"
    spec = importlib.util.spec_from_file_location("split_" + pid, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def split_box(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "vocabulary_policy.yaml").write_bytes((ROOT / "data/vocabulary_policy.yaml").read_bytes())
    base = data / "packages/installed/tools"
    base.mkdir(parents=True)
    for pid in set(SPLITS) | {s for s, _ in SPLITS.values()}:
        (base / pid).symlink_to(PACKAGES / pid, target_is_directory=True)
    state.invalidate_inventory()
    yield tmp_path
    state.invalidate_inventory()


@pytest.mark.parametrize("active,parent", [(True, "folder-own"), (False, "store"), (False, "trash")])
def test_split_inherits_selection_and_placement_once(split_box, active, parent):
    origins = {s for s, _ in SPLITS.values()}
    old = {"version": 1, "revision": 8, "active": {s: active for s in origins},
           "desktop": {"folders": {"folder-own": {"name": "내 분류", "parent": "desktop", "x": 500, "y": 24}},
                       "placements": {s: {"parent": parent, "x": 24 + i * 116, "y": 24,
                                           "restore": {"parent": "folder-own"}}
                                      for i, s in enumerate(sorted(origins))}}}
    state.write_state(old, split_box)
    actual = state.read_state(split_box)
    assert actual["revision"] == 9
    for pid in SPLITS:
        assert actual["active"][pid] is active
        assert actual["desktop"]["placements"][pid]["parent"] == parent
        assert actual["desktop"]["placements"][pid]["restore"] == {"parent": "folder-own"}
    assert {s: actual["desktop"]["placements"][s] for s in origins} == old["desktop"]["placements"]
    positions = list(actual["desktop"]["placements"].values())
    assert len({(p["parent"], p["x"], p["y"]) for p in positions}) == len(positions)
    # 사용자가 자식만 잠재운 뒤 원본을 바꿔도 그 선택을 덮어쓰지 않는다.
    chosen = copy.deepcopy(actual)
    chosen["active"]["world-statistics"] = False
    chosen["active"]["study"] = True
    state.write_state(chosen, split_box)
    before = state.state_path(split_box).read_bytes()
    assert not state.read_state(split_box)["active"]["world-statistics"]
    assert state.state_path(split_box).read_bytes() == before
    assert actual["active"]["world-statistics"] is active  # 이전 반환 객체도 불변


def test_late_package_arrival_is_inherited_even_after_cached_read(split_box):
    link = split_box / "data/packages/installed/tools/world-statistics"
    link.unlink()
    state.write_state({"version": 1, "revision": 0, "active": {"study": True}}, split_box)
    assert "world-statistics" not in state.read_state(split_box)["active"]
    link.symlink_to(PACKAGES / "world-statistics", target_is_directory=True)
    assert state.read_state(split_box)["active"]["world-statistics"]


def test_fresh_install_inherits_sleeping_parent_location(split_box):
    asleep = split_box / "data/packages/not_installed/tools"
    asleep.mkdir(parents=True)
    (split_box / "data/packages/installed/tools/study").rename(asleep / "study")
    actual = state.read_state(split_box)
    assert not actual["active"]["study"]
    assert not actual["active"]["world-statistics"]
    assert not actual["active"]["entity-lookup"]


def test_existing_child_choice_and_unrelated_install_are_not_activated(split_box):
    old = {"version": 1, "revision": 4, "active": {"study": True, "world-statistics": False}}
    state.write_state(old, split_box)
    actual = state.read_state(split_box)
    assert not actual["active"]["world-statistics"]
    assert "books" not in actual["active"]  # 원본 선택을 모르는 설치는 자동으로 깨우지 않음


def test_state_without_split_policy_keeps_existing_selection(split_box):
    (split_box / "data/vocabulary_policy.yaml").unlink()
    old = {"version": 1, "revision": 4, "active": {"study": True}}
    state.write_state(old, split_box)
    assert state.read_state(split_box) == old
    assert state.read_state(split_box) == old  # 캐시에서도 선언 없는 자식은 추가하지 않음


def test_moved_word_gate_and_recall_are_independent_from_parent(split_box, monkeypatch):
    import runtime_utils
    import ibl_registry
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: split_box)
    monkeypatch.setattr(state, "get_base_path", lambda: split_box)
    monkeypatch.setattr(ibl_registry, "_nodes_path", ROOT / "data/ibl_nodes.yaml")
    monkeypatch.setattr(ibl_registry, "_merge_api_registry_actions", lambda _: None)
    monkeypatch.setattr(ibl_registry, "_nodes", None)
    state.write_state({"version": 1, "revision": 1, "active": {"study": True}}, split_box)
    assert ibl_registry.code_is_own('[sense:world_bank]{indicator: "GDP"}')
    chosen = copy.deepcopy(state.read_state(split_box))
    chosen["active"]["world-statistics"] = False
    chosen["revision"] += 1
    state.write_state(chosen, split_box)
    assert not ibl_registry.code_is_own('[sense:world_bank]{indicator: "GDP"}')
    assert ibl_registry.code_is_own('[sense:paper]{query: "AI"}')
    with pytest.raises(ValueError, match="잠들어"):
        state.require_tool_active("fetch_world_bank_data", split_box)


@pytest.mark.parametrize("pid,tool,params", [
    ("books", "book_op", {"op": "codes", "code_type": "region"}),
    ("entity-lookup", "entity_op", {"query": ""}),
    ("world-statistics", "fetch_world_bank_data", {"indicator": "GDP", "country": "한국"}),
    ("freelance-services", "freelance_search", {}),
])
def test_exported_bundle_runs_without_original_package(tmp_path, pid, tool, params):
    payload = export_directory(PACKAGES / pid, pid)
    manifest, files, examples = unpack(payload)
    assert manifest["id"] == pid and examples
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # 새 프로세스에는 backend와 내보낸 묶음만 추가한다. 원본 패키지를 import할 수 없다.
    program = '''
import sys, importlib.util, json
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import boot_paths
spec = importlib.util.spec_from_file_location("exported", sys.argv[2])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if sys.argv[3] == "fetch_world_bank_data":
    mod.requests.get = lambda *a, **kw: SimpleNamespace(raise_for_status=lambda: None, json=lambda: [{}, [
        {"date": "2024", "value": 100, "indicator": {"value": "GDP"}, "country": {"value": "Korea"}}
    ]])
result = mod.execute(json.loads(sys.argv[4]), SimpleNamespace(tool_name=sys.argv[3]))
if isinstance(result, str): result = json.loads(result)
assert isinstance(result, dict)
if sys.argv[3] in ("book_op", "fetch_world_bank_data"): assert result and not result.get("error")
else: assert result.get("error") or result.get("success") is False
print("ok")
'''
    run = subprocess.run([sys.executable, "-I", "-c", program, str(ROOT / "backend"),
                          str(tmp_path / "handler.py"), tool, json.dumps(params)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr


def test_split_archives_register_without_any_original_bundle(runtime):
    from vocabulary_import import import_package
    from ibl_usage_db import IBLUsageDB
    payloads = {pid: export_directory(PACKAGES / pid, pid) for pid in SPLITS}
    for pid in set(SPLITS) | {s for s, _ in SPLITS.values()}:
        (runtime / "data/packages/installed/tools" / pid).unlink()
    state.invalidate_inventory()
    for pid, payload in payloads.items():
        result = import_package(payload)
        assert result["package_id"] == pid and result["status"] == "sleeping"
        assert result["seeded"] > 0
        assert not state.is_active(pid)
        assert import_package(payload)["status"] == "already_owned"
    assert IBLUsageDB().get_stats()["total_examples"] >= 5


def test_world_bank_response_contract(monkeypatch):
    mod = load_handler("world-statistics")
    def get(url, **kwargs):
        assert "/country/KOR/indicator/NY.GDP.MKTP.CD" in url
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: [{}, [
            {"date": "2025", "value": None, "indicator": {"value": "GDP"}, "country": {"value": "Korea"}},
            {"date": "2024", "value": 200, "indicator": {"value": "GDP"}, "country": {"value": "Korea"}},
            {"date": "2023", "value": 100, "indicator": {"value": "GDP"}, "country": {"value": "Korea"}},
        ]])
    monkeypatch.setattr(mod.requests, "get", get)
    result = json.loads(mod.execute({"indicator": "GDP", "country": "한국"},
                                   SimpleNamespace(tool_name="fetch_world_bank_data")))
    assert result["success"]
    assert result["items"] == [{"연도": "2023", "GDP": 100}, {"연도": "2024", "GDP": 200}]


def test_entity_and_books_keep_response_contracts(monkeypatch):
    entity = load_handler("entity-lookup")
    monkeypatch.setattr(entity, "_wd_search", lambda *a: [{"id": "Q42", "label": "Douglas Adams", "description": "writer"}])
    result = entity.execute({"query": "Adams"}, SimpleNamespace(tool_name="entity_op"))
    if isinstance(result, str):
        result = json.loads(result)
    assert result["success"] and result["count"] == 1 and "Q42" in str(result["items"])
    books = load_handler("books")
    monkeypatch.setitem(sys.modules, "tool_gutenberg", SimpleNamespace(search_gutenberg=lambda **kw: {
        "results": [{"title": "A &amp; B", "date": "20260913"}]}))
    result = json.loads(books.execute({"query": "test"}, SimpleNamespace(tool_name="classic_op")))
    assert result["items"] == [{"title": "A & B", "date": "2026.09.13"}]


def test_freelance_keeps_real_provider_adapter_contract(monkeypatch):
    import common.http_fetch as http
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        return SimpleNamespace(status_code=200, text=json.dumps({
            "totalItemCount": 1, "gigs": [{"gigId": 123, "title": "로고 제작", "price": 50000,
                                            "seller": {"nickname": "designer"}, "review": {}}]}))
    monkeypatch.setattr(http, "chrome_get", get)
    mod = load_handler("freelance-services")
    result = json.loads(mod.execute({"query": "로고", "limit": 1}, SimpleNamespace(tool_name="freelance_search")))
    assert result["items"][0]["title"] == "로고 제작"
    assert result["items"][0]["price"] == 50000
    assert len(seen) == 1 and "gigs/search" in seen[0]


def test_package_ownership_and_phone_actions_are_preserved():
    inv = state.inventory(ROOT)
    phone = json.loads((ROOT / "data/phone_manifest.json").read_text())
    for pid, (_, actions) in SPLITS.items():
        assert pid in phone["packages"]
        assert set(actions) <= set(phone["runnable_actions"])
        assert all(inv["actions"][a] == pid for a in actions)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
