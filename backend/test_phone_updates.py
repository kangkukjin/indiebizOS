"""Authenticated APK transport, update authority, version and completion contracts."""
import boot_paths  # noqa: F401
import hashlib
import importlib.util
import json
from pathlib import Path
import threading

import pytest
import limb_keys
import phone_updates as updates
import resident_pcs as pcs
import resident_store
from test_limb_client import hub, phone_env, _client, _enroll_phone  # noqa: F401


@pytest.fixture
def release(hub, phone_env, monkeypatch, tmp_path):
    root = tmp_path / 'releases'
    monkeypatch.setattr(updates, 'releases_root', lambda: root)
    data = bytes(range(256)) * 4500
    manifest = {'package': updates.PACKAGE, 'abi': 'arm64-v8a', 'version_code': 3,
                'version_name': '0.3', 'min_sdk': 28, 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'signer_sha256': 'a' * 64}
    directory = root / manifest['abi']
    directory.mkdir(parents=True)
    (directory / (manifest['sha256'] + '.apk')).write_bytes(data)
    (directory / 'current.json').write_text(json.dumps(manifest))
    return manifest, data


class Native:
    def __init__(self):
        self.calls = []
        self.caps = {'contract': 1, 'abi': 'arm64-v8a', 'sdk': 34, 'version_code': 2,
                     'signer_sha256': 'a' * 64, 'installed_sha256': 'b' * 64, 'can_install': True}

    def capabilities(self):
        return json.dumps(self.caps)

    def install(self, path, manifest, jid):
        self.calls.append((path, json.loads(manifest), jid))
        self.caps['attempt'] = {'job_id': jid, 'sha256': json.loads(manifest)['sha256'], 'state': 'installing'}
        return json.dumps({'success': True, 'accepted': True})


@pytest.fixture
def device(release, hub, monkeypatch):
    # The in-process HTTP adapter exercises legacy APK transport; binary sockets
    # have their own real server/consumer contract in test_resident_transfer_io.
    import api_resident_transfer
    monkeypatch.setattr(api_resident_transfer, 'offer', lambda: {})
    native = Native()
    monkeypatch.setattr(updates, '_bridge_factory', lambda: native)
    rec = _enroll_phone()
    client = _client(hub, rec, lambda *args: {'success': True})
    client.step(inline=True, wait=0)
    return rec, client, native


def test_real_authenticated_chunks_and_reconnect_completion(release, device):
    manifest, data = release
    rec, client, native = device
    target = rec['device_id']
    assert updates.status(pcs.resolve(target))['state'] == 'available'
    receipt = updates.submit(target)
    assert updates.submit(target)['job_id'] == receipt['job_id']
    client.step(inline=True, wait=0)
    client.step(inline=True, wait=0)
    assert len(native.calls) == 1
    assert Path(native.calls[0][0]).read_bytes() == data
    assert resident_store.history(job=receipt['job_id'])['tasks'][0]['result']['accepted']
    assert updates.status(pcs.resolve(target))['state'] == 'installing'  # accepted != installed
    native.caps.update(installed_sha256=manifest['sha256'], version_code=3)
    native.caps['attempt']['state'] = 'installed'
    client.step(inline=True, wait=0)
    assert updates.status(pcs.resolve(target))['state'] == 'current'


def test_ordinary_command_cannot_request_update(device, hub):
    rec, _, _ = device
    response = hub.post('/remote-pcs/command', json={'target': rec['device_id'], 'command': {'op': 'phone_update'}})
    assert response.status_code == 400
    assert 'unsupported_on_this_body' in response.text


@pytest.mark.parametrize('change,state', [({'signer_sha256': 'c' * 64}, 'incompatible'),
    ({'version_code': 3}, 'different_build'), ({'sdk': 27}, 'incompatible'),
    ({'abi': 'x86'}, 'unpublished'), ({'contract': 0}, 'bootstrap')])
def test_incompatible_or_legacy_never_enqueued(device, change, state):
    rec, client, native = device
    native.caps.update(change)
    client.step(inline=True, wait=0)
    assert updates.status(pcs.resolve(rec['device_id']))['state'] == state
    with pytest.raises(ValueError):
        updates.submit(rec['device_id'])
    assert not resident_store.pending(rec['device_id'], 'phone_update')


def test_newer_installed_apk_is_not_incompatible_or_downgraded(device, release):
    rec, client, native = device
    native.caps.update(version_code=4, version_name='0.4')
    client.step(inline=True, wait=0)
    status = updates.status(pcs.resolve(rec['device_id']))
    assert status['state'] == 'ahead'
    assert status['current_version_name'] == '0.4'
    assert status['latest_version_name'] == '0.3'
    assert updates.submit(rec['device_id'])['state'] == 'ahead'
    assert not resident_store.pending(rec['device_id'], 'phone_update')
    assert not native.calls
    # A higher version must not hide an unrelated signing-key mismatch.
    native.caps['signer_sha256'] = 'c' * 64
    client.step(inline=True, wait=0)
    assert updates.status(pcs.resolve(rec['device_id']))['state'] == 'incompatible'


def test_tampered_published_bytes_rejected(release, device):
    manifest, _ = release
    rec, _, _ = device
    path = updates.releases_root() / manifest['abi'] / (manifest['sha256'] + '.apk')
    path.write_bytes(b'x' * manifest['size'])
    with pytest.raises(ValueError, match='hash_mismatch'):
        updates.submit(rec['device_id'])


def test_waiting_for_android_confirmation_is_visible_and_not_duplicated(release, device):
    manifest, _ = release
    rec, client, native = device
    native.caps['attempt'] = {'sha256': manifest['sha256'], 'state': 'awaiting_confirmation'}
    client.step(inline=True, wait=0)
    assert updates.submit(rec['device_id'])['state'] == 'awaiting_confirmation'
    assert not resident_store.pending(rec['device_id'], 'phone_update')


@pytest.mark.parametrize('state', ['staged', 'installing', 'awaiting_permission', 'awaiting_confirmation'])
def test_new_publication_cannot_hide_or_duplicate_an_older_android_install(release, device, state):
    manifest, _ = release
    rec, client, native = device
    native.caps['attempt'] = {'sha256': 'd' * 64, 'state': state,
                              'release': {'version_code': 2}, 'message': '기존 설치 진행 중'}
    client.step(inline=True, wait=0)
    result = updates.submit(rec['device_id'])
    assert result['state'] == state
    assert result['installing_version'] == 2
    assert result['latest_version'] == manifest['version_code']
    assert not resident_store.pending(rec['device_id'], 'phone_update')
    assert not native.calls


def test_interrupted_caller_recovers_native_receipt_and_blocks_other_work(device):
    rec, client, native = device
    receipt = updates.submit(rec['device_id'])
    client.step(inline=True, wait=0)
    job = json.loads(client._record_path(receipt['job_id']).read_text())['job']
    client._record(receipt['job_id'], state='running')
    # Remove the simulated old result event, as a real process killed before return would have none.
    for path in (client.spool / 'events').glob('*.json'):
        if json.loads(path.read_text())['kind'] == 'result':
            path.unlink()
    client._recover()
    recovered = json.loads(client._record_path(receipt['job_id']).read_text())['result']
    assert recovered['accepted'] and recovered['installation']['state'] == 'installing'
    assert len(native.calls) == 1
    assert updates.recovered({'id': 'other'})['unknown']


def test_cancelled_download_never_calls_installer(device, release):
    rec, client, native = device
    receipt = updates.submit(rec['device_id'])
    jobs = pcs.sync(rec['key'], rec['registration']['installation_id'])['jobs']
    job = next(j for j in jobs if j['id'] == receipt['job_id'])
    stop = threading.Event(); stop.set()
    with pytest.raises(InterruptedError):
        updates.execute(client, job, json.loads(job['code']), stop)
    assert not native.calls


def test_controls_wait_while_apk_downloads(device, monkeypatch):
    _, client, native = device
    entered, release = threading.Event(), threading.Event()

    def download(*args):
        entered.set()
        assert release.wait(3)
        return {'success': True, 'accepted': True}

    monkeypatch.setattr(updates, 'execute', download)
    worker = threading.Thread(target=client._dispatch, args=({'id': 'update', 'code': '{"op":"phone_update"}'},))
    worker.start()
    try:
        assert entered.wait(3)
        job = {'id': 'info', 'code': '{"op":"info"}'}
        client._accept(job)
        client._schedule(inline=True)
        assert client._queue == [job]
        assert not client._controls
    finally:
        release.set(); worker.join(3)
    client._schedule(inline=True)
    assert not client._queue


def test_member_authority_cannot_update(device, monkeypatch):
    import principal
    monkeypatch.setattr(principal, 'is_owner', lambda: False)
    with pytest.raises(PermissionError):
        updates.submit(device[0]['device_id'])


def test_publisher_keeps_immutable_apk_and_rejects_downgrade(release, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('publish_phone_update', Path(__file__).parents[1] / 'scripts/publish_phone_update.py')
    publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)
    manifest, data = release
    source = tmp_path / 'app.apk'; source.write_bytes(data + b'new')
    newer = {**manifest, 'version_code': 4, 'size': source.stat().st_size, 'sha256': updates.digest(source)}
    monkeypatch.setattr(publisher, 'inspect_apk', lambda *args: newer)
    assert publisher.publish(source, '/sdk')['version_code'] == 4
    assert (updates.releases_root() / manifest['abi'] / (manifest['sha256'] + '.apk')).exists()
    monkeypatch.setattr(publisher, 'inspect_apk', lambda *args: manifest)
    with pytest.raises(ValueError, match='version_must_increase'):
        publisher.publish(source, '/sdk')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
