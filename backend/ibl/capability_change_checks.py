"""Reuse the repository's build and test selectors, without a second test policy."""
import hashlib
import os
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


def _run(root, argv, deadline, cancel):
    """선택기부터 검사까지 같은 대기 한도·취소와 자식 트리 정리를 사용한다."""
    from script_process import run_process
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(argv, 0)
    def check_cancel():
        if cancel and cancel():
            raise PermissionError('능력 변경 검사가 중단됐습니다. 남은 업무와 기존 후보를 보존하세요.')
    result = run_process(argv, b'', cwd=str(root), env=dict(os.environ), timeout=remaining,
                         check=check_cancel, terminate_descendants=True)
    if result['timed_out']:
        raise subprocess.TimeoutExpired(argv, remaining, result.get('stdout'), result.get('stderr'))
    return subprocess.CompletedProcess(argv, result['exit_code'], result.get('stdout', ''), result.get('stderr', ''))


def check(root, files, *, prepare=False, plan_only=False, timeout=1800):
    root = Path(root).resolve()
    files = sorted(set(files))
    for name in files:
        if not (root / name).resolve().is_relative_to(root) or Path(name).is_absolute():
            raise ValueError('검사 파일은 현재 저장소의 상대경로여야 합니다.')
    def snapshot():
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                if (root / name).is_file() else None for name in files}
    before = snapshot()
    started = time.monotonic()
    deadline = started + timeout
    from execution_turn import current
    turn = current()
    cancel = turn.cancel_check if turn else None
    if not files:
        return {'success': True, 'ok': True, 'items': [], 'files': [], 'behavior_verified': False}
    try:
        result = _run(root, [sys.executable, str(root / 'scripts/select_tests.py'), '--files', *files],
                      deadline, cancel)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {'success': True, 'ok': False, 'items': [{'step': 'selection', 'ok': False,
                'summary': str(exc)}], 'files': files, 'behavior_verified': False}
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
    if plan_only:
        return {'success': True, 'ok': before == snapshot(), 'files': files, 'behavior_verified': False,
                'plan_only': True, 'steps': [{'step': name, 'argv': argv} for name, argv in steps],
                'selected_tests': selected, 'selection': result.stderr[-4000:],
                'full_regression': selected == ['backend/'],
                'activation': '기존 소유자의 apply 경로에서 확인; 계획 조회는 반영·활성화를 수행하지 않음',
                'maintenance': '공개 계약·설명 변경 시 기존 어휘 체크리스트의 교재·용례·번역 정비 확인',
                'estimated_seconds': None}
    items = []
    for name, argv in steps:
        tick = time.monotonic()
        try:
            proc = _run(root, argv, deadline, cancel)
            items.append({'step': name, 'ok': proc.returncode == 0, 'exit_code': proc.returncode,
                          'seconds': round(time.monotonic() - tick, 3),
                          'summary': (proc.stdout + '\n' + proc.stderr)[-6000:]})
        except (subprocess.TimeoutExpired, OSError) as exc:
            items.append({'step': name, 'ok': False, 'exit_code': None, 'summary': str(exc)})
        if not items[-1]['ok']:
            break
    after = snapshot()
    return {'success': True, 'ok': all(row['ok'] for row in items) and (prepare or before == after), 'items': items,
            'candidate_before': before, 'candidate_after': after, 'candidate_changed': before != after,
            'selection': result.stderr[-4000:], 'files': files,
            'seconds': round(time.monotonic() - started, 3), 'behavior_verified': False}
