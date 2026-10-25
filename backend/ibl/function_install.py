"""Install current shipped functions through the compiler-owned catalog gate."""
import json
import uuid
from pathlib import Path
import yaml
import function_store as store


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
        edition = data.get('edition') if data is not None else 2
        source = (data.get('code', '').strip() if data is not None else path.read_text().strip())
        from ibl_edition import require_current
        require_current(source, edition)
        from ibl_v2_store import definition_name
        if definition_name(source) != name:
            raise ValueError('배포 이름과 정의 머리가 다릅니다.')
        entry = {'key': 'installed:' + filename, 'name': name, 'edition': edition,
                 'source': source, 'description': (data or {}).get('description', ''),
                 'origin': 'core', 'provenance': {'installed_file': filename}}
        if data is not None:
            entry['legacy_ids'] = [path.stem]
        result.append(entry)
    descriptions = installed_descriptions({e['name']: e['source'] for e in result}, root)
    for entry in result:
        entry['description'] = descriptions.get(entry['name'], entry['description'])
    return result


def install(base):
    """Fresh install/update through the same gate; personal revisions are retained."""
    root = Path(base) / 'data' / 'workflows'
    entries = installed_sources(base)
    if not entries:
        return {'updated': [], 'conflicts': []}
    prepared = prepare(entries, root=root)
    view = store.snapshot(root)
    changes, conflicts = [], []
    for change in prepared['changes']:
        record = change['record']
        old = store.resolve(record['name'], root=root, view=view, include_inactive=True)
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


def prepare(entries, *, root=None):
    changes = []
    scope = store.catalog(root)['scope_id']
    for entry in entries:
        fid = uuid.uuid5(uuid.NAMESPACE_URL, 'indiebiz:function:' + entry['key']).hex
        record = {k: entry[k] for k in ('name', 'edition', 'source', 'description', 'origin')}
        record.update(schema=1, scope_id=scope, function_id=fid, source_hash=store.digest(entry['source']),
                      provenance={'imports': [entry['key']], 'evidence': [entry.get('provenance', {})]})
        record['installation_source_hash'] = _body_hash(record)
        changes.append({'record': record, 'expected_revision': None, 'state': 'active',
                        'legacy_ids': entry.get('legacy_ids', [])})
    return {'changes': changes}
