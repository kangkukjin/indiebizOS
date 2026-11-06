"""Package identity, cache invalidation and call leases at the loader boundary."""
import json
from concurrent.futures import ThreadPoolExecutor

import boot_paths  # noqa: F401
import pytest
import tool_loader as loader
import vocabulary_state as state
from test_vocabulary_state import box


@pytest.fixture
def packages(box, monkeypatch):
    import runtime_utils
    import program_runtime
    monkeypatch.setattr(loader, 'get_base_path', lambda: box)
    monkeypatch.setattr(loader, 'get_tools_path', lambda: box / 'data/packages/installed/tools')
    monkeypatch.setattr(runtime_utils, 'get_installed_packages_root', lambda: box / 'data/packages/installed')
    monkeypatch.setattr(runtime_utils, 'get_source_root', lambda: box)
    monkeypatch.setattr(program_runtime, '_programs', {})
    for name in ('_package_handlers_cache', '_package_handler_mtimes', '_tool_to_package_map'):
        monkeypatch.setattr(loader, name, {})
    monkeypatch.setattr(loader, '_tool_map_source', None)
    root = state.package_path('awake')
    (root / 'tool.json').write_text(json.dumps({'tools': [{'name': 'a'}, {'name': 'b'}]}))
    (root / 'handler.py').write_text('state = 0\ndef execute(args, context):\n global state\n state += 1\n return state\n')
    state.invalidate_inventory()
    return root


def test_tools_share_state_and_concurrent_cold_reference(packages):
    with ThreadPoolExecutor(2) as pool:
        a, b = list(pool.map(loader.load_tool_handler, ['a', 'b']))
    assert a is b
    assert a.execute({}, None) == 1
    assert b.execute({}, None) == 2


def test_owner_change_and_removed_tool_do_not_return_old_reference(packages):
    old = loader.load_tool_handler('a')
    (packages / 'tool.json').write_text(json.dumps({'tools': [{'name': 'b'}]}))
    other = state.package_path('base')
    (other / 'tool.json').write_text(json.dumps({'tools': [{'name': 'a'}]}))
    (other / 'handler.py').write_text('def execute(args, context): return "new-owner"\n')
    new = loader.load_tool_handler('a')
    assert new is not old
    assert new.execute({}, None) == 'new-owner'
    (other / 'tool.json').write_text(json.dumps({'tools': []}))
    assert loader.load_tool_handler('a') is None


def test_running_generator_survives_clear(packages):
    (packages / 'handler.py').write_text('def execute(args, context):\n yield 1\n yield 2\n')
    old = loader.load_tool_handler('a')
    pending = old.execute({}, None)
    assert next(pending) == 1
    loader.clear_cache()
    new = loader.load_tool_handler('b')
    assert new is old
    assert list(pending) == [2]
    assert list(new.execute({}, None)) == [1, 2]


def test_missing_and_failed_handler_do_not_reuse_stale_module(packages):
    loader.load_tool_handler('a')
    (packages / 'handler.py').unlink()
    assert loader.load_tool_handler('a') is None
    (packages / 'handler.py').write_text('raise RuntimeError("broken handler")\n')
    assert loader.load_tool_handler('a') is None


def test_live_guide_metadata_is_stripped_without_mutating_definitions():
    definitions = [{'name': 'a', 'guide_file': 'guide.md', 'input_schema': {}}, {'name': 'b'}]
    assert loader._strip_guide_file_field(definitions) == [
        {'name': 'a', 'input_schema': {}}, {'name': 'b'}]
    assert definitions[0]['guide_file'] == 'guide.md'


def test_mapping_snapshot_changes_on_selection_and_metadata(packages, monkeypatch):
    import copy
    initial = loader.build_tool_package_map()
    assert initial['a'] == 'awake'
    assert loader.build_tool_package_map() is initial
    # 원장 선택만 바뀌어도 메타데이터 mtime과 무관하게 매핑 갱신.
    changed = copy.deepcopy(state.read_state())
    changed['active']['awake'] = False
    changed['revision'] += 1
    state.write_state(changed)
    assert 'a' not in loader.build_tool_package_map()
    assert initial['a'] == 'awake', '이미 취득한 매핑 스냅샷은 변경하지 않는다'
    with pytest.raises(ValueError, match='잠들어'):
        loader.load_tool_handler('a')
    changed['active']['awake'] = True
    changed['revision'] += 1
    state.write_state(changed)
    (packages / 'tool.json').write_text(json.dumps({'tools': [{'name': 'renamed'}]}))
    current = loader.build_tool_package_map()
    assert 'a' not in current and current['renamed'] == 'awake'
    loader.clear_cache()
    assert loader.build_tool_package_map() == current
    assert loader.build_tool_package_map() is not current


def test_mapping_uses_inventory_paths_without_a_second_root_probe(packages, monkeypatch):
    # 재고는 실제 활성 패키지 경로를 이미 제공한다. 다른 데이터 루트의
    # 설치 폴더 부재로 빈 매핑을 캐시하면 루트 복원 뒤에도 그 결과가 남는다.
    with monkeypatch.context() as isolated:
        isolated.setattr(loader, 'get_tools_path', lambda: packages / 'absent')
        observed = loader.build_tool_package_map(force=True)
        assert observed == {'a': 'awake', 'b': 'awake', 'base': 'base'}
    assert loader.build_tool_package_map() is observed


def test_mapping_rebuild_and_clear_are_serialized(packages, monkeypatch):
    import threading
    entered, release, clear_started, cleared = (threading.Event() for _ in range(4))
    original = loader.active_paths

    def paths(root):
        entered.set()
        assert release.wait(5)
        return original(root)

    def clear():
        clear_started.set()
        loader.clear_cache()
        cleared.set()

    monkeypatch.setattr(loader, 'active_paths', paths)
    with ThreadPoolExecutor(2) as pool:
        rebuilding = pool.submit(loader.build_tool_package_map, True)
        try:
            assert entered.wait(5)
            clearing = pool.submit(clear)
            assert clear_started.wait(5)
            assert not cleared.wait(0.05), '재생성 중인 매핑과 판본을 반쪽만 지우면 안 된다'
        finally:
            release.set()
        first = rebuilding.result(5)
        clearing.result(5)
    assert first['a'] == 'awake'
    assert loader.build_tool_package_map()['a'] == 'awake'
    assert loader.build_tool_package_map() is not first


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
