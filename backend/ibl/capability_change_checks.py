"""Reuse the repository's build and test selectors, without a second test policy."""
import subprocess
import sys
import time
from pathlib import Path


def changed_files(root):
    result = subprocess.run(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'],
                            cwd=root, capture_output=True, check=True)
    entries = result.stdout.decode().split('\0')
    files = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        files.append(entry[3:])
        if 'R' in entry[:2] or 'C' in entry[:2]:
            files.append(entries[index])
            index += 1
    return sorted(set(files))


def check(root, files, *, prepare=False):
    root = Path(root)
    started = time.monotonic()
    if not files:
        return {'success': True, 'ok': True, 'items': [], 'files': [], 'behavior_verified': False}
    result = subprocess.run([sys.executable, str(root / 'scripts/select_tests.py'), '--files', *files],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        return {'success': True, 'ok': False, 'items': [], 'error_detail': result.stderr[-4000:]}
    selected = result.stdout.strip().split()
    steps = []
    if any(p.startswith(('data/ibl_nodes_src/', 'data/packages/')) for p in files):
        steps.append(('derive' if prepare else 'vocabulary', [sys.executable, 'scripts/build_ibl_nodes.py',
                     *([] if prepare else ['--check'])]))
    if any(p.startswith('backend/') and p.endswith('.py') for p in files):
        if prepare:
            steps.append(('body', [sys.executable, 'scripts/build_body_bundle.py', 'android']))
        else:
            steps.append(('layers', [sys.executable, 'scripts/check_backend_layers.py']))
    if selected and not prepare:
        steps.append(('tests', [sys.executable, '-m', 'pytest', *selected, '-n', 'auto', '--dist', 'loadfile']))
    items = []
    for name, argv in steps:
        tick = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=1800)
            items.append({'step': name, 'ok': proc.returncode == 0, 'exit_code': proc.returncode,
                          'seconds': round(time.monotonic() - tick, 3),
                          'summary': (proc.stdout + '\n' + proc.stderr)[-6000:]})
        except subprocess.TimeoutExpired:
            items.append({'step': name, 'ok': False, 'exit_code': None, 'summary': '검사 시간 초과'})
        if not items[-1]['ok']:
            break
    return {'success': True, 'ok': all(row['ok'] for row in items), 'items': items,
            'selection': result.stderr[-4000:], 'files': files,
            'seconds': round(time.monotonic() - started, 3), 'behavior_verified': False}
