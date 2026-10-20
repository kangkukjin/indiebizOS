"""수명 원장의 현재 정의 관측. 원문·자격증명은 복제하지 않고 로컬 구현 지문만 만든다.

동적 호출을 정규식으로 해석하지 않는다. 공통 backend와 스크립트/관용구의 호출 가능
영역은 보수적으로 묶는다. 의존 변경과 항목 자체의 구현 변경은 별도 지문이다.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

import yaml


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    default=str).encode()).hexdigest()


def _mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label}: 객체 형식이어야 합니다.')
    return value


def _yaml(path):
    value = yaml.safe_load(path.read_text(encoding='utf-8')) if path.is_file() else {}
    return _mapping(value if value is not None else {}, path.name)


def _json(path):
    return _mapping(json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}, path.name)


def _files(root, paths):
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(set(paths)) if p.is_file()})


def _code_files(root):
    return [p for p in root.rglob('*.py') if '__pycache__' not in p.parts
            and not p.name.startswith('test_') and p.name != 'conftest.py']


def _readonly(path):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _entry(kind, name, definition, dependencies, *, created_at=None, metadata=None):
    implementation = digest(definition)
    return {'kind': kind, 'name': name, 'implementation_revision': implementation,
            'dependency_revision': dependencies, 'revision': digest([implementation, dependencies]),
            'created_at': created_at, 'metadata': metadata or {}}


def collect(root):
    root = Path(root)
    data = root / 'data'
    catalog = _yaml(data / 'ibl_nodes.yaml') or {}
    if not isinstance(catalog.get('nodes'), dict):
        raise ValueError('어휘 사전이 없거나 손상되었습니다. 기존 수명 원장은 변경하지 않습니다.')
    # 소스 지문은 파일 이동에도 재현 가능하도록 몸 상대 경로를 쓴다.
    backend_dir = root / 'backend'
    if not backend_dir.is_dir():  # 배포 몸은 사용자 데이터와 엔진 자원이 분리된다.
        backend_dir = Path(__file__).resolve().parents[1]
    backend = digest([_files(backend_dir, _code_files(backend_dir) +
                             list(backend_dir.glob('requirements*.txt'))),
                      _files(root, list(root.glob('requirements*.txt')) + [data / 'api_registry.yaml'])])
    packages = {}
    owners = _mapping(_json(data / 'package_meta.json').get('action_owner', {}), 'action_owner')
    for base in (data / 'packages/installed/tools', data / 'packages/installed/extensions'):
        if not base.is_dir():
            continue
        for directory in sorted(base.iterdir()):
            if directory.is_dir():
                packages[directory.name] = (directory, _files(root, _code_files(directory) +
                    [directory / 'tool.json'] + list(directory.glob('requirements*.txt'))))
    package_realm = digest({name: fingerprint for name, (_, fingerprint) in packages.items()})
    source_realm = _files(root, list((data / 'ibl_nodes_src').glob('*.yaml')) +
                          list((data / 'packages/installed').rglob('ibl_actions.yaml')))
    runtime = digest([backend, package_realm, source_realm, catalog])
    review = _mapping(_json(data / 'ibl_example_review.json').get('actions', {}), 'example review')
    items = {}
    for node, cfg in catalog['nodes'].items():
        actions = _mapping(_mapping(cfg, node).get('actions') or {}, f'{node}.actions')
        for action, declaration in actions.items():
            _mapping(declaration, f'{node}:{action}')
            name = f'{node}:{action}'
            package = packages.get(owners.get(name))
            source = package[0] / 'ibl_actions.yaml' if package else data / 'ibl_nodes_src' / f'{node}.yaml'
            definition = {'declaration': declaration, 'source': _files(root, [source]),
                          'package': package[1] if package else None}
            items[f'action:{name}'] = _entry('action', name, definition, backend, metadata={
                'source': str(source.relative_to(root)), 'fingerprint_scope': 'declaration + source fragment + package Python; backend dependency realm',
                'legacy_example_reviewed_at': _mapping(review.get(name, {}), name).get('reviewed'),
                'legacy_path_audited': declaration.get('path_audited'),
                'external_state_covered': False})

    registry = _yaml(data / 'scripts/registry.yaml') or {}
    if not isinstance(registry, dict):
        raise ValueError('스크립트 등록부가 손상되었습니다.')
    scripts = {}
    for sid, entry in registry.items():
        _mapping(entry, f'script:{sid}')
        path = data / 'scripts' / str(entry.get('file') or '')
        # 날짜/실행/자동 정리 표지는 정의 버전의 재료가 아니다.
        definition = {k: entry.get(k) for k in ('file', 'interpreter', 'description', 'timeout', 'callable_contract')}
        definition['source_hash'] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'
        scripts[sid] = definition
        items[f'script:{sid}'] = _entry('script', sid, definition, '', created_at=entry.get('created_at'), metadata={
            'source': str(path.relative_to(root)), 'source_missing': not path.is_file(),
            'legacy_registered_at': entry.get('registered_at'),
            'fingerprint_scope': 'script definition + local script namespace and body dependencies',
            'external_state_covered': False})
    script_files = [p for p in (data / 'scripts').rglob('*') if p.is_file()
                    and p.suffix in {'.py', '.sh', '.js', '.ibl'} and '__pycache__' not in p.parts]
    script_realm = digest([scripts, _files(root, script_files)])

    idioms = {}
    usage = data / 'ibl_usage.db'
    if usage.is_file():
        conn = _readonly(usage)
        try:
            for row in conn.execute("SELECT * FROM ibl_examples WHERE COALESCE(alias,'') != ''"):
                row = dict(row)
                key = f"idiom:db:{row['id']}"
                definition = {k: row.get(k) for k in ('alias', 'ibl_code', 'intent', 'signature', 'returns')}
                idioms[key] = definition
                items[key] = _entry('idiom', row['alias'], definition, '', created_at=row.get('created_at'), metadata={
                    'source': f"data/ibl_usage.db#ibl_examples/{row['id']}",
                    'legacy_updated_at': row.get('updated_at'), 'external_state_covered': False})
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='ibl_idiom_revisions'").fetchone():
                for row in conn.execute('SELECT example_id,MAX(revised_at) AS at FROM ibl_idiom_revisions GROUP BY example_id'):
                    key = f"idiom:db:{row['example_id']}"
                    if key in items:
                        items[key]['metadata']['legacy_revised_at'] = row['at']
        finally:
            conn.close()
    for path in sorted((data / 'workflows').glob('*.yaml')):
        entry = _yaml(path)
        if not isinstance(entry, dict) or entry.get('edition') != 2:
            continue
        key = f'idiom:workflow:{path.stem}'
        definition = {k: entry.get(k) for k in ('name', 'code', 'description', 'edition', 'capability_contract')}
        idioms[key] = definition
        items[key] = _entry('idiom', entry.get('name') or path.stem, definition, '', metadata={
            'source': str(path.relative_to(root)), 'external_state_covered': False})
    for name, filename in (_json(data / 'idioms/installed.json') or {}).items():
        if not isinstance(filename, str):
            raise ValueError('배포 관용구 파일명은 문자열이어야 합니다.')
        path = data / 'idioms' / filename
        if path.is_symlink() or path.parent != data / 'idioms' or path.suffix != '.ibl':
            raise ValueError('배포 관용구 경로 오류')
        definition = path.read_text(encoding='utf-8')
        key = f'idiom:installed:{name}'
        idioms[key] = definition
        items[key] = _entry('idiom', name, definition, '', metadata={
            'source': str(path.relative_to(root)), 'external_state_covered': False})
    # 스크립트/관용구는 동적으로 서로를 호출할 수 있다. 정의 카탈로그의 보수적 폐포.
    dependencies = digest([runtime, script_realm, idioms])
    for item in items.values():
        if item['kind'] in {'script', 'idiom'}:
            item['dependency_revision'] = dependencies
            item['revision'] = digest([item['implementation_revision'], dependencies])
            item['metadata']['dependency_scope'] = 'local body + scripts + named idioms (conservative)'
    return items


def executions(root):
    """기존 실행 기록의 읽기 투영. 과거 updated_at을 실행 시각으로 추정하지 않는다."""
    root = Path(root)
    result, errors = {}, []
    path = root / 'data/world_pulse.db'
    if path.is_file():
        try:
            from pulse_db import NOT_ISOLATED_SQL
            conn = _readonly(path)
            try:
                for row in conn.execute(f'''SELECT node,action,MAX(timestamp) AS at FROM action_health
                        WHERE source='usage' AND {NOT_ISOLATED_SQL} GROUP BY node,action'''):
                    result[f"action:{row['node']}:{row['action']}"] = {
                        'at': row['at'], 'source': 'action_health:usage', 'revision': None}
            finally:
                conn.close()
        except sqlite3.Error as exc:
            errors.append({'source': 'action_health', 'error': str(exc)})
    try:
        for sid, state in (_json(root / 'data/scripts.json') or {}).items():
            run = state.get('last_run') or {}
            if run.get('at'):
                result[f'script:{sid}'] = {'at': run['at'], 'success': run.get('ok'),
                                          'source': 'scripts.json:last_run', 'revision': None}
    except (ValueError, AttributeError) as exc:
        errors.append({'source': 'scripts.json', 'error': str(exc)})
    return result, errors
