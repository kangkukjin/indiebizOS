"""Durable binary batches, cross-client protocol and crash reconciliation."""
import boot_paths
import contextlib
import hashlib
import json
import struct
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_resident_pcs
import api_resident_transfer
import phone_jobs
import resident_pcs as pcs
import resident_transfer_io as io
from phone_transfer_wire import PhoneTransferWire
from test_resident_pcs import registry


def row(rec, data=b'payload', direction='from_pc'):
    return pcs.transfer_create(rec['device_id'], direction, 'probe.bin', len(data), hashlib.sha256(data).hexdigest())


def test_crash_after_file_sync_before_ledger_commit(registry, monkeypatch):
    rec = registry()
    tid = row(rec)['id']
    original = phone_jobs._db

    class Crash:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            if "SET offset=" in sql:
                raise RuntimeError('simulated_crash')
            return self.db.execute(sql, *args)

    @contextlib.contextmanager
    def crash_db():
        with original() as db:
            yield Crash(db)

    with monkeypatch.context() as patch:
        patch.setattr(phone_jobs, '_db', crash_db)
        with pytest.raises(RuntimeError, match='simulated_crash'):
            io.write(tid, 0, b'payload')
    assert pcs.transfer_info(tid)['offset'] == 0
    assert pcs.transfer_path(tid, True).read_bytes() == b'payload'
    assert io.write(tid, 0, b'pay') == {'offset': 3}
    assert pcs.transfer_path(tid, True).read_bytes() == b'pay'
    io.write(tid, 3, b'load')
    assert io.commit(tid)['state'] == 'committed'


def test_lost_ack_concurrent_conflict_and_missing_durable_bytes(registry):
    tid = row(registry())['id']
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: io.write(tid, 0, b'pay'), range(2))) == [{'offset': 3}] * 2
    with pytest.raises(ValueError, match='offset_conflict'):
        io.write(tid, 0, b'bad')
    pcs.transfer_path(tid, True).write_bytes(b'p')
    with pytest.raises(ValueError, match='durable_data_missing'):
        io.write(tid, 3, b'load')


def test_commit_recovery_after_atomic_rename_and_no_db_lock_during_hash(registry, monkeypatch):
    tid = row(registry())['id']
    io.write(tid, 0, b'payload')
    pcs.transfer_path(tid, True).replace(pcs.transfer_path(tid))
    assert io.commit(tid)['state'] == 'committed'
    assert io.commit(tid)['state'] == 'committed'


@pytest.mark.parametrize('size', [0, 1, io.BATCH - 1, io.BATCH, io.BATCH + 1])
def test_binary_protocol_roundtrip_and_direction(registry, monkeypatch, size):
    rec = registry()
    monkeypatch.setattr(api_resident_transfer.lan, 'offer', lambda *a, **k: {})
    data = bytes(range(251)) * (size // 251) + bytes(range(size % 251))
    uploaded = row(rec, data)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    auth = {'key': rec['key'], 'installation_id': rec['registration']['installation_id']}
    with TestClient(app) as client:
        with client.websocket_connect('/limb/resident/transfer/' + uploaded['id']) as ws:
            ws.send_json(auth)
            assert ws.receive_json()['version'] == 1
            for offset in range(0, size, io.BATCH):
                block = data[offset:offset + io.BATCH]
                ws.send_bytes(struct.pack('!Q', offset) + block)
                assert ws.receive_json()['offset'] == offset + len(block)
                # An acknowledgement lost on the wire does not append duplicate bytes.
                ws.send_bytes(struct.pack('!Q', offset) + block)
                assert ws.receive_json()['offset'] == offset + len(block)
            ws.send_json({'action': 'commit'})
            assert ws.receive_json()['state'] == 'committed'
            ws.send_json({'action': 'read', 'offset': 0})
            assert ws.receive_json()['error'] == 'transfer_wrong_direction'
        assert pcs.transfer_path(uploaded['id']).read_bytes() == data


def test_phone_consumes_actual_binary_server_and_closes(registry, monkeypatch):
    rec = registry()
    data = b'phone\x00' * 120000
    down = row(rec, data, 'to_pc')
    io.write(down['id'], 0, data)
    io.commit(down['id'])
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    auth = {'key': rec['key'], 'installation_id': rec['registration']['installation_id']}
    monkeypatch.setattr(api_resident_transfer.lan, 'offer', lambda *a, **k: {})
    with TestClient(app) as client:
        class Client:
            def _auth(self):
                return auth

            def _post(self, path, payload, timeout):
                return client.post('/limb/resident/' + path, json=payload).json()

        class Socket:
            def __init__(self, tid):
                self.manager = client.websocket_connect('/limb/resident/transfer/' + tid)
                self.ws = self.manager.__enter__()
                self.ws.send_json(auth)
                assert self.ws.receive_json()['type'] == 'ready'

            def settimeout(self, value):
                pass

            def send(self, value):
                self.ws.send_text(value)

            def send_binary(self, value):
                self.ws.send_bytes(value)

            def recv(self):
                msg = self.ws.receive()
                return msg.get('bytes') if msg.get('bytes') is not None else msg['text']

            def close(self):
                self.manager.__exit__(None, None, None)

        monkeypatch.setattr(PhoneTransferWire, '_open', lambda wire: setattr(wire, 'socket', Socket(wire.tid)))
        for direction in ('to_pc', 'from_pc'):
            tid = down['id'] if direction == 'to_pc' else row(rec, data)['id']
            wire = PhoneTransferWire(Client(), tid, lambda: 30)
            assert wire.request('info')['binary']['version'] == 1
            if direction == 'to_pc':
                assert wire.request('read', offset=3, chunk_size=512 * 1024)['data'] == data[3:3 + 512 * 1024]
            else:
                assert wire.request('write', offset=0, data=data)['offset'] == len(data)
                assert wire.request('commit')['state'] == 'committed'
            wire.close()
            assert wire.socket is None


def test_binary_rejects_other_device_revocation_and_cancel(registry):
    import limb_keys
    import resident_store
    a, b = registry('a'), registry('b')
    tid = row(a)['id']
    with pytest.raises(ValueError, match='not_owned'):
        io.authorize(tid, b['key'], b['registration']['installation_id'])
    task = pcs.submit(a['device_id'], {'op': 'transfer', 'transfer_id': tid, 'path': 'probe.bin'})
    resident_store.cancel(task['job_id'])
    with pytest.raises(ValueError, match='transfer_cancelled'):
        io.authorize(tid, a['key'], a['registration']['installation_id'])
    limb_keys.revoke(a['device_id'])
    with pytest.raises(ValueError):
        io.authorize(tid, a['key'], a['registration']['installation_id'])


def test_phone_network_fallback_preserves_batch_and_auth_errors(monkeypatch):
    import base64
    calls = []

    class Client:
        def _auth(self):
            return {'key': 'test', 'installation_id': 'test'}

        def _post(self, path, payload, timeout):
            calls.append(payload)
            return {'offset': 10}

    def fail(wire):
        raise OSError('websocket_unavailable')

    wire = PhoneTransferWire(Client(), 'a' * 32, lambda: 30)
    wire.offer = {'version': 1}
    monkeypatch.setattr(PhoneTransferWire, '_open', fail)
    assert wire.request('write', offset=3, data=b'payload')['offset'] == 10
    assert calls[0]['offset'] == 3
    assert base64.b64decode(calls[0]['data']) == b'payload'
    assert wire.route == 'https-fallback'

    def denied(wire):
        raise ValueError('transfer_not_owned')

    wire.offer = {'version': 1}
    monkeypatch.setattr(PhoneTransferWire, '_open', denied)
    with pytest.raises(ValueError, match='not_owned'):
        wire.request('write', offset=3, data=b'payload')
    assert len(calls) == 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
