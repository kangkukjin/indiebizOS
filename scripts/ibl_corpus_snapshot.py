"""Private, consistent-per-store corpus snapshots; never changes source data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone


def sha(value):
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def connect(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def source_files(root):
    patterns = [
        'data/training/*.json', 'data/idioms/**/*', 'data/workflows/**/*',
        'data/hippocampus_tree/**/*', 'data/guides/*.md',
        'data/common_prompts/**/*', 'data/ibl_nodes_src/*.yaml',
        'data/system_docs/ibl.md', 'data/system_docs/vision.md',
        'data/packages/installed/tools/**/tool.json',
        'data/packages/installed/tools/**/ibl_actions.yaml',
        'data/packages/installed/tools/**/package.json',
        'data/scripts/*.py', 'data/scripts/*.ibl', 'data/scripts/registry.yaml',
        'data/vocabulary/activation.json', 'data/ibl_nodes.yaml',
        'data/api_registry.yaml', 'data/calendar_events.json',
        'data/event_triggers.json', 'data/webapps.json', 'data/member_apps.yaml',
        'data/models/ibl_embedding/config.json',
        'data/models/ibl_embedding/modules.json',
        'backend/ibl/*.py', 'backend/base/ibl_edition.py',
        'backend/common/value_semantics.py',
        'backend/datastore/ibl_registry.py',
    ]
    return sorted({p for pattern in patterns for p in root.glob(pattern)
                   if p.is_file() and '__pycache__' not in p.parts})


def snapshot(root=ROOT):
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S_ibl_corpus_audit')
    dest = root / 'data/_backups' / stamp
    dest.mkdir(parents=True, exist_ok=False)
    manifest = {'version': 1, 'started_at': now(), 'root': str(root),
                'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                'files': [], 'databases': [], 'errors': [],
                'consistency': 'Each SQLite backup is consistent; cross-store drift must be reconciled.'}
    for name in ('ibl_usage.db', 'world_pulse.db', 'triggers.db'):
        src, target = root / 'data' / name, dest / 'data' / name
        if not src.exists():
            manifest['errors'].append({'source': str(src.relative_to(root)), 'kind': 'missing_database'})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        start = now()
        with connect(src) as original, sqlite3.connect(target) as copied:
            original.backup(copied, pages=256)
            check = copied.execute('PRAGMA quick_check').fetchall()
            if check != [('ok',)]:
                raise ValueError(f'Snapshot integrity failure: {name}')
        manifest['databases'].append({'path': str(src.relative_to(root)),
                                      'started_at': start, 'ended_at': now(),
                                      'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size})
    for src in source_files(root):
        relative = src.relative_to(root)
        if src.is_symlink():
            manifest['errors'].append({'source': str(relative), 'kind': 'symlink_not_copied'})
            continue
        try:
            raw = src.read_bytes()
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            manifest['files'].append({'path': str(relative), 'sha256': sha(raw),
                                      'bytes': len(raw), 'captured_at': now(),
                                      'changed_during_copy': sha(src.read_bytes()) != sha(raw)})
        except OSError as exc:
            manifest['errors'].append({'source': str(relative), 'kind': type(exc).__name__})
    # Pin model identity without copying hundreds of megabytes or loading it.
    manifest['model'] = [{'path': str(p.relative_to(root)), 'bytes': p.stat().st_size,
                          'sha256': sha(p.read_bytes())}
                         for p in sorted((root / 'data/models/ibl_embedding').glob('*.safetensors'))]
    manifest['ended_at'] = now()
    dump(dest / 'manifest.json', manifest)
    return dest


if __name__ == '__main__':
    print(snapshot())
