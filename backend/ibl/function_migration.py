"""Explicit import of old definition owners; never called by name resolution."""
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import yaml
import function_store as store
from ibl_edition import source_edition


def installed_descriptions(definitions, root=None):
    """배포 정의와 일치하는 기존 시딩 교재의 용도만 읽는다. 별도 설명 사본은 없다."""
    from runtime_utils import get_base_path
    from thread_context import get_repair_workspace
    root = Path(root) if root is not None else Path(get_repair_workspace() or get_base_path()) / 'data/idioms'
    descriptions = {}
    for path in sorted(root.glob('*_seeds.json')):
        try:
            rows = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name, filename, intent = row.get('alias'), row.get('source_file'), row.get('intent')
            if (not isinstance(name, str) or name not in definitions
                    or not isinstance(filename, str) or not isinstance(intent, str)):
                continue
            source = root / filename
            if source.parent != root or source.is_symlink() or source.suffix != '.ibl':
                continue
            try:
                if source.read_text().strip() != definitions[name].strip():
                    continue
            except (OSError, UnicodeError):
                continue
            if intent.strip():
                descriptions.setdefault(name, set()).add(intent.strip())
    # 충돌한 교재를 임의로 선택하지 않는다. 이름과 상세 조회는 계속 사용 가능하다.
    return {name: next(iter(values)) for name, values in descriptions.items() if len(values) == 1}


def installed_sources(base):
    root = Path(base) / 'data' / 'idioms'
    manifest = root / 'installed.json'
    if not manifest.is_file():
        return []
    mapping = json.loads(manifest.read_text())
    result = []
    for name, filename in mapping.items():
        path = root / filename
        if path.parent != root or path.suffix not in ('.ibl', '.yaml') or path.is_symlink():
            raise ValueError('배포 정의 경로가 잘못되었습니다.')
        data = yaml.safe_load(path.read_text()) if path.suffix == '.yaml' else None
        if path.suffix == '.yaml' and not isinstance(data, dict):
            raise ValueError('배포 관용구는 정의 객체여야 합니다.')
        edition = data.get('edition', 1) if data is not None else 2
        source = (data.get('code', '').strip() if data is not None else path.read_text().strip())
        if edition == 2:
            from ibl_v2_store import definition_name
            if definition_name(source) != name:
                raise ValueError('배포 이름과 정의 머리가 다릅니다.')
        elif not isinstance(data, dict) or data.get('name') != name:
            raise ValueError('배포 이름과 정의 머리가 다릅니다.')
        entry = {'key': 'installed:' + filename, 'name': name, 'edition': edition,
                 'source': source, 'description': (data or {}).get('description', ''),
                 'origin': 'core', 'provenance': {'installed_file': filename}}
        if data is not None:
            entry['legacy_ids'] = [path.stem]
            if edition == 1:
                entry['legacy'] = data
        result.append(entry)
    descriptions = installed_descriptions({e['name']: e['source'] for e in result}, root)
    for entry in result:
        entry['description'] = descriptions.get(entry['name'], entry['description'])
    return result


def inventory(base, db_path=None):
    base = Path(base)
    entries = []
    for path in sorted((base / 'data' / 'workflows').glob('*.yaml')):
        if path.is_symlink():
            raise ValueError('구형 관용구 원장의 심볼릭 링크는 이전할 수 없습니다.')
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f'손상된 workflow: {path.name}')
        edition = data.get('edition', 1)
        entry = {'key': 'workflow:' + path.stem, 'name': data.get('name', path.stem),
                 'edition': edition, 'source': data.get('code', '').strip(),
                 'description': data.get('description', ''), 'origin': 'user',
                 'legacy_ids': [path.stem], 'provenance': {'workflow_id': path.stem}}
        if edition == 1:
            entry['legacy'] = data
        entries.append(entry)
    db_path = Path(db_path) if db_path else base / 'data' / 'ibl_usage.db'
    if db_path.is_file():
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=10) as db:
            db.row_factory = sqlite3.Row
            rows = (db.execute("SELECT * FROM ibl_examples WHERE COALESCE(alias,'') != '' ORDER BY updated_at,id")
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ibl_examples'").fetchone() else [])
            for item in rows:
                row = dict(item)
                provenance = json.loads(row.get('provenance') or '{}')
                review = provenance.get('corpus_review') or {}
                state = review.get('decision')
                if state not in ('hold', 'quarantine'):
                    state = 'invalid' if review.get('static_status') in ('invalid', 'failed') else 'active'
                entries.append({'key': 'memory:' + str(row['id']), 'name': row['alias'],
                                'edition': source_edition(row['ibl_code']), 'source': row['ibl_code'].strip(),
                                'description': row['intent'], 'origin': 'user', 'state': state,
                                'provenance': {'memory_id': row['id'], 'evidence': provenance}})
    entries.extend(installed_sources(base))
    return entries


def prepare(entries, resolutions=None):
    groups, conflicts = {}, []
    for entry in entries:
        key = (entry['edition'], entry['name'])
        groups.setdefault(key, []).append(entry)
    changes, mapping, history = [], {}, []
    for (edition, name), candidates in groups.items():
        bodies = {store.digest({'source': c['source'], 'legacy': c.get('legacy')}) for c in candidates}
        if len(bodies) > 1:
            decision = (resolutions or {}).get(f'{edition}:{name}')
            chosen = next((c for c in candidates if c['key'] == decision), None)
            if chosen is None:
                conflicts.append({'name': name, 'edition': edition,
                                  'sources': [c['key'] for c in candidates]})
                continue
        else:
            chosen = next((c for c in candidates if c['origin'] == 'core'), candidates[0])
        # Stable across reruns and within the receiving owner's independent scope.
        fid = uuid.uuid5(uuid.NAMESPACE_URL, 'indiebiz:function:' + chosen['key']).hex
        record = {k: chosen[k] for k in ('name', 'edition', 'source', 'description', 'origin')}
        record.update(schema=1, scope_id=store.catalog()['scope_id'], function_id=fid, source_hash=store.digest(chosen['source']),
                      provenance={'imports': [c['key'] for c in candidates],
                                  'evidence': [c.get('provenance', {}) for c in candidates]})
        if 'legacy' in chosen:
            record['legacy'] = chosen['legacy']
        if chosen['origin'] == 'core':
            record['installation_source_hash'] = _body_hash(record)
        states = {c.get('state', 'active') for c in candidates}
        state = next((s for s in ('quarantine', 'hold', 'invalid') if s in states), 'active')
        changes.append({'record': record, 'expected_revision': None, 'state': state,
                        'legacy_ids': list(dict.fromkeys(x for c in candidates for x in c.get('legacy_ids', [])))})
        ref = {'scope_id': record['scope_id'], 'function_id': fid, 'revision': store.digest(record), 'name': name, 'edition': edition}
        for candidate in candidates:
            previous = dict(record)
            previous['source'] = candidate['source']
            previous['source_hash'] = store.digest(candidate['source'])
            if previous['source'] != record['source'] or candidate.get('legacy') != record.get('legacy'):
                previous['provenance'] = {'imports': [candidate['key']], 'superseded_by': chosen['key']}
                if 'legacy' in candidate:
                    previous['legacy'] = candidate['legacy']
                history.append(previous)
                mapping[candidate['key']] = {**ref, 'revision': store.digest(previous),
                                              'source_hash': previous['source_hash']}
            else:
                mapping[candidate['key']] = {**ref, 'source_hash': store.digest(candidate['source'])}
    return {'changes': changes, 'mapping': mapping, 'conflicts': conflicts,
            'history': history, 'resolutions': resolutions or {},
            'inventory_hash': store.digest(entries), 'source_count': len(entries)}


def prepared_snapshot(plan, generation=0):
    """The proposed library, usable for a side-effect-free compiler check."""
    return {'generation': generation, 'records': {
        c['record']['function_id']: {**c['record'], 'state': c.get('state', 'active'),
          'revision': store.digest(c['record']), 'legacy_ids': c.get('legacy_ids', [])}
        for c in plan['changes']}}


def backup(base, db_path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    paths = ['data/workflows', 'data/idioms', 'data/hippocampus_tree', 'data/calendar_events.json']
    for relative in paths:
        src, dst = base / relative, destination / relative
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    if db_path.is_file():
        with sqlite3.connect(db_path, timeout=10) as src, sqlite3.connect(destination / 'ibl_usage.db', timeout=10) as dst:
            src.backup(dst)


def project_references(db_path, mapping):
    if not db_path.is_file():
        return 0
    count = 0
    with sqlite3.connect(db_path, timeout=10) as db:
        db.execute('BEGIN IMMEDIATE')
        for old_key, ref in mapping.items():
            if not old_key.startswith('memory:'):
                continue
            eid = int(old_key.split(':')[1])
            row = db.execute('SELECT ibl_code,provenance FROM ibl_examples WHERE id=?', (eid,)).fetchone()
            if not row or store.digest(row[0].strip()) != ref['source_hash']:
                raise ValueError('이전 중 해마 원문이 바뀌었습니다. 다시 대조하세요.')
            provenance = json.loads(row[1] or '{}')
            provenance['function_ref'] = {k: ref[k] for k in ('scope_id', 'function_id', 'revision', 'name', 'edition')}
            provenance['legacy_statistics'] = 'legacy_unattributed'
            db.execute('UPDATE ibl_examples SET provenance=? WHERE id=?',
                       (json.dumps(provenance, ensure_ascii=False), eid))
            count += 1
    return count


def migrate(base, *, apply=False, db_path=None, backup_dir=None, resolutions=None):
    base = Path(base).resolve()
    root = base / 'data' / 'workflows'
    db_path = Path(db_path).resolve() if db_path else base / 'data' / 'ibl_usage.db'
    with store.transaction(root):
        existing = store.catalog(root)
        if existing.get('migration', {}).get('complete'):
            if apply:
                _archive_legacy_inputs(root, existing['migration'])
            mapping = existing['migration']['mapping']
            count = 0
            if apply and not existing['migration'].get('projection_complete'):
                count = project_references(db_path, mapping)
                _finish_projection(root)
            return {'already_migrated': True, 'functions': len(existing['functions']), 'references': count}
        plan = prepare(inventory(base, db_path), resolutions)
        summary = {k: plan[k] for k in ('conflicts', 'inventory_hash', 'source_count')}
        summary['functions'] = len(plan['changes'])
        if plan['conflicts']:
            return summary
        from function_library import validate_changes
        before = store.snapshot(root)
        records = {c['record']['function_id']: {**c['record'], 'state': c.get('state', 'active'),
                    'revision': store.digest(c['record']), 'legacy_ids': c.get('legacy_ids', [])}
                   for c in plan['changes']}
        validate_changes(before, {'generation': before['generation'] + 1, 'records': records}, set(records))
        summary['validated'] = True
        if not apply:
            return summary
        if existing['functions']:
            raise ValueError('기존 관용구 원장이 비어 있지 않습니다. 명시 import가 필요합니다.')
        destination = Path(backup_dir) if backup_dir else base / 'data' / '_backups' / (
            datetime.now().strftime('%Y-%m-%d_관용구통합_%H%M%S'))
        backup(base, db_path, destination)
        if store.digest(inventory(base, db_path)) != plan['inventory_hash']:
            raise ValueError('백업 중 정의 입력이 바뀌었습니다. 이전을 중단합니다.')
        metadata = {'complete': True, 'inventory_hash': plan['inventory_hash'],
                    'mapping': plan['mapping'], 'backup': str(destination), 'resolutions': plan['resolutions']}
        for record in plan['history']:
            path = root / 'revisions' / record['function_id'] / (store.digest(record) + '.yaml')
            if not path.exists():
                store._atomic(path, yaml.safe_dump(record, allow_unicode=True, sort_keys=True))
        result = store.publish(plan['changes'], expected_generation=existing['generation'],
                               root=root, migration=metadata, request_id='initial-import:' + plan['inventory_hash'])
        references = project_references(db_path, plan['mapping'])
        _finish_projection(root)
        _archive_legacy_inputs(root, metadata)
        (destination / 'migration.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        return {**summary, 'generation': result['generation'], 'references': references,
                'backup': str(destination), 'applied': True}


def _finish_projection(root):
    index = store.catalog(root)
    index['migration']['projection_complete'] = True
    index['generation'] += 1
    store._atomic(root / 'catalog.json', json.dumps(index, ensure_ascii=False, indent=2))


def install(base):
    """Fresh install/update through the same gate; personal revisions are retained."""
    root = Path(base) / 'data' / 'workflows'
    if not (root / 'catalog.json').exists() and any(
            not e['key'].startswith('installed:') for e in inventory(base)):
        raise ValueError('기존 정의의 명시 이전이 필요합니다: scripts/migrate_functions.py --apply')
    entries = installed_sources(base)
    if not entries:
        return {'updated': [], 'conflicts': []}
    prepared = prepare(entries)
    view = store.snapshot(root)
    changes, conflicts = [], []
    for change in prepared['changes']:
        record = change['record']
        old = store.resolve(record['name'], edition=record['edition'], root=root, view=view, include_inactive=True)
        if old:
            if _body_hash(old) == _body_hash(record):
                continue
            if _body_hash(old) != old.get('installation_source_hash'):
                conflicts.append(record['name'])
                continue
            record['function_id'] = old['function_id']
            change['expected_revision'] = old['revision']
            change['state'] = old['state']
        changes.append(change)
    if changes:
        store.publish(changes, root=root, expected_generation=view['generation'])
    store._atomic(root / 'install-conflicts.json', json.dumps(
        {'conflicts': conflicts, 'proposals': [e for e in entries if e['name'] in conflicts]},
        ensure_ascii=False, indent=2))
    return {'updated': [c['record']['name'] for c in changes], 'conflicts': conflicts}


def _body_hash(record):
    return store.digest({'source': record['source'], 'legacy': record.get('legacy')})


def _archive_legacy_inputs(root, metadata):
    """Only remove imported loose files after verifying the durable backup copy."""
    backup_root = Path(metadata['backup']) / 'data/workflows'
    for key in metadata['mapping']:
        if not key.startswith('workflow:'):
            continue
        name = key.removeprefix('workflow:') + '.yaml'
        path = root / name
        if not path.exists():
            continue
        archived = backup_root / name
        if path.is_symlink() or not archived.is_file() or path.read_bytes() != archived.read_bytes():
            raise ValueError(f'구형 입력이 백업과 다릅니다. 보존하고 이전을 중단합니다: {name}')
        path.unlink()
