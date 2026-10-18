"""Network appliances share discovery, not PC execution credentials."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import hardware_registry as hardware
import limb_keys

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setattr(limb_keys, '_cache_mtime', None)


def register(**kw):
    return hardware.register('screen', {'ip': '192.0.2.10', 'token': 'private-token',
                             'apps': {'youtube': '123'}}, **kw)


def test_public_rows_never_include_private_connection_or_pc_credentials():
    row = register()
    public = json.dumps(hardware.devices())
    assert all(value not in public for value in ('192.0.2.10', 'private-token', 'connection', 'installation_id'))
    assert row['connected'] is None
    assert row['registration']['adapter'] == 'network-api'
    assert limb_keys.list_keys() == []
    assert hardware.connection(row['device_id'])['connection']['token'] == 'private-token'
    assert hardware._store_path().stat().st_mode & 0o777 == 0o600
    limb_keys.invalidate()
    assert hardware.devices() == [row]


def test_paused_removed_and_ambiguous_targets_never_execute():
    row = register()
    hardware.update(row['device_id'], paused=True)
    with pytest.raises(PermissionError):
        hardware.connection(row['device_id'])
    hardware.update(row['device_id'], paused=False)
    limb_keys.mint('screen')
    with pytest.raises(ValueError, match='중복'):
        hardware.connection('screen')
    assert hardware.connection(row['device_id'])
    hardware.update(row['device_id'], remove=True)
    with pytest.raises(PermissionError):
        hardware.connection(row['device_id'])
    with pytest.raises(PermissionError):
        hardware.save_token(row['device_id'], 'late-token')
    assert 'private-token' not in hardware._store_path().read_text()


@pytest.mark.parametrize('cfg', [
    {'ip': 'https://192.0.2.1'}, {'ip': '127.0.0.1'}, {'ip': '0.0.0.0'},
    {'ip': '192.0.2.1', 'token': 'abc&token=other'},
    {'ip': '192.0.2.1', 'mac': 'invalid'}, {'ip': '192.0.2.1', 'pc_input_index': True},
    {'ip': '192.0.2.1', 'apps': {'youtube': '../bad'}},
])
def test_bad_connection_is_rejected_before_persistence(cfg):
    with pytest.raises(ValueError):
        hardware.register('screen', cfg)
    assert not hardware._store_path().exists()


def test_duplicate_address_and_update_preserve_token():
    row = register()
    with pytest.raises(ValueError, match='이미 등록'):
        register()
    hardware.register('new name', {'ip': '192.0.2.11'}, target=row['device_id'])
    assert hardware.connection(row['device_id'])['connection']['token'] == 'private-token'


def test_observation_expires_and_is_not_power_state(monkeypatch):
    row = register()
    hardware.observe(row['device_id'], False)
    assert hardware.devices()[0]['connected'] is False
    now = hardware.time.time()
    monkeypatch.setattr(hardware.time, 'time', lambda: now + 91)
    assert hardware.devices()[0]['connected'] is None


def test_owner_api_and_existing_management_operations(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_resident_pcs
    import resident_pcs
    monkeypatch.setattr(resident_pcs, 'usb_status', lambda: {})
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        result = client.post('/remote-pcs/hardware', json={
            'alias': 'screen', 'connection': {'ip': '192.0.2.10', 'token': 'secret'}})
        assert result.status_code == 200
        did = result.json()['device_id']
        assert 'secret' not in client.get('/remote-pcs').text
        assert client.post('/remote-pcs/state', json={'target': did, 'paused': True}).status_code == 200
        assert client.put('/remote-pcs/context', json={'target': did, 'context': 'room'}).status_code == 200
        with pytest.raises(PermissionError):
            hardware.connection(did)
        assert client.post('/remote-pcs/state', json={'target': did, 'remove': True}).status_code == 200
        assert hardware.devices()[0]['revoked']


def test_prompt_contains_guide_even_without_heartbeat_or_description(monkeypatch):
    import associative_recall as recall
    import device_registry
    row = register()
    monkeypatch.setattr(device_registry, 'live_with_capability', lambda _: [])
    block = recall._connected_limbs(recall.RecallRequest(None, 'TV', []), None)
    item = ET.fromstring(block.text).find('limb')
    assert item.attrib['device_id'] == row['device_id']
    assert item.attrib['connected'] == 'unknown'
    assert item.attrib['control_guide'] == 'tv_control.md'
    assert 'private-token' not in block.text and '192.0.2.10' not in block.text
    hardware.update(row['device_id'], remove=True)
    assert recall._connected_limbs(recall.RecallRequest(None, 'TV', []), None) is None


def test_limb_list_and_guestpc_rejection(monkeypatch):
    import device_registry
    spec = importlib.util.spec_from_file_location('hardware_guest_handler', ROOT / 'data/packages/installed/tools/guest-helper/handler.py')
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    monkeypatch.setattr(device_registry, 'live_with_capability', lambda _: [])
    monkeypatch.setattr(handler, '_issue_root', lambda: str(ROOT))
    monkeypatch.setattr(handler, '_issue_parent', lambda: 'unused')
    row = register()
    assert handler._limb_list({})['items'][0]['device_id'] == row['device_id']
    assert handler._resolve_limb(row['device_id'])[2]
    assert handler._limb_approve({'target': row['device_id'], 'approved': False})['success']
    assert handler._limb_revoke({'target': row['device_id']})['success']


def test_process_writes_preserve_each_other_and_pc_credentials(tmp_path):
    import os
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    pc = limb_keys.mint('pc')
    original = limb_keys._store_path().read_bytes()
    source = "import sys; sys.path.insert(0, 'backend'); import boot_paths, hardware_registry; hardware_registry.register(sys.argv[1], {'ip': sys.argv[2]})"
    env = {**os.environ, 'INDIEBIZ_USERDATA': str(tmp_path)}
    def create(i):
        return subprocess.run([sys.executable, '-c', source, f'tv-{i}', f'192.0.2.{i}'],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    import sys
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(create, range(1, 5)))
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert len(hardware.devices()) == 4
    assert limb_keys._store_path().read_bytes() == original
    assert limb_keys.get_by_device(pc['device_id'])


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
