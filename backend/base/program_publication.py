"""Verified sparse code/catalog publications, separate from host generations.

Only the trusted repair gate creates these records after candidate validation.
Readers require the exact baseline, live bytes and immutable object hashes.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import shutil

from program_boundary import canonical, change
from program_versions import home, digest, _file_hash
from restart_protocol import atomic_json


def read(repo):
    path = home(repo) / 'modules.json'
    return json.loads(path.read_bytes()) if path.is_file() else {}


def file_hash(path):
    path = Path(path)
    if not path.is_file():
        return None
    st = path.stat()
    return _file_hash(str(path), (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))


def snapshot(repo, code, session):
    previous = read(repo)
    if previous.get('activation') != 'active':
        previous = previous.get('previous_active', {})
    files = dict(previous.get('files', {})) if compatible(previous, code) else {}
    before = dict(previous.get('baseline', {})) if files else {}
    work = Path(repo) / session['worktree']
    for relative, item in session['sealed'].items():
        if item.get('artifact'):
            continue
        if not canonical(relative):
            raise ValueError('Noncanonical program path')
        owner = change(relative, item.get('before'), item.get('after'),
                       managed=session.get('managed_files'), derived=session.get('derived_files'))
        if not owner or owner['route'] != 'workspace':
            raise PermissionError('Protected program path: ' + relative)
        files[relative] = (item.get('after') or {}).get('sha')
        before.setdefault(relative, file_hash(Path(code) / relative))
    version = digest(files)
    destination = home(repo) / 'module_objects' / version
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
            root = Path(tmp)
            for relative, sha in files.items():
                if sha is None:
                    continue
                source = work / relative if relative in session['sealed'] else object_root(repo, previous) / relative
                if file_hash(source) != sha:
                    raise ValueError('Program snapshot changed: ' + relative)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            _view(root, Path(code), files)
            root.rename(destination)
    row = {'version': version, 'files': files, 'baseline': before,
           'receipt': {'session': session['key']}, 'activation': 'prepared',
           'previous_active': {k: v for k, v in previous.items() if k != 'previous_active'},
           'owners': {**previous.get('owners', {}), **{p: session['key'] for p, i in session['sealed'].items() if not i.get('artifact')}}}
    verify_object(repo, row)
    return row


def _view(root, code, files):
    """Sparse overlay. Deleted paths stay absent, unchanged code stays sealed."""
    def populate(destination, source, prefix=''):
        if not source.is_dir():
            return
        for child in source.iterdir():
            relative = prefix + child.name
            target = destination / child.name
            if child.name in {'.git', '.worktrees', '.venv', '__pycache__', 'restart_control', '_code_data'}:
                continue
            if relative in files:
                continue
            nested = any(p.startswith(relative + '/') for p in files)
            if nested:
                target.mkdir(parents=True, exist_ok=True)
                populate(target, code / '_code_data' if relative == 'data' and (code / '_code_data').is_dir() else child, relative + '/')
            elif not target.exists():
                target.symlink_to(child.resolve(), target_is_directory=child.is_dir())
    populate(root, code)
    if (code / '_code_data').is_dir():
        (root / '_code_data').symlink_to('data', target_is_directory=True)


def object_root(repo, row):
    version = row.get('version', '')
    if len(version) != 64 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('Invalid module publication version')
    return home(repo) / 'module_objects' / version


def compatible(row, code):
    return bool(row) and all(file_hash(Path(code) / p) in (sha, row['files'].get(p))
                             for p, sha in row.get('baseline', {}).items())


def verify_object(repo, row):
    root = object_root(repo, row)
    if digest(row['files']) != row['version'] or any(file_hash(root / p) != sha for p, sha in row['files'].items()):
        raise ValueError('Published module object is corrupt')
    return root


def selected(repo, code):
    row = read(repo)
    pending = row.get('activation') != 'active'
    if pending:
        row = row.get('previous_active', {})
    if not compatible(row, code):
        return Path(code), None
    root = verify_object(repo, row)
    # A fresh generation already containing every published byte supersedes the
    # sparse overlay. Do not retain symlinks to a retired generation forever.
    from generation_store import sealed, _excluded
    generation = sealed(code)
    if all((generation and _excluded(p)) or file_hash(Path(code) / p) == sha
           for p, sha in row['files'].items()):
        return Path(code), row
    return root, row


def selected_path(repo, code, relative):
    root, _ = selected(repo, code)
    return root / relative


def publish(repo, row):
    verify_object(repo, row)
    atomic_json(home(repo) / 'modules.json', row)


def covers_changes(repo, code, changes, inventory):
    row = read(repo)
    if not compatible(row, code):
        return set()
    verify_object(repo, row)
    if not row:
        return set()
    return {p for p in changes if p in row['files'] and inventory.get(p) == row['files'][p]}


def activation_matches(repo, code, session):
    root, row = selected(repo, code)
    if not row or row.get('activation') != 'active':
        return False
    from generation_store import sealed, _excluded
    generation = sealed(root)
    return all(row.get('owners', {}).get(p) == session['key'] and
               file_hash(Path(repo) / p) == (item.get('after') or {}).get('sha') and
               (file_hash(root / p) == (item.get('after') or {}).get('sha') or
                generation and _excluded(p) and row['files'].get(p) == (item.get('after') or {}).get('sha'))
               for p, item in session.get('sealed', {}).items() if not item.get('artifact'))


def package_files(repo, code, row, package):
    """Overlay symlinks represent sealed files, including unchanged core gates."""
    from program_versions import source_inventory
    prefix = 'data/packages/installed/tools/' + package + '/'
    files = source_inventory(Path(code) / prefix)
    for relative, sha in row['files'].items():
        if relative.startswith(prefix):
            local = relative[len(prefix):]
            if sha is None:
                files.pop(local, None)
            else:
                files[local] = sha
    return files
