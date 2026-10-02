"""Printable-form acceptance and isolated, path-scoped activation.

The shared follow-up verifier may carry another repair's edits. Keep this
phase independent so activation never commits or overwrites those edits.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

PATHS = [
    'backend/services/spreadsheet_templates.py',
    'backend/test_spreadsheet_print_live.py',
    'scripts/verify_spreadsheet_print.py',
    'docs/SPREADSHEET_APP_DESIGN_2026_10_02.md',
    'data/bodies/android.engine.json', 'data/core_manifest.json',
]


def checks(args):
    env = {**os.environ, 'INDIEBIZ_OFFICE_LIVE_TEST': '1',
           'PYTHONPATH': str(ROOT / 'backend')}
    mode = args.get('mode', 'live')
    commands = {
        'live': [[sys.executable, '-m', 'pytest',
                  'backend/test_spreadsheet_print_live.py', '-s', '--tb=short']],
        'manual': [[sys.executable, '-m', 'pytest',
                    'backend/test_spreadsheet_print_live.py', '-k', 'manual', '-s', '--tb=short']],
        'structure': [[sys.executable, '-m', 'pytest',
                       'backend/test_spreadsheet_print_live.py', '-k', 'structure', '-s', '--tb=short']],
        'multipage': [[sys.executable, '-m', 'pytest',
                       'backend/test_spreadsheet_print_live.py', '-k', 'multipage', '-s', '--tb=short']],
        'build': [['npx', '--no-install', 'tsc', '-p', 'tsconfig.app.json'],
                  ['npx', '--no-install', 'vite', 'build']],
    }
    if mode not in commands:
        raise ValueError('지원하지 않는 인쇄 검사 모드')
    results = []
    for command in commands[mode]:
        result = subprocess.run(command, cwd=ROOT / 'frontend' if mode == 'build' else ROOT,
                                env=env, capture_output=True, text=True, timeout=600)
        results.append({'command': command, 'exit_code': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    ok = all(row['exit_code'] == 0 for row in results)
    return {'ok': ok, 'items': results,
            'operation_outcome': {'status': 'passed' if ok else 'failed',
                                  'message': '인쇄 검사 통과' if ok else '인쇄 검사 실패'}}


def activate():
    import verify_spreadsheet_app as base
    if '.worktrees' in ROOT.parts or subprocess.check_output(
            ['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() != 'main':
        raise RuntimeError('정본 main에서만 활성 검사와 커밋합니다')
    # Frontend is unchanged; reuse its existing build receipt.
    receipt = checks({'mode': 'live'})
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    if not receipt['ok']:
        raise RuntimeError('인쇄 활성 인수 실패 — 커밋하지 않습니다')
    base.PATHS = PATHS
    original_run = base.run
    def run(command, **kwargs):
        if command[:2] == ['git', 'commit']:
            command[-1] = 'Preserve form numbering during row insertion and verify workbook printing'
        return original_run(command, **kwargs)
    base.run = run
    sys.argv = [__file__, '--commit-only']
    base.main()


def main():
    if '--activate' in sys.argv:
        activate()
        return
    args = json.loads(sys.stdin.read() or '{}') if not sys.stdin.isatty() else {}
    receipt = checks(args)
    print(json.dumps(receipt, ensure_ascii=False))
    raise SystemExit(0 if receipt['ok'] else 1)


if __name__ == '__main__':
    main()
