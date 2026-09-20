"""통합 증류 판단·후보 영수증. 큐 행 삭제 뒤에도 재배달을 식별한다."""
import json
from datetime import datetime, timezone


class PermanentDistillError(ValueError):
    """받은 출력의 계약 위반. 모델을 다시 불러 고치지 않는다."""


def _conn():
    from pulse_db import _get_pulse_db
    conn = _get_pulse_db()
    conn.execute("CREATE TABLE IF NOT EXISTS distill_jobs ("
                 "job_key TEXT PRIMARY KEY, payload TEXT NOT NULL, prepared TEXT, decision TEXT, "
                 "status TEXT NOT NULL, receipts TEXT NOT NULL DEFAULT '{}', "
                 "attempts INTEGER NOT NULL DEFAULT 0, error TEXT, updated_at TEXT NOT NULL)")
    conn.commit()
    return conn


def read(key):
    conn = _conn()
    try:
        row = conn.execute("SELECT payload,prepared,decision,status,receipts,attempts,error "
                           "FROM distill_jobs WHERE job_key=?", (key,)).fetchone()
        if not row:
            return None
        names = ("payload", "prepared", "decision", "status", "receipts", "attempts", "error")
        result = dict(zip(names, row))
        for name in ("payload", "prepared", "decision", "receipts"):
            result[name] = json.loads(result[name]) if result[name] is not None else None
        return result
    finally:
        conn.close()


def create(payload):
    conn = _conn()
    try:
        conn.execute("INSERT OR IGNORE INTO distill_jobs (job_key,payload,status,updated_at) "
                     "VALUES (?,?,'prepared',?)", (payload["job_key"], json.dumps(payload, ensure_ascii=False), _now()))
        conn.commit()
    finally:
        conn.close()
    return read(payload["job_key"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def update(key, **values):
    allowed = {"prepared", "decision", "status", "receipts", "attempts", "error"}
    if not values or not set(values) <= allowed:
        raise ValueError("invalid ledger fields")
    for name in ("prepared", "decision", "receipts"):
        if name in values:
            values[name] = json.dumps(values[name], ensure_ascii=False)
    values["updated_at"] = _now()
    conn = _conn()
    try:
        conn.execute("UPDATE distill_jobs SET " + ",".join(k + "=?" for k in values) + " WHERE job_key=?",
                     (*values.values(), key))
        conn.commit()
    finally:
        conn.close()


def receipt(key, name, result):
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT receipts FROM distill_jobs WHERE job_key=?", (key,)).fetchone()
        if not row:
            raise ValueError("missing distill job")
        receipts = json.loads(row[0])
        receipts[name] = result
        conn.execute("UPDATE distill_jobs SET receipts=?,updated_at=? WHERE job_key=?",
                     (json.dumps(receipts, ensure_ascii=False), _now(), key))
        conn.commit()
    finally:
        conn.close()


def once(key, name, action):
    """범위 밖 후처리는 불명확한 중단 후 재실행하지 않는다(중단 영수증 보존)."""
    name = "stage:" + name
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT receipts FROM distill_jobs WHERE job_key=?", (key,)).fetchone()
        receipts = json.loads(row[0])
        if name in receipts:
            return receipts[name]
        receipts[name] = {"status": "started", "reason": "중단 시 자동 재실행 금지"}
        conn.execute("UPDATE distill_jobs SET receipts=? WHERE job_key=?",
                     (json.dumps(receipts, ensure_ascii=False), key))
        conn.commit()
    finally:
        conn.close()
    try:
        action()
        result = {"status": "completed"}
    except Exception as exc:
        result = {"status": "failed", "reason": str(exc)}
    receipt(key, name, result)
    return result
