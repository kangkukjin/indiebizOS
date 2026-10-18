"""문서 안의 단언 ID와 판본 있는 근거 절. JSON은 검색 본문과 분리한다."""
import json
import re
import uuid

from forage_evidence import bind, provenance, claim_digest
from distill_receipts import fingerprint

SECTION = '## 근거'
REF_RE = re.compile(r'(?:^|·)\s*ref:([a-f0-9]{32})\s*(?:$|·)')


def prepare(row):
    row = dict(row)
    p = provenance(row.get('provenance'))
    # 최초 이행의 ID는 재시도/중단에도 같다. 새 note는 발급 ID를 DB에 저장한다.
    p.setdefault('claim_ref', uuid.uuid5(uuid.NAMESPACE_URL,
                 fingerprint([row.get('body'), claim_digest(row)])).hex)
    row['provenance'] = json.dumps(bind(row, p), ensure_ascii=False)
    return row


def render(rows):
    records, seen = [], set()
    for row in rows:
        p = provenance(row['provenance'])
        ref = p['claim_ref']
        if ref in seen:
            raise ValueError('duplicate_claim_ref')
        seen.add(ref)
        records.append({'id': ref, 'provenance': p})
    return SECTION + '\n\n```json\n' + json.dumps(
        {'schema_version': 1, 'claims': records}, ensure_ascii=False, indent=2) + '\n```\n'


def claim_lines(body):
    pending = None
    for line in body.splitlines():
        if pending is not None:
            if line.startswith(('### ', '- [')):
                raise ValueError('unclosed_claim_metadata')
            pending += ' ' + line.strip()
            if '›' in line:
                yield pending
                pending = None
        elif line.startswith('- [') and '‹' in line and '›' not in line:
            pending = line
        else:
            yield line
    if pending is not None:
        raise ValueError('unclosed_claim_metadata')


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate_evidence_key')
        out[key] = value
    return out


def parse(text):
    import tree_doc
    if len(re.findall(r'^## 근거\s*$', text, re.M)) > 1:
        raise ValueError('duplicate_evidence_section')
    section = tree_doc.split_section(text, SECTION)[1]
    if not section:
        return {}
    match = re.search(r'```json\s*\n(.*?)\n```', section, re.S)
    if not match:
        raise ValueError('invalid_evidence_section')
    data = json.loads(match[1], object_pairs_hook=_unique)
    if data.get('schema_version') != 1 or not isinstance(data.get('claims'), list):
        raise ValueError('unsupported_evidence_version')
    records = {}
    for record in data['claims']:
        ref, p = record['id'], record['provenance']
        if not re.fullmatch('[a-f0-9]{32}', ref) or ref in records or p.get('claim_ref') != ref:
            raise ValueError('duplicate_or_conflicting_evidence')
        e = p.get('evidence', {})
        if e.get('schema_version') != 1 or not isinstance(e.get('items'), list):
            raise ValueError('unsupported_evidence_version')
        records[ref] = p
    return records


def attach(row, meta, records, seen):
    match = REF_RE.search(meta)
    if not match:
        return
    ref = match[1]
    if ref in seen:
        raise ValueError('duplicate_claim_ref')
    if ref not in records:
        raise ValueError('missing_claim_evidence')
    seen.add(ref)
    row['provenance'] = json.dumps(bind(row, records[ref]), ensure_ascii=False)


def replace(text, rendered):
    import tree_doc
    claims, evidence = rendered.split(SECTION, 1)
    text = tree_doc.replace_section(text, '## 단언', claims)
    return tree_doc.replace_section(text, SECTION, SECTION + evidence)


# 같은 쓰기 호출의 문서 비교값. pending receipt에도 실어 프로세스 중단을 건넌다.
from contextvars import ContextVar
from functools import wraps
_versions = ContextVar('forage_document_versions', default=None)
_note_signature = ContextVar('forage_note_signature', default=None)


def document_hash(path):
    from pathlib import Path
    return fingerprint(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else None


def check_write(path, rendered=None):
    versions = _versions.get()
    if (versions is not None and document_hash(path) != versions.get(path)
            and (rendered is None or document_hash(path) != fingerprint(rendered))):
        raise ValueError('forage_document_changed')


def projected(path):
    versions = _versions.get()
    if versions is not None:
        versions[path] = document_hash(path)


def document_versions():
    return dict(_versions.get() or {})


def note_signature():
    return _note_signature.get()


from contextlib import contextmanager


@contextmanager
def document_guard(versions):
    token = _versions.set(dict(versions))
    try:
        yield
    finally:
        _versions.reset(token)


def guarded_note(fn):
    @wraps(fn)
    def call(**kwargs):
        import principal
        if not principal.is_owner():
            return {"success": False, "error": "principal_not_owner"}
        import forage_doc as fd
        import forage_memory as fm
        from distill_receipts import lookup, projection_pending, pending_connection
        signature = fingerprint(kwargs)
        key = kwargs.get('candidate_key')
        conn = fm._connect()
        try:
            if not key:
                if pending_connection(conn):
                    for pending_key, raw in conn.execute('SELECT candidate_key,result FROM distill_receipts WHERE projected=0'):
                        if json.loads(raw).get('note_signature') == signature:
                            key = pending_key
                            break
                key = key or 'forage-note:' + uuid.uuid4().hex
                kwargs['candidate_key'] = key
            receipt = lookup(conn, key)
        finally:
            conn.close()
        pending = projection_pending(fm._DB_PATH)
        if pending and not receipt:
            raise ValueError('pending_distill_projection')
        paths = fd._covering_docs(kwargs['locus'], kwargs.get('body'))
        if not pending:
            for path in paths:
                if fd.FM.get_meta(fd._stamp_key(path)) != fd.tree_doc.stamp_value(path):
                    result = fd.sync_doc_to_db(path)
                    if not result.get('success'):
                        raise ValueError(result.get('error') or result.get('reason'))
        versions = (receipt or {}).get('document_versions') if pending else None
        if versions is None:
            versions = {p: document_hash(p) for p, _, _ in fd._scan_docs()}
        token = _versions.set(versions)
        sig_token = _note_signature.set(signature)
        try:
            result = fn(**kwargs)
            return {k: v for k, v in result.items() if k not in {'document_versions', 'note_signature'}}
        finally:
            _versions.reset(token)
            _note_signature.reset(sig_token)
    return call
