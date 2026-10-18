"""읽기 제공자가 발급하는 작은 관측 영수증. 본문은 저장하지 않는다.

pulse DB의 영수증은 신원/출처를 해소하는 통로다. 기억은 해소한 범위와 판본을
자기 문서에 복사하므로 영수증 수명과 현재성은 독립이다.
"""
import copy
import hashlib
import json
import os
import stat
import uuid
from datetime import datetime, timezone

from distill_receipts import fingerprint


def now():
    return datetime.now(timezone.utc).isoformat()


def identity():
    import principal
    from runtime_utils import detect_body
    return principal.current().key(), (detect_body() or {}).get('profile') or 'pc'


def device_identity():
    state = os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR')
    if state:
        return fingerprint(['runtime-device', os.path.abspath(state)])
    from device_registry import self_device_id
    return self_device_id()


def file_state(path):
    s = os.stat(path)
    return {'size': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns,
            'dev': s.st_dev, 'ino': s.st_ino, 'target': os.path.realpath(path)}


def file_evidence(path, before, digest, scope, *, method='sha256_bytes'):
    try:
        after = file_state(path)
    except OSError:
        after = None
    return {'schema_version': 1, 'source': {'kind': 'file', 'address': os.path.abspath(path)},
            'observation_kind': 'file_full' if scope.get('complete') else 'file_partial',
            'scope': scope, 'version': {'method': method, 'sha256': digest, 'metadata': before},
            'observed_at': now(), 'link_state': 'observed', 'stable': before == after}


def listing_evidence(path, before, records, *, pattern=None, complete=True):
    entries = []
    for r in records:
        p = r.get('path') or os.path.join(path, r.get('name', ''))
        mode = os.lstat(p).st_mode
        kind = 'symlink' if stat.S_ISLNK(mode) else ('directory' if stat.S_ISDIR(mode) else 'file')
        entries.append([os.path.relpath(p, path), kind])
    return {'schema_version': 1, 'source': {'kind': 'directory', 'address': os.path.abspath(path)},
            'observation_kind': 'directory_listing',
            'scope': {'depth': 1, 'pattern': pattern, 'exclusions': [], 'complete': complete},
            'version': {'method': 'listing_names_kinds', 'sha256': fingerprint(sorted(entries)),
                        'metadata': before},
            'observed_at': now(), 'link_state': 'observed', 'stable': before == file_state(path)}


def _conn():
    from pulse_db import _get_pulse_db
    # Processes/tests already share this runtime-state boundary. Production uses pulse DB.
    state = os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR')
    if state:
        import sqlite3
        os.makedirs(state, exist_ok=True)
        conn = sqlite3.connect(os.path.join(state, 'source_observations.db'), timeout=10)
    else:
        conn = _get_pulse_db()
    conn.execute('CREATE TABLE IF NOT EXISTS source_observations '
                 '(id TEXT PRIMARY KEY, principal TEXT NOT NULL, body TEXT NOT NULL, '
                 'result_hash TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS source_observations_result '
                 'ON source_observations(result_hash, principal, body)')
    return conn


def publish(evidence, result):
    """도구 구현만 호출한다. AI의 provenance는 이 레코드를 만들 수 없다."""
    principal, body = identity()
    evidence = copy.deepcopy(evidence)
    ref = uuid.uuid4().hex
    evidence['source']['body'] = body
    evidence['source']['device_id'] = device_identity()
    evidence['observation_ref'] = {'receipt_id': ref}
    conn = _conn()
    try:
        conn.execute('INSERT INTO source_observations VALUES (?,?,?,?,?,?)',
                     (ref, principal, body, fingerprint(result), json.dumps(evidence), now()))
        conn.commit()
    finally:
        conn.close()
    return ref


def resolve(ref, *, locus, principal=None, body=None):
    current_principal, current_body = identity()
    principal, body = principal or current_principal, body or current_body
    if principal != current_principal or body != current_body:
        raise ValueError('observation_identity_mismatch')
    conn = _conn()
    try:
        row = conn.execute('SELECT principal,body,payload FROM source_observations WHERE id=?',
                           (ref,)).fetchone()
    finally:
        conn.close()
    if not row or row[0] != principal or row[1] != body:
        raise ValueError('unknown_or_foreign_observation')
    evidence = json.loads(row[2])
    if evidence['source'].get('device_id') != device_identity():
        raise ValueError('observation_device_mismatch')
    address = evidence['source']['address']
    # A folder claim may cite observed children; a file cannot cite unrelated siblings.
    if not (address == locus or address.startswith(locus.rstrip('/') + '/')):
        raise ValueError('observation_outside_locus')
    return evidence


def find_for_result(result, *, principal=None, body=None):
    """생산자가 반환한 값과 정확히 일치할 때만 연결. 주소 추측/AI 해시는 사용하지 않는다."""
    owner, host = identity()
    principal, body = principal or owner, body or host
    if principal != owner or body != host:
        return []
    conn = _conn()
    try:
        rows = conn.execute('SELECT payload FROM source_observations WHERE result_hash=? '
                            "AND principal=? AND body=? GROUP BY json_extract(payload, '$.source.address') "
                            'ORDER BY max(created_at) DESC LIMIT 2',
                            (fingerprint(result), principal, body)).fetchall()
        return [json.loads(rows[0][0])] if len(rows) == 1 else []
    finally:
        conn.close()


def attach(result, evidence, envelope=True):
    """문자열 본문 계약은 유지. JSON 봉투에는 해소 가능한 참조만 추가한다."""
    ref = publish(evidence, result)
    if not envelope:
        return result
    try:
        obj = json.loads(result) if isinstance(result, str) else result
    except (ValueError, TypeError):
        return result
    if isinstance(obj, dict):
        obj = {**obj, 'source_observation_ref': ref}
        return json.dumps(obj, ensure_ascii=False) if isinstance(result, str) else obj
    return result


def from_result(result, *, principal=None, body=None):
    matched = find_for_result(result, principal=principal, body=body)
    if matched:
        return matched
    try:
        obj = json.loads(result) if isinstance(result, str) else result
    except (ValueError, TypeError):
        obj = result
    if isinstance(obj, dict) and obj.get('source_observation_ref'):
        # Address comes from the stored receipt, never a model supplied claim.
        conn = _conn()
        try:
            r = conn.execute('SELECT payload FROM source_observations WHERE id=?',
                             (obj['source_observation_ref'],)).fetchone()
        finally:
            conn.close()
        if not r:
            raise ValueError('unknown_observation')
        address = json.loads(r[0])['source']['address']
        return [resolve(obj['source_observation_ref'], locus=address, principal=principal, body=body)]
    if isinstance(obj, dict) and obj.get('edition') == 2 and obj.get('executed') is True:
        found = []
        for ref in obj.get('source_observation_refs', []):
            found.extend(from_result({'source_observation_ref': ref}, principal=principal, body=body))
        for event in obj.get('evidence', []):
            if isinstance(event, dict) and event.get('kind') == 'tool_evidence':
                ref = event.get('source_observation_ref')
                if ref:
                    found.extend(from_result({'source_observation_ref': ref}, principal=principal, body=body))
        return found
    return find_for_result(result, principal=principal, body=body)


# 반환 모양을 바꾸지 않고 실제 읽기와 최종 반환을 연결하는 호출 범위.
from contextvars import ContextVar
from functools import wraps
_capture = ContextVar('source_observation_capture', default=None)


def capture(evidence, envelope=True):
    slot = _capture.get()
    if slot is not None:
        slot.append((evidence, envelope))


def observed_tool(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        observations = []
        token = _capture.set(observations)
        try:
            result = fn(*args, **kwargs)
            for evidence, envelope in observations:
                if envelope:
                    obj = json.loads(result) if isinstance(result, str) else result
                    if isinstance(obj, dict) and (obj.get('success') is False or obj.get('error')):
                        continue
                result = attach(result, evidence, envelope)
            return result
        finally:
            _capture.reset(token)
    return run
