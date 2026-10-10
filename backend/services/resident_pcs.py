"""Owner-facing resident PC operations. Transport authenticates separately."""
import hashlib
import ipaddress
import json
import os
import re
import socket
import time
import uuid
from pathlib import Path

import device_registry
import limb_keys
import phone_jobs
import resident_store


def resolve(target, active=True):
    rows = [r for r in limb_keys.list_keys() if r.get("registration") and
            (r["device_id"] == target or r["alias"] == target)]
    if len(rows) != 1:
        raise ValueError("PC 이름이 없거나 중복입니다. device_id로 지정하세요")
    rec = limb_keys.get_by_device(rows[0]["device_id"])
    if active:
        limb_keys.resident_auth(rec["key"], rec["registration"]["installation_id"])
    return rec


def devices():
    now = time.time()
    return [{**r, "connected": r["registration"]["state"] != "removed" and now - (r["registration"].get("last_seen") or 0) < 90}
            for r in limb_keys.list_keys() if r.get("registration")]


def submit(target, command, request_id=None):
    rec = resolve(target)
    allowed = {"shell", "read", "write", "list", "info", "screen", "click", "move", "type",
               "key", "scroll", "drag", "transfer", "media", "wake"}
    op = command.get("op", "shell")
    if op not in allowed:
        raise ValueError("unsupported_resident_operation")
    if op in {"screen", "click", "move", "type", "key", "scroll", "drag"} and command.get("mode") != "interactive":
        raise ValueError("needs_interactive")
    if not isinstance(command.get("timeout", 1800), int) or not 1 <= command.get("timeout", 1800) <= 86400:
        raise ValueError("timeout must be 1..86400")
    command = {**command, "op": op, "mode": command.get("mode", "background")}
    if len(json.dumps(command).encode()) > 256 * 1024:
        raise ValueError("command_too_large_use_transfer")
    with limb_keys._lock:
        rec = limb_keys.resident_auth(rec["key"], rec["registration"]["installation_id"])
        jid = resident_store.submit(rec, command, request_id or uuid.uuid4().hex)
    import task_receipts
    return task_receipts.receipt("guestpc", jid, state=task_receipts.QUEUED,
                                 limb=rec["device_id"], job_id=jid, accepted=True)


def remove(target):
    rec = resolve(target, active=False)
    if rec["registration"]["state"] == "removed":
        return rec["registration"]
    out = limb_keys.resident_update(rec["device_id"], state="removal_pending")
    with phone_jobs._db() as db:
        resident_store.schema(db)
        pending = [row[0] for row in db.execute("SELECT id FROM resident_tasks WHERE device=? AND result IS NULL", (rec["device_id"],))]
    for jid in pending:
        resident_store.cancel(jid, rec["device_id"])
    phone_jobs._wake()
    return out


def sync(key, installation_id, events=None, capabilities=None, wait=0):
    rec = limb_keys.resident_auth(key, installation_id, cleanup=True)
    ack = resident_store.observe(rec, events or [])
    updates = {"last_seen": time.time()}
    if capabilities is not None:
        if len(json.dumps(capabilities).encode()) > 16384:
            raise ValueError("capabilities_too_large")
        updates["capabilities"] = capabilities
    public = limb_keys.resident_update(rec["device_id"], **updates)
    device_registry.register(rec["device_id"], rec["alias"], [limb_keys.GUEST_PC_CLASS], "",
                             auth="limb_key", owner="self", primary=False)
    reg = public["registration"]
    jobs = []
    if reg["state"] == "active" and not reg.get("paused"):
        jobs = phone_jobs.pull_blocking(rec["device_id"], min(20, max(0, wait)))
        # Recheck after long poll: a removal during wait cannot deliver new work.
        latest = limb_keys.resident_auth(key, installation_id, cleanup=True)["registration"]
        if latest["state"] != "active" or latest.get("paused"):
            for j in jobs:
                resident_store.cancel(j["id"], rec["device_id"])
            jobs = []
        reg = latest
    return {"success": True, "ack": ack, "jobs": jobs, "generation": reg["generation"],
            "state": reg["state"], "paused": reg.get("paused", False),
            "cancel": resident_store.cancellations(rec["device_id"])}


def configure_wake(target, mac, broadcast, relay):
    rec = resolve(target)
    compact = re.sub(r"[:-]", "", mac)
    if not re.fullmatch(r"[0-9a-fA-F]{12}", compact):
        raise ValueError("invalid_mac")
    ipaddress.IPv4Address(broadcast)
    if relay != "central":
        relay = resolve(relay)["device_id"]
    return limb_keys.resident_update(rec["device_id"], wake={"mac": compact, "broadcast": broadcast,
                                                             "relay": relay, "tested": False})


def wake(target):
    rec = resolve(target)
    route = rec["registration"].get("wake")
    if not route:
        raise ValueError("wake_route_not_configured")
    if route["relay"] == "central":
        packet = b"\xff" * 6 + bytes.fromhex(route["mac"]) * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (route["broadcast"], 9))
        return {"success": True, "state": "signal_sent", "ready": False}
    return submit(route["relay"], {"op": "wake", "mac": route["mac"], "broadcast": route["broadcast"]})


def files_root():
    return phone_jobs._db_path().parent / "resident_files"


def transfer_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS resident_transfers (
        id TEXT PRIMARY KEY, device TEXT NOT NULL, direction TEXT NOT NULL,
        name TEXT NOT NULL, size INTEGER, sha256 TEXT, offset INTEGER NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL)""")


def transfer_create(target, direction, name, size=None, sha256=None):
    rec = resolve(target)
    if direction not in {"to_pc", "from_pc"}:
        raise ValueError("invalid_direction")
    if not name or len(name) > 255 or any(c in name for c in ("/", "\\", "\0")) or name in {".", ".."}:
        raise ValueError("invalid_filename")
    if size is not None or sha256 is not None:
        if not isinstance(size, int) or size < 0 or not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256 or ""):
            raise ValueError("invalid_file_metadata")
    tid = uuid.uuid4().hex
    with phone_jobs._db() as db:
        transfer_schema(db)
        db.execute("INSERT INTO resident_transfers(id,device,direction,name,size,sha256,created) VALUES(?,?,?,?,?,?,?)",
                   (tid, rec["device_id"], direction, name, size, sha256, time.time()))
    return transfer_info(tid)


def transfer_path(tid, partial=False):
    if not re.fullmatch(r"[a-f0-9]{32}", tid):
        raise ValueError("invalid_transfer")
    root = files_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root / (tid + (".part" if partial else ".blob"))


def transfer_info(tid):
    with phone_jobs._db() as db:
        transfer_schema(db)
        row = db.execute("SELECT * FROM resident_transfers WHERE id=?", (tid,)).fetchone()
        if not row:
            raise ValueError("transfer_not_found")
        return dict(row)


def transfer_meta(tid, size, sha256):
    if not isinstance(size, int) or size < 0 or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("invalid_file_metadata")
    with phone_jobs._db() as db:
        transfer_schema(db)
        row = db.execute("SELECT * FROM resident_transfers WHERE id=?", (tid,)).fetchone()
        if not row or (row["sha256"] and (row["sha256"] != sha256 or row["size"] != size)):
            raise ValueError("file_version_conflict")
        db.execute("UPDATE resident_transfers SET size=?,sha256=? WHERE id=?", (size, sha256, tid))
    return transfer_info(tid)


def transfer_write(tid, offset, data):
    if len(data) > 1024 * 1024:
        raise ValueError("chunk_too_large")
    with phone_jobs._db() as db:
        transfer_schema(db)
        row = db.execute("SELECT * FROM resident_transfers WHERE id=?", (tid,)).fetchone()
        if not row or row["state"] == "committed" or row["size"] is None:
            raise ValueError("transfer_not_writable")
        if offset != row["offset"] or offset + len(data) > row["size"]:
            raise ValueError("offset_conflict")
        path = transfer_path(tid, True)
        with path.open("r+b" if path.exists() else "w+b") as f:
            f.seek(offset)
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        os.chmod(path, 0o600)
        db.execute("UPDATE resident_transfers SET offset=?,state='transferring' WHERE id=?",
                   (offset + len(data), tid))
    return {"offset": offset + len(data)}


def transfer_commit(tid):
    with phone_jobs._db() as db:
        transfer_schema(db)
        row = db.execute("SELECT * FROM resident_transfers WHERE id=?", (tid,)).fetchone()
        if not row:
            raise ValueError("transfer_not_found")
        if row["state"] == "committed":
            return dict(row)
        if row["size"] != row["offset"]:
            raise ValueError("transfer_incomplete")
        path = transfer_path(tid, True)
        if row["size"] == 0:
            path.touch(mode=0o600, exist_ok=True)
        # A crash after rename but before DB commit is recoverable.
        source = path if path.exists() else transfer_path(tid)
        digest = hashlib.sha256()
        with source.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise ValueError("hash_mismatch")
        if source == path:
            os.replace(path, transfer_path(tid))
        db.execute("UPDATE resident_transfers SET state='committed' WHERE id=?", (tid,))
    return transfer_info(tid)


def transfer_local(target, args):
    """Agent file transfer, without loading large files into tool results or memory."""
    action = args.get('action', 'send')
    tid = args.get('transfer_id')
    if action == 'collect':
        row = transfer_info(tid)
        if row['direction'] != 'from_pc' or row['state'] != 'committed':
            raise ValueError('transfer_not_ready')
        dest = Path(args['local_path']).expanduser()
        if not dest.is_absolute():
            raise ValueError('absolute_local_path_required')
        import shutil
        with transfer_path(tid).open('rb') as src, dest.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        return {'success': True, 'path': str(dest), 'sha256': row['sha256']}
    if action == 'send':
        source = Path(args['local_path']).expanduser()
        digest = hashlib.sha256()
        with source.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(chunk)
        row = transfer_info(tid) if tid else transfer_create(
            target, 'to_pc', source.name, source.stat().st_size, digest.hexdigest())
        if row['device'] != resolve(target)['device_id'] or row['direction'] != 'to_pc' or row['sha256'] != digest.hexdigest():
            raise ValueError('transfer_source_conflict')
        if row['state'] != 'committed':
            offset = row['offset']
            with source.open('rb') as f:
                f.seek(offset)
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    offset = transfer_write(row['id'], offset, chunk)['offset']
            transfer_commit(row['id'])
    elif action == 'receive':
        row = transfer_info(tid) if tid else transfer_create(target, 'from_pc', Path(args['path']).name)
        if row['device'] != resolve(target)['device_id'] or row['direction'] != 'from_pc':
            raise ValueError('transfer_source_conflict')
    else:
        raise ValueError('action must be send/receive/collect')
    receipt = submit(target, {'op': 'transfer', 'transfer_id': row['id'], 'path': args['path'],
                              'timeout': args.get('timeout', 86400)}, args.get('request_id'))
    return {**receipt, 'transfer_id': row['id']}


def public_base():
    """The helper needs the direct tunnel host, not a static Worker/CDN face."""
    from urllib.parse import urlsplit
    import face_config
    cfg = face_config.load_config()
    base = (cfg.get('public_base') or '').rstrip('/')
    direct = cfg.get('direct_hosts') or []
    if base and urlsplit(base).hostname in [host.split(':')[0] for host in direct]:
        return base
    if direct:
        return 'https://' + direct[0]
    return base
