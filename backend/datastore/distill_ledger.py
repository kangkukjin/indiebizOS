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


def compact_finished(comparison_selector):
    """종결 원장의 코퍼스 중복 사본만 제거한다. 원문·판정·영수증·작업 키는 보존한다."""
    from hashlib import sha256
    stats = {'compacted': 0, 'bytes_saved': 0}
    conn = _conn()
    try:
        # JSON 비교 조건으로 동시 갱신을 덮어쓰지 않는다. 진행/재시도 행은 제외한다.
        rows = conn.execute("SELECT job_key,prepared FROM distill_jobs WHERE status IN "
                            "('completed','completed_empty','completed_with_rejections','skipped','failed') "
                            "AND prepared IS NOT NULL").fetchall()
        for key, raw in rows:
            prepared = json.loads(raw)
            section = (prepared.get('sections') or {}).get('execution')
            if not section or 'known' not in section:
                continue
            # 실제 모델에 보인 비교 4건은 전문 보존. 코퍼스 전체는 판단 입력이 아니었다.
            known = section.pop('known')
            section['comparison_examples'] = comparison_selector(section.get('source_calls', []), known)
            section['corpus_snapshot'] = {'count': len(known), 'sha256': sha256(
                json.dumps(known, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
            # 통합 경로에서 사용하지 않은 구형 별도 증류 프롬프트만 제거한다.
            prompt = section.pop('prompt', None)
            if prompt is not None:
                section['unused_prompt_sha256'] = sha256(prompt.encode()).hexdigest()
            compact = json.dumps(prepared, ensure_ascii=False)
            updated = conn.execute("UPDATE distill_jobs SET prepared=? WHERE job_key=? AND prepared=? "
                                   "AND status IN ('completed','completed_empty','completed_with_rejections',"
                                   "'skipped','failed')", (compact, key, raw)).rowcount
            stats['compacted'] += updated
            stats['bytes_saved'] += updated * (len(raw.encode()) - len(compact.encode()))
        conn.commit()
        return stats
    finally:
        conn.close()
