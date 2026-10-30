"""순수 부품의 등록·불변 판본·게시 원장. 제어자도 이 작은 계약만 읽는다."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from restart_protocol import atomic_json


def strict_json(data):
    return json.loads(data)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def registry(code_root):
    """등록/검사 계약은 현재 봉인 세대가 소유한다. 후보가 수정할 수 없다."""
    root = Path(code_root).resolve()
    entries = {}
    for path in sorted((root / 'data/packages/installed/tools').glob('*/runtime_components.json')):
        for spec in strict_json(path.read_bytes()):
            source = spec['source']
            if (spec.get('protocol') != 'pure-json/1'
                    or Path(source).is_absolute() or '..' in Path(source).parts
                    or not source.startswith('data/packages/installed/tools/')
                    or not source.endswith('.py') or spec['id'] in entries):
                raise ValueError('잘못된 부품 등록')
            entries[spec['id']] = {**spec, 'contract_hash': sha(json.dumps(spec, sort_keys=True).encode()),
                                   'baseline_version': sha((root / source).read_bytes())}
    return entries


def handler_fingerprint(pkg_dir):
    """허브 권한 코드는 전수 해시. 제한 자식의 소스 대신 보호된 등록/검사 계약을 해시한다."""
    pkg = Path(pkg_dir)
    manifest = pkg / 'runtime_components.json'
    isolated = set()
    if manifest.exists():
        for spec in strict_json(manifest.read_bytes()):
            source = Path(spec['source'])
            prefix = Path('data/packages/installed/tools') / pkg.name
            if (spec.get('protocol') != 'pure-json/1' or not source.is_relative_to(prefix)
                    or '..' in source.parts or source.name == 'handler.py'):
                raise ValueError('순수 부품 등록 경계가 유효하지 않습니다')
            isolated.add(source.relative_to(prefix).as_posix())
    h = hashlib.sha256()
    for path in sorted(pkg.rglob('*.py')):
        rel = path.relative_to(pkg).as_posix()
        if '__pycache__' in path.parts or path.name.startswith('test_') or rel in isolated:
            continue
        h.update(rel.encode()); h.update(b'\0'); h.update(path.read_bytes()); h.update(b'\0')
    if manifest.exists():
        h.update(b'runtime_components.json\0'); h.update(manifest.read_bytes()); h.update(b'\0')
    return h.hexdigest()[:16]


def home(repo):
    return Path(repo) / 'data/restart_control/components'


def active(repo, spec):
    path = home(repo) / 'active.json'
    rows = strict_json(path.read_bytes()) if path.exists() else {}
    row = rows.get(spec['id'])
    if row and row.get('contract_hash') == spec['contract_hash']:
        return row
    return None


def object_path(repo, version):
    if len(version) != 64 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('잘못된 부품 판본')
    return home(repo) / 'objects' / (version + '.py')


def store_object(repo, source):
    version = sha(source)
    path = object_path(repo, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            f.write(source)
            f.flush()
            os.fsync(f.fileno())
        os.replace(f.name, path)
    if path.read_bytes() != source:
        raise ValueError('부품 소스 객체 손상')
    return version


def publish(repo, spec, version, *, receipt):
    if sha(object_path(repo, version).read_bytes()) != version:
        raise ValueError('게시할 부품 판본 손상')
    path = home(repo) / 'active.json'
    rows = strict_json(path.read_bytes()) if path.exists() else {}
    rows[spec['id']] = {'version': version, 'source': spec['source'],
                        'contract_hash': spec['contract_hash'], 'receipt': receipt,
                        'baseline_version': spec['baseline_version']}
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, rows)


def active_source(repo, code_root, spec):
    selected = active(repo, spec)
    baseline = (Path(code_root) / spec['source']).read_bytes()
    if selected and sha(baseline) in {selected['version'], selected.get('baseline_version')}:
        data = object_path(repo, selected['version']).read_bytes()
        if sha(data) != selected['version']:
            raise ValueError('활성 부품 판본 손상')
        # 정본을 되돌렸을 때도 부분 판본이 그 편집을 가리지 않는다.
        # 미검증 정본은 실행하지 않고 현재 봉인 세대의 구현으로 돌아간다.
        live = Path(repo) / spec['source']
        if live.is_file() and sha(live.read_bytes()) == selected['version']:
            return data
    return baseline


def covers_changes(repo, code_root, changes, inventory):
    """세대 감시자는 실제 게시된 동일 바이트만 부분 활성화로 인정한다."""
    try:
        return _covers_changes(repo, code_root, changes, inventory)
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _covers_changes(repo, code_root, changes, inventory):
    covered = set()
    for spec in registry(code_root).values():
        row = active(repo, spec)
        if row and row['source'] in changes and inventory.get(row['source']) == row['version']:
            path = object_path(repo, row['version'])
            if path.is_file() and sha(path.read_bytes()) == row['version']:
                covered.add(row['source'])
    return bool(changes) and changes <= covered
