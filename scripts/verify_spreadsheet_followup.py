"""Focused follow-up gates. Receipts are not the full fourteen release scenarios."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401


def activate():
    import verify_spreadsheet_app as base
    import httpx
    if '.worktrees' in ROOT.parts or subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() != 'main':
        raise RuntimeError('정본에서만 활성 검증·커밋합니다')
    # Rebuild the deployed surface. Unit and engine receipts are retained; the
    # full release remains open (LET, other formats, accessibility, recovery).
    base.run(['npx', '--no-install', 'vite', 'build'], cwd=ROOT/'frontend')
    response = httpx.post('http://127.0.0.1:8765/spreadsheets/__acceptance_missing__/changes',
                         json={'args': {}}, timeout=20, trust_env=False)
    if response.status_code != 400 or response.json().get('detail') != '문서 작업 항목을 찾을 수 없습니다':
        raise RuntimeError('새 시트 변경 경로가 활성화되지 않았습니다')
    base.PATHS = [
        'backend/services/spreadsheet_changes.py', 'backend/services/spreadsheet_files.py',
        'backend/services/spreadsheet_workspace.py', 'backend/services/spreadsheet_imports.py',
        'backend/surface/api_spreadsheets.py', 'backend/static/spreadsheet_plugin/plugin.js',
        'backend/test_spreadsheet_changes.py', 'backend/test_spreadsheet_browser_live.py',
        'backend/test_spreadsheet_functions_live.py', 'backend/test_spreadsheet_scale_live.py',
        'frontend/src/components/spreadsheets/SpreadsheetEditor.tsx', 'frontend/src/lib/api-spreadsheets.ts',
        'frontend/i18n/catalog.json', 'frontend/i18n/translations.json', 'frontend/i18n/remote.json',
        'scripts/check_backend_layers.py', 'scripts/verify_spreadsheet_followup.py',
        'data/scripts/spreadsheet_followup.py', 'data/scripts/registry.yaml',
        'docs/SPREADSHEET_APP_DESIGN_2026_10_02.md',
        'data/member_manifest.json', 'data/phone_manifest.json', 'data/package_meta.json',
        'data/ibl_nodes.yaml', 'data/ibl_fixtures.json', 'data/core_manifest.json',
        'data/bodies/android.engine.json', 'data/system_docs/architecture.md',
        'data/system_docs/system_structure.md', 'data/shell_shadow.json',
    ]
    # Reuse the established tracked/unignored path selection and build/commit
    # gates. No prior commit is repeated; these are the new follow-up paths.
    original_run = base.run
    def run(command, **kwargs):
        if command[:2] == ['git', 'commit']:
            command[-1] = 'Preserve spreadsheet edits during cancellation and import refresh'
        return original_run(command, **kwargs)
    base.run = run
    sys.argv = [__file__, '--commit-only']
    base.main()


def main():
    if '--activate' in sys.argv:
        activate()
        return
    args = json.loads(sys.stdin.read() or '{}') if not sys.stdin.isatty() else {}
    mode = args.get('mode', 'unit')
    env = dict(os.environ, INDIEBIZ_OFFICE_LIVE_TEST='1')
    env['PYTHONPATH'] = str(ROOT / 'backend')
    commands = {
        'unit': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_changes.py',
                  'backend/test_spreadsheet_workspace.py', 'backend/test_spreadsheet_imports.py']],
        'build': [['npx', 'tsc', '-p', 'tsconfig.app.json'], ['npx', 'vite', 'build']],
        'live': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_browser_live.py', '-s']],
        'scale': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_scale_live.py', '-s']],
        'functions': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_functions_live.py', '-s']],
        'gates': [[sys.executable, 'scripts/check_backend_layers.py'],
                  [sys.executable, 'scripts/check_file_size.py'],
                  [sys.executable, 'scripts/check_value_judgment.py']],
    }
    if mode not in commands:
        raise ValueError('Unknown check mode')
    results = []
    for cmd in commands[mode]:
        result = subprocess.run(cmd, cwd=ROOT / 'frontend' if mode == 'build' else ROOT,
                                env=env, text=True, capture_output=True, timeout=600)
        results.append({'command': cmd, 'exit_code': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            break
    print(json.dumps({'ok': all(r['exit_code'] == 0 for r in results), 'items': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
