#!/usr/bin/env python3
"""Reuse only successfully installed, unchanged dependency environments."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: F401,E402

import argparse
import hashlib
import json
import os
import shutil
import subprocess

from restart_protocol import atomic_json, read_json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def environment_stamp(directory):
    """Metadata inventory catches removal/replacement without hashing large binaries.

    Ignore interpreter caches, which ordinary app use writes. This is a reuse
    receipt, not an integrity/security attestation; explicit refresh is supported.
    """
    if not directory.is_dir():
        return None
    rows = []
    def unreadable(error):
        raise error

    for folder, dirs, files in os.walk(directory, onerror=unreadable):
        dirs[:] = sorted(d for d in dirs if d not in {'__pycache__', '.cache', '.vite', '.vite-temp', '.tmp'})
        for name in sorted(dirs + files):
            path = Path(folder) / name
            junction = getattr(path, 'is_junction', lambda: False)()
            if path.is_symlink() or junction:
                # External editable trees are not safely reusable by this receipt.
                resolved = path.resolve()
                if directory.resolve() not in resolved.parents and resolved != directory.resolve():
                    if resolved.is_dir():
                        return None
                stat = resolved.stat()
                rows.append((str(path.relative_to(directory)), str(resolved), stat.st_size, stat.st_mtime_ns))
                if junction and name in dirs:
                    dirs.remove(name)
            elif path.is_file() and path.suffix not in {'.pyc', '.pyo'}:
                stat = path.stat()
                rows.append((str(path.relative_to(directory)), stat.st_size, stat.st_mtime_ns))
    return digest(rows)


def configuration(root, group, npm):
    vpy = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python3')
    if group == 'python':
        files = sorted((root / 'backend').glob('requirements*.txt'))
        commands = [[str(vpy), '-m', 'pip', 'install', '-r', str(root / 'backend' / f'requirements-{name}.txt')]
                    for name in ('core', 'tools', 'ml')]
        commands.append([str(vpy), '-m', 'pip', 'check'])
        runtime = subprocess.check_output([str(vpy), '-c',
            'import sys; print(sys.version, sys.executable, sys.base_prefix)'], text=True, encoding='utf-8')
        environment = root / '.venv'
    else:
        frontend = root / 'frontend'
        files = [frontend / 'package.json', frontend / 'package-lock.json', frontend / '.npmrc']
        files += sorted((frontend / 'scripts').rglob('*'))
        files = [p for p in files if not p.is_dir()]
        node = shutil.which('node', path=str(Path(npm).parent))
        if not node:
            raise ValueError('Node must be beside npm')
        runtime = subprocess.check_output([node, '-p',
            'JSON.stringify({versions:process.versions,execPath:process.execPath,platform:process.platform,arch:process.arch})'],
            text=True, encoding='utf-8')
        runtime += subprocess.check_output([npm, '--version'], text=True, encoding='utf-8')
        commands = [[npm, 'ci', '--no-audit', '--no-fund'], [npm, 'run', 'rebuild-trusted']]
        environment = frontend / 'node_modules'
    contents = [(str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
                for p in files]
    # Arbitrary requirement includes/editable/local dependencies cannot be
    # described by the requirements files alone. Conservatively install them.
    reusable = group != 'python' or not any(
        line.strip().startswith(('-', '.', '/', 'file:')) or 'git+' in line
        for p in files for line in p.read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#'))
    return digest([1, str(root), group, runtime, contents]), commands, environment, reusable


def install(root, group, npm='', refresh=False):
    root = root.resolve()
    key, commands, environment, reusable = configuration(root, group, npm)
    receipt = root / 'data/runtime/remote_dependencies' / f'{group}.json'
    previous = read_json(receipt, {}) or {}
    stamp = environment_stamp(environment) if reusable and not refresh else None
    if stamp and previous.get('inputs') == key and previous.get('environment') == stamp:
        print(json.dumps({'group': group, 'status': 'reused', 'reason': 'inputs_and_environment_unchanged'}), flush=True)
        return
    # A failed install must not leave an older success receipt reusable.
    receipt.unlink(missing_ok=True)
    cwd = root if group == 'python' else root / 'frontend'
    for command in commands:
        print(json.dumps({'group': group, 'status': 'installing', 'command': command}), flush=True)
        subprocess.run(command, cwd=cwd, check=True)
    after, _, _, reusable = configuration(root, group, npm)
    if after != key:
        raise ValueError('Dependency inputs changed during installation; receipt not saved')
    stamp = environment_stamp(environment) if reusable else None
    if stamp:
        atomic_json(receipt, {'inputs': key, 'environment': stamp})
    print(json.dumps({'group': group, 'status': 'installed', 'reusable': bool(stamp)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=['python', 'node'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--npm', default='')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    try:
        install(args.root, args.group, args.npm, args.refresh)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
