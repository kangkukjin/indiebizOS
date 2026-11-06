"""Isolated filesystem projections for drafts and fixed source snapshots."""
import os
import shutil
from pathlib import Path

from coding_git import CodingConflict, safe_path
from code_analysis_changes import decode, decoded, identity
from coding_store import fingerprint, identifier
from lsp_positions import encode

SKIP = {'.git', '__pycache__', '_backups', '.pytest_cache', '.mypy_cache', 'analysis_runtime'}
DEPENDENCIES = {'node_modules', '.venv'}


def project_files(root, *, use_git=True):
    root = Path(root)
    import subprocess
    found = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                           capture_output=True, timeout=30) if use_git else None
    if found is not None and found.returncode == 0:
        for relative in sorted(set(found.stdout.decode().split('\0')) - {''}):
            if (root / relative).is_symlink():
                continue
            path = safe_path(root, relative)
            if path.is_file() and not path.is_symlink() and not any(p in SKIP | DEPENDENCIES for p in Path(relative).parts):
                yield relative, path
        return
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP | DEPENDENCIES and not (Path(folder) / d).is_symlink()]
        for name in files:
            path = Path(folder) / name
            if path.is_file() and not path.is_symlink():
                yield path.relative_to(root).as_posix(), path


def mirror(store, row, view, *, fixed=False):
    root = Path(row['path'])
    target = store.root / 'analysis_runtime' / view['id'] / 'source'
    if fixed and target.is_dir() and view.get('ready'):
        return target
    target.mkdir(parents=True, exist_ok=True)
    seen, evidence = set(), {}
    for relative, path in project_files(root):
        seen.add(relative)
        data = path.read_bytes()
        evidence[relative] = fingerprint(data)
        dest = safe_path(target, relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or dest.read_bytes() != data:
            dest.write_bytes(data)
            shutil.copymode(path, dest)
    for relative, path in project_files(target, use_git=False):
        if relative not in seen:
            path.unlink()
    # Dependencies are shared read-only by the language-server process boundary; source files are copied.
    for folder, dirs, _ in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and (d in DEPENDENCIES or not (Path(folder) / d).is_symlink())]
        for name in list(dirs):
            if name in DEPENDENCIES:
                relative = (Path(folder) / name).relative_to(root)
                dest = target / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    dest.symlink_to(root / relative, target_is_directory=True)
                dirs.remove(name)
    for relative, content in view.get('files', {}).items():
        dest = safe_path(target, relative)
        if content is None:
            dest.unlink(missing_ok=True)
        else:
            original = view['originals'][relative]
            encoding = decode(decoded(original['bytes']), relative)[1] if original['bytes'] is not None else 'utf-8'
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(encode(content, encoding))
    if fixed:
        current = {rel: fingerprint(path.read_bytes()) for rel, path in project_files(root)}
        if current != evidence:
            raise CodingConflict('스냅샷을 만드는 동안 원문이 바뀌었습니다')
        view.update(ready=True, evidence=evidence)
        store.save('code_snapshot', view)
    return target


def snapshot(store, row):
    view = {'id': identifier('codesnapshot'), 'project': row['id'], 'root_identity': identity(row['path']), 'files': {}, 'fixed': True}
    mirror(store, row, view, fixed=True)
    return view['id']
