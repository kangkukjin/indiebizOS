"""Focused linked-sheet checks and path-scoped post-restart acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

PATHS = [
    'backend/services/spreadsheet_workspace.py', 'backend/services/resource_links.py',
    'backend/surface/api_documents.py', 'backend/surface/api_spreadsheets.py',
    'backend/test_spreadsheet_links.py', 'backend/test_spreadsheet_links_live.py',
    'frontend/src/components/DocumentReferences.tsx',
    'frontend/src/components/spreadsheets/SpreadsheetEditor.tsx',
    'scripts/verify_spreadsheet_links.py', 'data/scripts/spreadsheet_followup.py',
    'docs/SPREADSHEET_APP_DESIGN_2026_10_02.md',
    'data/bodies/android.engine.json', 'data/core_manifest.json',
]


def checks(args):
    mode = args.get('mode', 'unit')
    commands = {
        'unit': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_links.py',
                  'backend/test_spreadsheet_workspace.py', 'backend/test_document_workspace.py',
                  'backend/test_document_office.py', '-m', 'not system']],
        'live': [[sys.executable, '-m', 'pytest', 'backend/test_spreadsheet_links_live.py', '-s', '--tb=short']],
        'build': [['npx', '--no-install', 'tsc', '-p', 'tsconfig.app.json'], ['npx', '--no-install', 'vite', 'build']],
    }
    if mode not in commands:
        raise ValueError('지원하지 않는 연결 검사 모드')
    env = {**os.environ, 'INDIEBIZ_OFFICE_LIVE_TEST': '1', 'PYTHONPATH': str(ROOT / 'backend')}
    results = []
    for command in commands[mode]:
        r = subprocess.run(command, cwd=ROOT / 'frontend' if mode == 'build' else ROOT,
                           env=env, capture_output=True, text=True, timeout=600)
        results.append({'command': command, 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        if r.returncode:
            break
    ok = all(row['exit_code'] == 0 for row in results)
    return {'ok': ok, 'items': results, 'operation_outcome': {
        'status': 'passed' if ok else 'failed', 'message': '연결 검사 통과' if ok else '연결 검사 실패'}}


def activate():
    import verify_spreadsheet_app as base
    if '.worktrees' in ROOT.parts or subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() != 'main':
        raise RuntimeError('정본 main에서만 활성 검사·커밋합니다')
    import httpx
    probes = [
        ('spreadsheets', 'request-snapshot', {'operation_id': 'activation-probe'}),
        ('documents', 'refresh-sheet', {'reference_id': 'missing', 'snapshot_id': 'missing',
                                     'start': 0, 'end': 1, 'selected_sha256': 'missing',
                                     'source_snapshot_id': 'missing'}),
    ]
    for surface, operation, args in probes:
        response = httpx.post(f'http://127.0.0.1:8765/{surface}/__acceptance_missing__/{operation}',
                              json={'args': args}, timeout=20, trust_env=False)
        if response.status_code != 400 or response.json().get('detail') != '문서 작업 항목을 찾을 수 없습니다':
            raise RuntimeError('연결 갱신 API가 활성화되지 않았습니다')
    base.run(['npx', '--no-install', 'vite', 'build'], cwd=ROOT / 'frontend')
    receipt = checks({'mode': 'live'})
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    if not receipt['ok']:
        raise RuntimeError('연결 활성 인수 실패 — 커밋하지 않습니다')
    base.PATHS = PATHS
    original_run = base.run
    def run(command, **kwargs):
        if command[:2] == ['git', 'commit']:
            command[-1] = 'Refresh linked spreadsheet reports from pinned live snapshots'
        return original_run(command, **kwargs)
    base.run = run
    sys.argv = [__file__, '--commit-only']
    base.main()


if __name__ == '__main__':
    if '--activate' in sys.argv:
        activate()
    else:
        receipt = checks(json.loads(sys.stdin.read() or '{}'))
        print(json.dumps(receipt, ensure_ascii=False))
        raise SystemExit(0 if receipt['ok'] else 1)
