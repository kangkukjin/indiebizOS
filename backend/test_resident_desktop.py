"""Desktop profiles remain owner data and never become arbitrary launch commands."""
import boot_paths
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_resident_pcs
import resident_desktop as desktop


@pytest.fixture
def registry(tmp_path, monkeypatch):
    records = {
        'a': {'device_id': 'a', 'registration': {'state': 'active'}},
        'b': {'device_id': 'b', 'registration': {'state': 'active', 'paused': True}},
        'removed': {'device_id': 'removed', 'registration': {'state': 'removed'}},
        'revoked': {'device_id': 'revoked', 'registration': {'state': 'active'}, 'revoked': True},
    }
    monkeypatch.setattr(desktop, '_path', lambda: tmp_path / 'desktop.json')
    monkeypatch.setattr(desktop.resident_pcs, 'resolve', lambda target, **_: records[target])
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    return TestClient(app)


def test_profiles_are_per_device_persisted_and_independent_of_helper_pause(registry):
    profile = {'direct_host': 'Mac.local', 'tunnel_host': 'remote.example.com', 'port': 5900}
    assert registry.put('/remote-pcs/desktop/a', json=profile).status_code == 200
    assert registry.get('/remote-pcs/desktop/a').json()['direct_host'] == 'mac.local'
    assert registry.get('/remote-pcs/desktop/b').json()['direct_host'] == ''
    assert registry.put('/remote-pcs/desktop/b', json={'direct_host': '::1'}).status_code == 200
    assert registry.put('/remote-pcs/desktop/a', json={}).json()['tunnel_host'] == ''


@pytest.mark.parametrize('value', [
    {'direct_host': 'vnc://mac.local'}, {'direct_host': 'user:password@mac.local'},
    {'direct_host': '--help'}, {'direct_host': 'mac.local\n--url'},
    {'direct_host': 'mac.local/path'}, {'direct_host': None},
    {'tunnel_host': '127.0.0.1'}, {'tunnel_host': '::1'},
    {'port': True}, {'port': 0}, {'port': 65536}, {'port': '5900'},
    {'password': 'do-not-save'},
])
def test_unsafe_or_secret_profile_rejected_without_overwriting(registry, value):
    desktop.save('a', {'direct_host': 'mac.local'})
    assert registry.put('/remote-pcs/desktop/a', json=value).status_code == 400
    assert desktop.get('a')['direct_host'] == 'mac.local'


@pytest.mark.parametrize('device', ['removed', 'revoked', 'missing'])
def test_closed_registration_cannot_save_or_launch(registry, device):
    assert registry.get('/remote-pcs/desktop/' + device).status_code == 400
    assert registry.put('/remote-pcs/desktop/' + device, json={}).status_code == 400


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
