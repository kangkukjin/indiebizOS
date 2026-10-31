"""Bounded durable batches. Per-transfer OS locks, never a DB lock during file IO."""
import hashlib
import os

from filelock import FileLock

import phone_jobs
import resident_pcs as pcs

BATCH = 1024 * 1024


def lock(tid):
    return FileLock(str(pcs.transfer_path(tid)) + '.lock', timeout=30)


def sync_directory(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write(tid, offset, data):
    if not isinstance(data, bytes) or not 0 < len(data) <= BATCH:
        raise ValueError('chunk_too_large')
    if type(offset) is not int or offset < 0:
        raise ValueError('offset_conflict')
    with lock(tid):
        row = pcs.transfer_info(tid)
        if row['state'] == 'committed' or row['size'] is None:
            raise ValueError('transfer_not_writable')
        path = pcs.transfer_path(tid, True)
        if (path.stat().st_size if path.exists() else 0) < row['offset']:
            raise ValueError('durable_data_missing')
        if offset < row['offset'] and offset + len(data) <= row['offset']:
            with path.open('rb') as stream:
                stream.seek(offset)
                if stream.read(len(data)) == data:
                    return {'offset': offset + len(data)}
            raise ValueError('offset_conflict')
        if offset != row['offset'] or offset + len(data) > row['size']:
            raise ValueError('offset_conflict')
        with path.open('r+b' if path.exists() else 'w+b') as stream:
            os.chmod(path, 0o600)
            stream.seek(offset)
            stream.write(data)
            stream.truncate()  # discard only the unacknowledged crash tail
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(path.parent)
        with phone_jobs._db() as db:
            db.execute("UPDATE resident_transfers SET offset=?,state='transferring' WHERE id=?",
                       (offset + len(data), tid))
        return {'offset': offset + len(data)}


def commit(tid):
    with lock(tid):
        row = pcs.transfer_info(tid)
        if row['state'] == 'committed':
            return row
        if row['size'] != row['offset']:
            raise ValueError('transfer_incomplete')
        path = pcs.transfer_path(tid, True)
        if row['size'] == 0 and not pcs.transfer_path(tid).exists():
            path.touch(mode=0o600, exist_ok=True)
        source = path if path.exists() else pcs.transfer_path(tid)
        digest = hashlib.sha256()
        with source.open('r+b') as stream:
            # Never certify a tail that was not committed in the progress ledger.
            if os.fstat(stream.fileno()).st_size != row['size']:
                raise ValueError('file_size_conflict')
            for chunk in iter(lambda: stream.read(BATCH), b''):
                digest.update(chunk)
            if digest.hexdigest() != row['sha256']:
                raise ValueError('hash_mismatch')
            os.fsync(stream.fileno())
        if source == path:
            os.replace(path, pcs.transfer_path(tid))
        sync_directory(source.parent)
        with phone_jobs._db() as db:
            db.execute("UPDATE resident_transfers SET state='committed' WHERE id=?", (tid,))
        return pcs.transfer_info(tid)


def read(tid, offset, size=BATCH):
    row = pcs.transfer_info(tid)
    if row['state'] != 'committed':
        raise ValueError('transfer_not_committed')
    if type(offset) is not int or not 0 <= offset <= row['size']:
        raise ValueError('invalid_offset')
    if type(size) is not int or not 1 <= size <= BATCH:
        raise ValueError('invalid_chunk_size')
    with pcs.transfer_path(tid).open('rb') as stream:
        stream.seek(offset)
        return stream.read(size)


def authorize(tid, key, installation):
    import limb_keys
    rec = limb_keys.resident_auth(key, installation)
    row = pcs.transfer_info(tid)
    if row['device'] != rec['device_id']:
        raise ValueError('transfer_not_owned')
    # A cancelled command cannot keep writing through an already-open socket.
    with phone_jobs._db() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='resident_tasks'").fetchone()
        if exists:
            import json
            tasks = db.execute('SELECT summary,cancel_requested,state FROM resident_tasks '
                               'WHERE device=? ORDER BY created DESC', (rec['device_id'],)).fetchall()
            for task in tasks:
                if json.loads(task['summary']).get('transfer_id') == tid:
                    if task['cancel_requested'] or task['state'] == 'cancelled':
                        raise ValueError('transfer_cancelled')
                    break
    return row
