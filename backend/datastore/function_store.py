"""Immutable function revisions and one atomically published library catalog.

No compiler, memory database or deployment fallback is read here. The assembly
root supplies the compiler gate and the existing workflow storage location.
"""
import copy
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from contextlib import contextmanager
from functools import lru_cache
from contextvars import ContextVar


_root_provider = None
_validator = None
_registrar = None
_snapshot_context = ContextVar('function_snapshot', default=None)


@contextmanager
def using(view, root=None):
    root = Path(root) if root is not None else storage_root()
    token = _snapshot_context.set((str(root.resolve()), view))
    try:
        yield view
    finally:
        _snapshot_context.reset(token)


def wire(root, validator, registrar):
    global _root_provider, _validator, _registrar
    _root_provider, _validator, _registrar = root, validator, registrar


def storage_root(for_write=False):
    if _root_provider is None:
        raise ValueError('관용구 원장 배선이 없습니다. import boot_paths가 필요합니다.')
    return Path(_root_provider(for_write=for_write))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _token(value, revision=False):
    if not isinstance(value, str) or not re.fullmatch(
            r'[0-9a-f]{64}' if revision else r'[0-9a-f]{32}', value):
        raise ValueError('잘못된 관용구 ID 또는 판본입니다.')
    return value


def _safe(path, root):
    parents = [p for p in path.parents if p == root or root in p.parents]
    if path.is_symlink() or any(p.is_symlink() for p in parents):
        raise ValueError('관용구 원장의 심볼릭 링크는 허용되지 않습니다.')
    return path


def _sync(directory):
    if not hasattr(os, "O_DIRECTORY"):
        return  # Directory descriptors are not supported by every filesystem API.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, prefix='.function-', delete=False) as f:
            temporary = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=64)
def _lock(root):
    from filelock import FileLock
    return FileLock(str(Path(root) / '.mutation.lock'), timeout=30)


@contextmanager
def transaction(root=None):
    root = Path(root) if root is not None else storage_root(for_write=True)
    _safe(root, root)
    root.mkdir(parents=True, exist_ok=True)
    with _lock(str(root.resolve())):
        yield root


def catalog(root=None):
    root = Path(root) if root is not None else storage_root()
    path = _safe(root / 'catalog.json', root)
    if not path.exists():
        return {'schema': 1, 'scope_id': digest(str(root.resolve())), 'generation': 0,
                'functions': {}, 'requests': {}, 'migration': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema') != 1
            or type(data.get('generation')) is not int or not isinstance(data.get('functions'), dict)):
        raise ValueError('관용구 카탈로그 형식이 잘못되었습니다.')
    return data


@lru_cache(maxsize=1024)
def _revision_data(path, stamp, function_id, revision_id):
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or digest(data) != revision_id or data.get('function_id') != function_id:
        raise ValueError('관용구 판본 지문이 일치하지 않습니다.')
    return {**data, 'revision': revision_id}


def revision(function_id, revision_id, root=None):
    root = Path(root) if root is not None else storage_root()
    path = _safe(root / 'revisions' / _token(function_id) / (_token(revision_id, True) + '.yaml'), root)
    info = path.stat()
    stamp = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)
    return copy.deepcopy(_revision_data(str(path), stamp, function_id, revision_id))


def snapshot(root=None, *, index=None):
    import yaml
    root = Path(root) if root is not None else storage_root()
    bound = _snapshot_context.get()
    if index is None and bound and bound[0] == str(root.resolve()):
        return copy.deepcopy(bound[1])
    index = catalog(root) if index is None else index
    records = {}
    for fid, entry in index['functions'].items():
        try:
            row = revision(fid, entry['revision'], root)
            if row['name'] != entry['name'] or row['edition'] != entry['edition']:
                raise ValueError('카탈로그 이름 또는 언어 판본이 정의와 다릅니다.')
            records[fid] = {**row, **entry, 'function_id': fid}
        except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
            records[fid] = {**entry, 'function_id': fid, 'problem': str(exc), 'state': 'invalid'}
    return {'generation': index['generation'], 'records': records}


def resolve(name=None, *, function_id=None, edition=None, root=None, view=None, include_inactive=False):
    view = snapshot(root) if view is None else view
    rows = list(view['records'].values())
    if function_id is not None:
        rows = [r for r in rows if r['function_id'] == function_id]
    else:
        rows = [r for r in rows if name == r.get('name') or name in r.get('legacy_ids', [])]
    if edition is not None:
        rows = [r for r in rows if r.get('edition') == edition]
    elif any(r.get('edition') == 2 for r in rows):
        rows = [r for r in rows if r.get('edition') == 2]
    if function_id is None and any(r.get('state') != 'retired' for r in rows):
        rows = [r for r in rows if r.get('state') != 'retired']
    if len(rows) > 1:
        raise ValueError(f'관용구 이름이 충돌합니다: {name}')
    if not rows:
        return None
    row = rows[0]
    if not include_inactive and (row.get('state') != 'active' or row.get('problem')):
        raise ValueError(row.get('problem') or f'관용구가 실행 가능한 상태가 아닙니다: {row["name"]} ({row["state"]})')
    return copy.deepcopy(row)


def reference(row):
    return {k: row[k] for k in ('scope_id', 'function_id', 'revision', 'name', 'edition') if k in row}


def publish(changes, *, expected_generation=None, request_id=None, root=None,
            migration=None, request_payload=None):
    """CAS and compiler validation happen under the same catalog lock.

    A change is {record, expected_revision, state?, legacy_ids?}. The record
    contains no derived signatures or usage statistics. None expects creation.
    """
    if not isinstance(changes, list) or not changes:
        raise ValueError('변경할 관용구가 없습니다.')
    import yaml
    request_hash = digest(request_payload if request_payload is not None else {'changes': changes, 'migration': migration})
    with transaction(root) as root:
        before = catalog(root)
        if request_id and request_id in before.get('requests', {}):
            prior = before['requests'][request_id]
            if prior['hash'] != request_hash:
                raise ValueError('동일 변경 요청 ID의 내용이 다릅니다.')
            return copy.deepcopy(prior['result'])
        if expected_generation is not None and expected_generation != before['generation']:
            raise ValueError('관용구 원장이 변경됐습니다. 새 판본으로 다시 검사하세요.')
        after = copy.deepcopy(before)
        records = snapshot(root, index=before)['records']
        writes, refs, seen = [], [], set()
        for change in changes:
            record = copy.deepcopy(change['record'])
            record.setdefault('scope_id', before['scope_id'])
            if record['scope_id'] != before['scope_id']:
                raise ValueError('다른 소유 범위의 관용구 정의입니다.')
            fid = _token(record['function_id'])
            if fid in seen:
                raise ValueError('한 변경 묶음에 같은 관용구가 두 번 있습니다.')
            seen.add(fid)
            old = before['functions'].get(fid)
            if (old or {}).get('revision') != change.get('expected_revision'):
                raise ValueError('관용구 판본 충돌: 새 정의를 읽고 다시 개정하세요.')
            if record.get('schema') != 1 or record.get('edition') not in (1, 2) or not record.get('name'):
                raise ValueError('관용구 정의 형식이 잘못되었습니다.')
            record['source_hash'] = digest(record.get('source', ''))
            rid = digest(record)
            state = change.get('state', (old or {}).get('state', 'active'))
            if old and old.get('state') != 'active' and state == 'active' and not record.get('reason', '').strip():
                raise ValueError('비활성 관용구의 재활성화에는 이유가 필요합니다.')
            if state not in ('active', 'retired', 'hold', 'quarantine', 'invalid'):
                raise ValueError('잘못된 관용구 상태입니다.')
            entry = {'name': record['name'], 'edition': record['edition'], 'revision': rid,
                     'state': state, 'legacy_ids': change.get('legacy_ids', (old or {}).get('legacy_ids', []))}
            after['functions'][fid] = entry
            records[fid] = {**record, **entry}
            writes.append((fid, rid, record))
            refs.append(reference(records[fid]))
        names = {}
        for fid, row in records.items():
            if row.get('state') == 'retired':
                continue
            key = (row['edition'], row['name'])
            if key in names and names[key] != fid:
                raise ValueError(f'관용구 이름 충돌: {row["name"]}')
            names[key] = fid
        if _validator is None:
            raise ValueError('관용구 컴파일 관문이 배선되지 않았습니다.')
        _validator(snapshot(root, index=before), {'records': records, 'generation': before['generation'] + 1}, seen)
        for fid, rid, record in writes:
            path = _safe(root / 'revisions' / fid / (rid + '.yaml'), root)
            if path.exists():
                revision(fid, rid, root)
            else:
                _atomic(path, yaml.safe_dump(record, allow_unicode=True, sort_keys=True))
        after['generation'] += 1
        if migration is not None:
            after['migration'] = migration
        result = {'generation': after['generation'], 'functions': refs}
        if request_id:
            after.setdefault('requests', {})[request_id] = {'hash': request_hash, 'result': result}
        _atomic(root / 'catalog.json', json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        return result


def register_memory(name, source, description='', provenance=None, **kwargs):
    if _registrar is None:
        raise ValueError('관용구 등록 관문이 배선되지 않았습니다.')
    return _registrar(name, source, description, provenance or {}, **kwargs)


def project_memory(row, *, view=None):
    """A memory source remains historical; callable views use its exact reference."""
    result = dict(row)
    try:
        provenance = result.get('provenance') or {}
        if isinstance(provenance, str):
            provenance = json.loads(provenance)
        ref = provenance.get('function_ref')
        if not ref:
            if result.get('alias'):
                result['function_problem'] = '미이관 기억입니다. 실행 정의를 공급하지 않습니다.'
            return result
        current = resolve(function_id=ref['function_id'], view=view)
        if current is None or ref.get('scope_id') != current.get('scope_id'):
            raise ValueError('현재 소유 범위에 참조한 관용구가 없습니다.')
        from ibl_edition import pin_source
        result.update(ibl_code=(pin_source(current['source'], 2) if current['edition'] == 2 else current['source']), alias=current['name'],
                      function_ref=reference(current), evidence_revision=ref['revision'],
                      evidence_stale=current['revision'] != ref['revision'])
        from capability_history import function_statistics
        from ibl_signature_slot import signature_of
        result.update(function_statistics(reference(current)))
        result['signature'] = signature_of(result['ibl_code'])
        if result['evidence_stale']:
            result.update(returns='', avg_ms=-1, avg_tokens=-1)
        result['provenance'] = json.dumps({**provenance, 'function_ref': reference(current),
                                         'evidence_revision': ref['revision']}, ensure_ascii=False)
    except (OSError, ValueError, KeyError) as exc:
        result['function_problem'] = str(exc)
    return result


def memory_reference(name, edition=1):
    """Compatibility view, sourced from a definition rather than a memory row."""
    row = resolve(name, edition=edition)
    if row is None:
        return None
    from ibl_edition import pin_source
    return {'id': None, 'alias': row['name'], 'ibl_code': (pin_source(row['source'], 2) if row['edition'] == 2 else row['source']),
            'intent': row.get('description', ''), 'category': 'phrase', 'topic': '',
            'returns': '', 'returns_observed': '', 'signature': None,
            'provenance': json.dumps({'function_ref': reference(row)}, ensure_ascii=False),
            'function_ref': reference(row), 'success_count': 0, 'fail_count': 0,
            'bypass_count': 0}
