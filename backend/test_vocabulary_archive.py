"""공유 파일 → 잠든 등록 → 시딩 → 깨움 → 호출 → 다시 잠듦의 실제 경로."""
import io
import json
from pathlib import Path
import shutil
import zipfile

import pytest
import yaml

from vocabulary_archive import pack, unpack, export_package
import vocabulary_state as state
from ibl_routing import invalidate_runtime_caches as REAL_RESET

REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.system


def packet(edition=2):
    fragment = {'node': 'sense', 'actions': {'lego_probe': {
        'description': '공유 묶음 시험', 'router': 'handler', 'tool': 'lego_probe',
        'returns': 'items', 'side_effect': False, 'fixture': '[sense:lego_probe]{}',
        'runs_on': 'pc_only', 'group': 'test'}}, 'tool_json': {'header': {'name': 'lego_probe', 'version': '1.0.0',
        'description': '공유 묶음 시험'}, 'tools': [{'name': 'lego_probe',
        'description': '공유 묶음 시험', 'input_schema': {'type': 'object', 'properties': {}}}]}}
    return pack({'id': 'lego-probe', 'version': '1.0.0'}, {
        'handler.py': b'def execute(tool_input, context):\n    # lego_probe\n    return {"items": [{"value": "ok"}]}\n',
        'ibl_actions.yaml': yaml.safe_dump(fragment, allow_unicode=True).encode(),
        'examples.json': json.dumps([{'intent': '공유 어휘 시험', 'ibl_code': ('#!ibl edition=2\n' if edition == 2 else '') + '[sense:lego_probe]{}'}]).encode()})


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    for name in ('ibl_nodes_src', 'packages', 'guides'):
        # 보유 원본은 읽기 링크, 새 묶음만 임시 폴더에 쓴다.
        if name == 'packages':
            for loc in ('installed', 'not_installed'):
                for kind in ('tools', 'extensions'):
                    dst = data / name / loc / kind
                    dst.mkdir(parents=True)
                    src = REPO / 'data' / name / loc / kind
                    if src.exists():
                        for p in src.iterdir():
                            if p.is_dir() and not p.name.startswith('.'):
                                (dst / p.name).symlink_to(p, target_is_directory=True)
        else:
            (data / name).symlink_to(REPO / 'data' / name, target_is_directory=True)
    for name in ('ibl_nodes.yaml', 'vocabulary_policy.yaml', 'api_registry.yaml'):
        shutil.copy(REPO / 'data' / name, data / name)
    import runtime_utils, vocabulary_import, ibl_registry, ibl_routing, ibl_usage_db, tool_loader
    for mod in (runtime_utils, state, vocabulary_import, tool_loader):
        monkeypatch.setattr(mod, 'get_base_path', lambda: tmp_path)
    for name, value in {'_nodes_path': data / 'ibl_nodes.yaml', '_registry_path': data / 'api_registry.yaml',
                        '_nodes': None, '_registry': None, '_nodes_revision': None}.items():
        monkeypatch.setattr(ibl_registry, name, value)
    monkeypatch.setattr(ibl_usage_db, 'DB_PATH', str(data / 'usage.db'))
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_instance', None)
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_index_batch', lambda *a: None)
    monkeypatch.setattr(ibl_usage_db, '_tree_refresh', lambda *a: None)
    monkeypatch.setattr(ibl_usage_db, '_tree_refresh_all', lambda: None)
    def reset():
        ibl_registry._nodes = None
        ibl_registry._nodes_revision = None
        tool_loader._tool_handlers_cache.clear()
        tool_loader._tool_map_cache = None
        return []
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', reset)
    state.invalidate_inventory()
    yield tmp_path
    reset()
    state.invalidate_inventory()


def test_roundtrip_seed_sleep_wake(runtime):
    from vocabulary_import import import_package
    from vocabulary_lifecycle import set_package_active, HUMAN_AUTHORITY
    from ibl_usage_db import IBLUsageDB
    from ibl_registry import code_is_own, code_is_owned
    import tool_loader
    payload = packet()
    result = import_package(payload)
    assert result['status'] == 'sleeping' and result['seeded'] == 1
    assert code_is_owned('[sense:lego_probe]{}')
    assert not code_is_own('[sense:lego_probe]{}')
    from ibl_v2_learning import check_source, _owned_registry
    from ibl_v2_adapters import load_registry
    from ibl_v2_ir import Fault
    source = '#!ibl edition=2\n[sense:lego_probe]{}'
    assert check_source(source, owned_vocabulary=True) is None
    assert check_source(source) is not None
    assert check_source(source + '\nreturn $missing', owned_vocabulary=True) is not None
    assert 'sense:lego_probe' not in load_registry()
    with pytest.raises(Fault, match='실행할 수 없습니다'):
        _owned_registry()['sense:lego_probe'].run(None, {})
    with pytest.raises(ValueError, match='잠들어'):
        tool_loader.load_tool_handler('lego_probe')
    assert import_package(payload)['status'] == 'already_owned'
    assert import_package(export_package('lego-probe'))['status'] == 'already_owned'
    path = state.package_path('lego-probe')
    before = (runtime / 'data/ibl_nodes.yaml').read_bytes()
    assert set_package_active('lego-probe', True, authority=HUMAN_AUTHORITY)['success']
    handler = tool_loader.load_tool_handler('lego_probe')
    assert handler.execute({'tool': 'lego_probe'}, {}) == {'items': [{'value': 'ok'}]}
    assert code_is_own('[sense:lego_probe]{}')
    assert set_package_active('lego-probe', False, authority=HUMAN_AUTHORITY)['success']
    assert path.is_dir() and (runtime / 'data/ibl_nodes.yaml').read_bytes() == before
    assert IBLUsageDB().get_stats()['total_examples'] == 1
    assert not code_is_own('[sense:lego_probe]{}')


def test_failed_seed_restores_catalog_and_selection(runtime, monkeypatch):
    import vocabulary_import as receiver
    before = (runtime / 'data/ibl_nodes.yaml').read_bytes()
    selection = state.read_state()['active'].copy()
    def fail(*args):
        raise RuntimeError('seed failure')
    monkeypatch.setattr(receiver, '_seed_examples', fail)
    with pytest.raises(RuntimeError, match='seed failure'):
        receiver.import_package(packet())
    assert (runtime / 'data/ibl_nodes.yaml').read_bytes() == before
    assert state.read_state()['active'] == selection
    assert 'lego-probe' not in state.inventory()['packages']


def test_archive_rejects_tamper_and_path_escape():
    original = zipfile.ZipFile(io.BytesIO(packet()))
    for badname in ('../outside.py', 'handler.py'):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as altered:
            for name in original.namelist():
                altered.writestr(name, b'changed' if name == badname else original.read(name))
            if badname.startswith('..'):
                altered.writestr(badname, b'bad')
        with pytest.raises(ValueError):
            unpack(output.getvalue())



def test_real_cache_reset_updates_catalog_and_gate(runtime, monkeypatch):
    import asyncio
    import ibl_routing, ibl_access, ibl_registry
    from api_ibl import get_actions_catalog
    from vocabulary_import import import_package
    from vocabulary_lifecycle import set_package_active, HUMAN_AUTHORITY
    monkeypatch.setattr(ibl_routing, 'invalidate_runtime_caches', REAL_RESET)
    monkeypatch.setattr(ibl_routing, 'system_capability', lambda name: lambda: None)
    monkeypatch.setattr(ibl_access, '_get_nodes_path', lambda: runtime / 'data/ibl_nodes.yaml')
    import_package(packet())
    assert 'lego_probe' not in asyncio.run(get_actions_catalog())['nodes']['sense']['actions']
    set_package_active('lego-probe', True, authority=HUMAN_AUTHORITY)
    assert 'lego_probe' in asyncio.run(get_actions_catalog())['nodes']['sense']['actions']
    assert 'lego_probe' in ibl_access.build_environment()
    set_package_active('lego-probe', False, authority=HUMAN_AUTHORITY)
    assert 'lego_probe' not in asyncio.run(get_actions_catalog())['nodes']['sense']['actions']
    assert 'lego_probe' not in ibl_access.build_environment()
    assert '잠들어' in ibl_registry.pruned_reason('sense', 'lego_probe')


def test_legacy_manifest_dependencies_do_not_become_package_ids(runtime):
    from vocabulary_lifecycle import check_ready
    # 기존 manifest의 system/optional은 묶음 버전 의존 선언이 아니다.
    assert not any('system' in item or 'optional' in item for item in check_ready('web-builder'))


def test_legacy_text_converts_without_executing_code():
    from vocabulary_archive import convert_legacy
    manifest, files, _ = unpack(packet())
    files['manifest.json'] = b'{"dependencies":{"system":["python"]}}'
    text = '===PACKAGE_START===\nid: lego-probe\n' + ''.join(
        f'===FILE:{name}===\n{content.decode()}\n' for name, content in files.items()) + '===PACKAGE_END==='
    converted, _, examples = unpack(convert_legacy(text))
    assert converted['id'] == manifest['id'] and len(examples) == 1


def test_legacy_examples_are_readable_but_rejected_before_install(runtime, monkeypatch):
    import vocabulary_import as receiver
    payload = packet(edition=1)
    assert unpack(payload)[2][0]['ibl_code'] == '[sense:lego_probe]{}'
    monkeypatch.setattr(receiver, 'read_state', lambda: pytest.fail('mutation boundary entered'))
    with pytest.raises(ValueError, match='EDITION_RETIRED'):
        receiver.import_package(payload)
    assert not (runtime/'data/packages/not_installed/tools/lego-probe').exists()


@pytest.mark.parametrize('source', [
    '[sense:lego_probe]{} >> [table:take]{n:1}',
    '[sense:lego_probe]{q:$x}', '[sense:lego_probe]{q:"$x"}',
])
def test_export_requires_authored_current_examples_for_dynamic_fixtures(source):
    from vocabulary_archive import _current_fixture
    with pytest.raises(ValueError, match='examples.json'):
        _current_fixture(source)

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_invalid_current_example_is_archive_validation_error():
    manifest, files, _ = unpack(packet())
    files['examples.json'] = json.dumps([{
        'intent': '잘못된 현재 문장',
        'ibl_code': '#!ibl edition=2\n[sense:lego_probe]{x:',
    }]).encode()
    with pytest.raises(ValueError, match='IBL 문장'):
        pack(manifest, files)
