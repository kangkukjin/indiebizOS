"""Immutable package programs and atomic publication, independent of worker generations."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import os
import subprocess
from functools import lru_cache

from restart_protocol import atomic_json
from program_boundary import protected_reason


def home(repo):
    return Path(repo) / 'data/restart_control/programs'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def package_id(value):
    if not isinstance(value, str) or not value or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in value):
        raise ValueError('Invalid package program id')
    return value


def source_inventory(root):
    root = Path(root)
    excluded = {'data', '__pycache__', '.git', 'node_modules', '.venv', '.pytest_cache'}
    paths = []
    repo = root.parents[4] if len(root.parents) > 4 else root
    if (repo / '.git').exists() and root.is_relative_to(repo / 'data/packages/installed/tools'):
        listing = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard',
                                  '--', root.relative_to(repo).as_posix()], cwd=repo, capture_output=True,
                                 check=True, timeout=30)
        paths = [repo / os.fsdecode(p) for p in listing.stdout.split(b'\0') if p]
    else:
        for directory, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in excluded and not (Path(directory) / d).is_symlink()]
            paths.extend(Path(directory) / n for n in names)
    result = {}
    for path in sorted(paths):
        rel = path.relative_to(root)
        if set(rel.parts) & excluded or path.is_symlink() or not path.is_file():
            continue
        if path.suffix in {'.db', '.sqlite', '.sqlite3', '.pyc', '.log'} or path.name.startswith('.env'):
            continue
        stat = path.stat()
        stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        result[rel.as_posix()] = _file_hash(str(path), stamp)
    return result


@lru_cache(maxsize=32768)
def _file_hash(path, stamp):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(repo, package, source, *, code_root=None):
    """Copy code/assets, never copy runtime state or secrets."""
    package = package_id(package)
    source = Path(source)
    files = source_inventory(source)
    version = digest(files)
    destination = home(repo) / 'objects' / package / version
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            temp = Path(temporary)
            package_root = temp / 'data/packages/installed/tools' / package
            for rel in files:
                target = package_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / rel, target)
            if source_inventory(source) != files or source_inventory(package_root) != files:
                raise ValueError('Program changed during snapshot')
            _view(temp, Path(repo), Path(code_root or repo), package)
            atomic_json(temp / 'manifest.json', {'package': package, 'version': version, 'files': files})
            # Atomic directory rename; the surrounding application lock owns publication.
            temp.rename(destination)
    return {'package': package, 'version': version, 'files': files}


def _view(target, repo, code, package):
    """Preserve __file__-relative repository shape without copying live data."""
    def link_children(source, destination, excluded=()):
        destination.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            for child in source.iterdir():
                link = destination / child.name
                if child.name not in excluded and not link.exists():
                    link.symlink_to(child.resolve(), target_is_directory=child.is_dir())
    link_children(code, target, {'.git', '.worktrees', 'data'})
    link_children(repo / 'data', target / 'data', {'packages', 'restart_control'})
    link_children(code / 'data/packages', target / 'data/packages', {'installed'})
    link_children(code / 'data/packages/installed', target / 'data/packages/installed', {'tools'})
    link_children(code / 'data/packages/installed/tools', target / 'data/packages/installed/tools', {package})
    state = repo / 'data/packages/installed/tools' / package / 'data'
    if state.is_dir():
        (target / 'data/packages/installed/tools' / package / 'data').symlink_to(state, target_is_directory=True)


def read(repo):
    path = home(repo) / 'active.json'
    return json.loads(path.read_bytes()) if path.is_file() else {}


def publish(repo, manifest, baseline, receipt):
    package = package_id(manifest['package'])
    prefix = 'data/packages/installed/tools/' + package + '/'
    changed = {p for p in baseline.keys() | manifest['files'].keys() if baseline.get(p) != manifest['files'].get(p)}
    protected = {p: protected_reason(prefix + p) for p in changed if protected_reason(prefix + p)}
    if protected:
        raise PermissionError('Program cannot change protected contracts: ' + ', '.join(protected))
    rows = read(repo)
    previous = rows.get(package)
    rows[package] = {**manifest, 'baseline': baseline, 'receipt': receipt,
                     'previous': previous.get('version') if previous else None}
    atomic_json(home(repo) / 'active.json', rows)
    return rows[package]


def selected(repo, package, baseline_root):
    """Only exact, published live bytes may supersede a sealed baseline."""
    package = package_id(package)
    from program_publication import selected as module_selected
    prefix = 'data/packages/installed/tools/' + package
    baseline_root = Path(baseline_root)
    code = baseline_root.parents[4]
    module_root, publication = module_selected(repo, code)
    if publication and any(p.startswith(prefix + '/') for p in publication['files']):
        from program_publication import package_files
        files = package_files(repo, code, publication, package)
        if not any(protected_reason(prefix + '/' + p) for p in files if p.endswith('.py')):
            return module_root / prefix, {'package': package, 'version': digest(files), 'files': files}
    row = read(repo).get(package)
    if not row:
        return Path(baseline_root), None
    if not isinstance(row.get('version'), str) or len(row['version']) != 64 or any(
            c not in '0123456789abcdef' for c in row['version']):
        raise ValueError('Invalid published program version')
    baseline = source_inventory(baseline_root)
    live = source_inventory(Path(repo) / 'data/packages/installed/tools' / package)
    if baseline not in (row['baseline'], row['files']) or live != row['files']:
        return Path(baseline_root), None
    root = home(repo) / 'objects' / package / row['version'] / 'data/packages/installed/tools' / package
    files = source_inventory(root)
    if files != row['files'] or digest(files) != row['version']:
        raise ValueError('Published program object is corrupt')
    return root, row


def covers_changes(repo, code_root, changes, inventory):
    """Watcher exemption requires verified source bytes, not an agent's label."""
    covered = set()
    for package, row in read(repo).items():
        prefix = 'data/packages/installed/tools/' + package + '/'
        relevant = {p for p in changes if p.startswith(prefix)}
        if not relevant:
            continue
        _, selected_row = selected(repo, package, Path(code_root) / prefix)
        if selected_row and all(inventory.get(p) == row['files'].get(p[len(prefix):]) for p in relevant):
            covered.update(relevant)
    return covered


def activation_matches(repo, code_root, session):
    if session.get('module_publication'):
        from program_publication import activation_matches as module_matches
        return module_matches(repo, code_root, session)
    entries = session.get('program_activation') or []
    if not entries or any(r.get('activation') != 'active' for r in entries):
        return False
    for entry in entries:
        manifest = entry['manifest']
        prefix = 'data/packages/installed/tools/' + manifest['package']
        _, row = selected(repo, manifest['package'], Path(code_root) / prefix)
        if not row or row['version'] != manifest['version'] or row.get('receipt', {}).get('session') != session['key']:
            return False
        for rel, item in session.get('sealed', {}).items():
            if rel.startswith(prefix + '/') and manifest['files'].get(rel[len(prefix) + 1:]) != (item.get('after') or {}).get('sha'):
                return False
    return True
