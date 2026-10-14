"""Real resident HTTP transfer protocol to/from an isolated phone workspace."""
import boot_paths  # noqa: F401
import hashlib
import threading
import pytest
import resident_pcs as pcs
import phone_limb_transfer as transfer
from test_limb_client import hub, phone_env, _client, _enroll_phone  # noqa: F401


def test_phone_binary_roundtrip_and_no_clobber(hub, phone_env, tmp_path):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: {})
    data = bytes(range(256)) * 4500
    sha = hashlib.sha256(data).hexdigest()
    row = pcs.transfer_create(rec['device_id'], 'to_pc', 'blob', len(data), sha)
    pcs.transfer_write(row['id'], 0, data[:1024 * 1024])
    pcs.transfer_write(row['id'], 1024 * 1024, data[1024 * 1024:])
    pcs.transfer_commit(row['id'])
    target = phone_env / 'remote_work/blob.bin'
    target.parent.mkdir()
    partial = target.parent / ('.indiebiz-' + row['id'] + '.part')
    partial.write_bytes(data[:12345])  # Resume from a previous interrupted download.
    command = {'transfer_id': row['id'], 'path': 'blob.bin'}
    result = transfer.execute(c, command, threading.Event())
    assert target.read_bytes() == data and result['sha256'] == sha
    assert transfer.execute(c, command, threading.Event())['success']
    target.write_bytes(b'existing')
    with pytest.raises(ValueError, match='destination_exists'):
        transfer.execute(c, command, threading.Event())
    target.write_bytes(data)
    upload = pcs.transfer_create(rec['device_id'], 'from_pc', 'return.bin')
    pcs.transfer_meta(upload['id'], len(data), sha)
    pcs.transfer_write(upload['id'], 0, data[:12345])
    result = transfer.execute(c, {'transfer_id': upload['id'], 'path': str(target)}, threading.Event())
    assert result['sha256'] == sha and pcs.transfer_path(upload['id']).read_bytes() == data


def test_cancel_prevents_transfer_io(hub, phone_env):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: {})
    event = threading.Event()
    event.set()
    with pytest.raises(InterruptedError):
        transfer.execute(c, {'transfer_id': 'a' * 32, 'path': 'x'}, event)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
