"""Resident PC jobs and append-only observations in the existing phone job database."""
import hashlib
import json
import time
import uuid

import phone_jobs


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS resident_tasks (
        id TEXT PRIMARY KEY, device TEXT NOT NULL, generation TEXT NOT NULL,
        request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, summary TEXT NOT NULL,
        created REAL NOT NULL, state TEXT NOT NULL, result TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        UNIQUE(device,generation,request_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS resident_events (
        cursor INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, device TEXT NOT NULL,
        event_id TEXT NOT NULL, kind TEXT NOT NULL, occurred REAL NOT NULL,
        received REAL NOT NULL, payload TEXT NOT NULL, UNIQUE(device,event_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS resident_events_job ON resident_events(job,cursor)")


def _event(db, device, job, event_id, kind, payload, occurred=None):
    now = time.time()
    db.execute("INSERT OR IGNORE INTO resident_events(job,device,event_id,kind,occurred,received,payload) "
               "VALUES(?,?,?,?,?,?,?)", (job, device, event_id, kind, occurred or now, now,
                                          json.dumps(payload, ensure_ascii=False)))


def submit(rec, command, request_id, owner=None):
    reg = rec["registration"]
    if reg["state"] != "active" or reg.get("paused") or rec.get("revoked"):
        raise ValueError("registration_unavailable")
    if not request_id or len(request_id) > 160:
        raise ValueError("request_id_required")
    serialized = json.dumps(command, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    with phone_jobs._db() as db:
        schema(db)
        old = db.execute("SELECT * FROM resident_tasks WHERE device=? AND generation=? AND request_id=?",
                         (rec["device_id"], reg["generation"], request_id)).fetchone()
        if old:
            if old["fingerprint"] != fingerprint:
                raise ValueError("request_id_conflict")
            return old["id"]
        jid = uuid.uuid4().hex
        now = time.time()
        envelope = {**command, "resident": True, "generation": reg["generation"]}
        # Secret stdin and environment are not copied into the history or events.
        summary = {k: v for k, v in command.items() if k not in {"stdin", "env"}}
        db.execute("INSERT INTO jobs(id,device,code,agent,created,updated,state) VALUES(?,?,?,?,?,?,'queued')",
                   (jid, rec["device_id"], json.dumps(envelope, ensure_ascii=False), owner, now, now))
        db.execute("INSERT INTO resident_tasks VALUES(?,?,?,?,?,?,?,'queued',NULL,0)",
                   (jid, rec["device_id"], reg["generation"], request_id, fingerprint,
                    json.dumps(summary, ensure_ascii=False), now))
        _event(db, rec["device_id"], jid, "submitted:" + jid, "queued", summary)
    phone_jobs._wake()
    return jid


def observe(rec, events):
    if len(events) > 64:
        raise ValueError("too_many_events")
    acknowledged = []
    with phone_jobs._db() as db:
        schema(db)
        for event in events:
            jid, eid = event.get("job_id", ""), event.get("event_id", "")
            if not eid or len(eid) > 160:
                raise ValueError("invalid_event_id")
            row = db.execute("SELECT * FROM resident_tasks WHERE id=? AND device=? AND generation=?",
                             (jid, rec["device_id"], rec["registration"]["generation"])).fetchone()
            if row is None:
                raise ValueError("job_not_owned")
            kind = event.get("kind")
            if kind not in {"started", "log", "result", "log_gap"}:
                raise ValueError("invalid_event_kind")
            payload = event.get("payload") or {}
            if len(json.dumps(payload).encode()) > (2 * 1024 * 1024 if kind == "result" else 128 * 1024):
                raise ValueError("event_too_large")
            existing = db.execute("SELECT job,kind,payload FROM resident_events WHERE device=? AND event_id=?",
                                  (rec["device_id"], eid)).fetchone()
            if existing:
                if existing["job"] != jid or existing["kind"] != kind or json.loads(existing["payload"]) != payload:
                    raise ValueError("event_id_conflict")
                acknowledged.append(eid)
                continue
            _event(db, rec["device_id"], jid, eid, kind, payload, event.get("occurred_at"))
            if kind == "started" and row["result"] is None:
                db.execute("UPDATE resident_tasks SET state='running' WHERE id=?", (jid,))
            if kind == "result" and row["result"] is None:
                state = ("cancelled" if payload.get("cancelled") else
                         "unknown" if payload.get("unknown") else
                         "failed" if payload.get("error") or payload.get("exit", 0) != 0 else "succeeded")
                encoded = json.dumps(payload, ensure_ascii=False)
                db.execute("UPDATE resident_tasks SET state=?,result=? WHERE id=?", (state, encoded, jid))
                db.execute("UPDATE jobs SET state='completed',result=?,partial=NULL,updated=? WHERE id=?",
                           (encoded, time.time(), jid))
            acknowledged.append(eid)
    phone_jobs._wake()
    return acknowledged


def cancel(jid, device=None):
    with phone_jobs._db() as db:
        schema(db)
        row = db.execute("SELECT * FROM resident_tasks WHERE id=?", (jid,)).fetchone()
        if not row or (device and row["device"] != device):
            raise ValueError("job_not_found")
        if row["result"] or row["cancel_requested"]:
            return False
        pending = db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND state='queued'",
                             (time.time(), jid)).rowcount
        db.execute("UPDATE resident_tasks SET cancel_requested=1,state=? WHERE id=?",
                   ("cancelled" if pending else "cancel_requested", jid))
        _event(db, row["device"], jid, "cancel:" + jid, "cancel_requested", {"before_delivery": bool(pending)})
    phone_jobs._wake()
    return True


def cancellations(device):
    with phone_jobs._db() as db:
        schema(db)
        return [r[0] for r in db.execute("SELECT id FROM resident_tasks WHERE device=? "
                                       "AND cancel_requested=1 AND result IS NULL", (device,))]


def history(device=None, job=None, cursor=0, limit=100):
    limit = int(limit)
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1..200")
    with phone_jobs._db() as db:
        schema(db)
        where, params = [], []
        if device:
            where.append("device=?")
            params.append(device)
        if job:
            where.append("id=?")
            params.append(job)
        clause = " WHERE " + " AND ".join(where) if where else ""
        tasks = [dict(r) for r in db.execute("SELECT * FROM resident_tasks" + clause +
                                            " ORDER BY created DESC LIMIT ?", (*params, limit))]
        for task in tasks:
            task["summary"] = json.loads(task["summary"])
            task["result"] = json.loads(task["result"]) if task["result"] else None
            current = db.execute("SELECT state FROM jobs WHERE id=?", (task["id"],)).fetchone()
            if current and current[0] in {"expired", "unknown"} and task["result"] is None:
                task["state"] = current[0]
            task.pop("fingerprint", None)
        ev_where, ev_params = ["cursor> ?"], [max(0, int(cursor))]
        for key, value in (("device", device), ("job", job)):
            if value:
                ev_where.append(key + "=?")
                ev_params.append(value)
        events = [dict(r) for r in db.execute("SELECT * FROM resident_events WHERE " +
                    " AND ".join(ev_where) + " ORDER BY cursor LIMIT ?", (*ev_params, limit))]
        for e in events:
            e["payload"] = json.loads(e["payload"])
        return {"tasks": tasks, "events": events,
                "cursor": events[-1]["cursor"] if events else int(cursor)}
