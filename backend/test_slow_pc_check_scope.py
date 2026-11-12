"""A catalog update shares one check scope and can finish after an existing body starts."""
import sys
import threading
import types

import boot_paths  # noqa: F401

import ibl_dependencies as deps
import vocabulary_state as vs


def test_nested_compiles_share_one_check_observation():
    reads = []
    with deps.compilation_dependencies():
        outer = deps._check_metadata.get()
        for _ in range(3):
            with deps.compilation_dependencies():   # compile_program 의 데코레이터 자리
                assert deps._check_metadata.get() is outer
                deps._check_value(('environment', 'x'), lambda: reads.append(1) or 'fp')
    assert reads == [1]
    assert deps._check_metadata.get() is None   # 실행은 검사 관측을 물려받지 않는다


def test_candidate_registry_never_shares_enclosing_snapshot(tmp_path):
    with deps.compilation_dependencies():
        outer = deps._check_metadata.get()
        with deps.using_script_registry(tmp_path / 'registry.yaml', {}):
            assert deps._check_metadata.get() is not outer
        assert deps._check_metadata.get() is outer


def test_pinned_inventory_scope_survives_the_window(monkeypatch, tmp_path):
    scans = []
    real = vs._location_root
    monkeypatch.setattr(vs, '_location_root', lambda root, loc: scans.append(loc) or real(root, loc))
    monkeypatch.setattr(vs, '_SCOPE_WINDOW_S', 0.0)        # 느린 PC: 창이 매번 만료된다
    with vs.inventory_scope(pinned=True):
        for _ in range(5):
            with vs.inventory_scope():                    # build_tool_package_map 의 데코레이터 자리
                vs.inventory(tmp_path)
    assert scans.count('installed') == 1
    scans.clear()
    with vs.inventory_scope():                            # 고정 아닌 범위는 종전대로 창을 따른다
        vs.inventory(tmp_path)
        vs.inventory(tmp_path)
    assert scans.count('installed') == 2


def test_publication_check_is_one_observation(monkeypatch):
    import function_library as fl
    seen = {}

    def probe(before, after, changed):
        seen['check'] = deps._check_metadata.get() is not None
        seen['pinned'] = bool((vs._scope.get() or {}).get(vs._PINNED))
        return {}
    monkeypatch.setattr(fl, '_validate_changes', probe)
    fl.validate_changes({'records': {}, 'generation': 0}, {'records': {}, 'generation': 1}, set())
    assert seen == {'check': True, 'pinned': True}


def test_function_install_does_not_block_boot(monkeypatch):
    started, release, done = threading.Event(), threading.Event(), threading.Event()

    def install(base):
        started.set()
        release.wait(5)
        done.set()
        return {'updated': [], 'conflicts': []}
    monkeypatch.setitem(sys.modules, 'function_install', types.SimpleNamespace(install=install))
    import boot_common
    monkeypatch.setattr('function_store.catalog', lambda root: {'functions': {'existing': {}}})
    assert boot_common._start_function_install('[test]', defer_updates=True) == 'background'
    try:
        assert started.wait(5)
        assert not done.is_set()
    finally:
        release.set()
    assert done.wait(5)


def test_first_boot_installs_before_return(monkeypatch, tmp_path):
    import boot_common
    import function_install
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    outcome = {'updated': ['first'], 'conflicts': []}
    monkeypatch.setattr(function_install, 'install', lambda base: outcome)
    assert boot_common._start_function_install('[test]', defer_updates=True) == outcome


def test_non_server_caller_finishes_existing_catalog_update(monkeypatch, tmp_path):
    import boot_common
    import function_install

    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('function_store.catalog', lambda root: {'functions': {'existing': {}}})
    outcome = {'updated': ['existing'], 'conflicts': []}
    monkeypatch.setattr(function_install, 'install', lambda base: outcome)
    assert boot_common._start_function_install('[test]', defer_updates=False) == outcome
