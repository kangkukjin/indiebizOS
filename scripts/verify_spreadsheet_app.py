#!/usr/bin/env python3
"""Post-activation spreadsheet acceptance and optional path-scoped main commit.

Invoked by self:patch active_verify_cmd after the worker is ACTIVE. Uses the
registered test/gate runners and treats their JSON ok field as authoritative.
Passing this phase does not complete the design's fourteen release scenarios.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

TESTS = [
    'backend/test_spreadsheet_workspace.py', 'backend/test_spreadsheet_imports.py',
    'backend/test_document_workspace.py', 'backend/test_document_office.py',
    'backend/test_document_sheet_transit_2026_09_15.py',
    'backend/test_spreadsheet_engine_live.py', 'backend/test_spreadsheet_browser_live.py',
    'backend/test_document_office_live.py',
]
PATHS = [
    'backend/api.py', 'backend/datastore/office_store.py',
    'backend/services/document_office.py', 'backend/services/document_workspace.py',
    'backend/services/office_sessions.py', 'backend/services/resource_links.py',
    'backend/services/spreadsheet_files.py', 'backend/services/spreadsheet_imports.py',
    'backend/services/spreadsheet_workspace.py', 'backend/surface/api_spreadsheets.py',
    'backend/static/spreadsheet_plugin/plugin.js',
    'backend/test_spreadsheet_workspace.py', 'backend/test_spreadsheet_imports.py',
    'backend/test_spreadsheet_engine_live.py', 'backend/test_spreadsheet_browser_live.py',
    'data/packages/installed/tools/system_essentials/handler.py',
    'data/packages/installed/tools/system_essentials/ibl_actions.yaml',
    'data/packages/installed/tools/system_essentials/sheet_ops.py',
    'data/packages/installed/tools/system_essentials/essentials_workspace.py',
    'data/packages/installed/tools/system_essentials/essentials_state_paths.py',
    'data/packages/installed/tools/system_essentials/tool.json',
    'data/ibl_example_review.json', 'data/ibl_nodes.yaml', 'data/member_manifest.json',
    'data/phone_manifest.json', 'data/package_meta.json', 'data/ibl_fixtures.json',
    'data/shell_shadow.json', 'data/core_manifest.json',
    'data/bodies/android.nodes.yaml', 'data/bodies/android.engine.json',
    'data/guides/sheet.md', 'docs/SPREADSHEET_APP_DESIGN_2026_10_02.md',
    'data/system_docs/architecture.md', 'data/system_docs/system_structure.md',
    'data/system_docs/technical.md',
    'frontend/electron/windows.js', 'frontend/src/App.tsx',
    'frontend/src/components/ActionDesktop.tsx', 'frontend/src/components/DocumentReferences.tsx',
    'frontend/src/components/OfficeDocumentEditor.tsx',
    'frontend/src/components/SpreadsheetWorkspace.tsx',
    'frontend/src/components/spreadsheets/SpreadsheetEditor.tsx',
    'frontend/src/components/spreadsheets/SpreadsheetImport.tsx',
    'frontend/src/components/spreadsheets/spreadsheet.css',
    'frontend/src/lib/api-spreadsheets.ts', 'frontend/src/lib/surface-navigation.ts',
    'frontend/src/types/index.ts', 'frontend/i18n/catalog.json',
    'frontend/i18n/translations.json', 'frontend/i18n/remote.json',
    'scripts/check_backend_layers.py', 'scripts/verify_spreadsheet_app.py',
]


def run(command, cwd=ROOT, payload=None, env=None, timeout=600, structured=False):
    result = subprocess.run(command, cwd=cwd, input=None if payload is None else json.dumps(payload),
                            text=True, capture_output=True, env=env, timeout=timeout)
    print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, flush=True)
    if result.returncode:
        raise RuntimeError(f'검사 실패: {command[0]} (exit {result.returncode})')
    if structured and not json.loads(result.stdout).get('ok'):
        raise RuntimeError('등록 검사 실행기가 실패를 보고했습니다')
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--commit-only', action='store_true',
                        help='Resume commit after recorded acceptance; checks active route and commit gates only')
    options = parser.parse_args()
    # Check the activated route, not just imports or a fixture health endpoint.
    import httpx
    response = httpx.get('http://127.0.0.1:8765/spreadsheets', timeout=20, trust_env=False)
    response.raise_for_status()
    assert response.json().get('release_complete') is False
    if not options.commit_only:
        run(['npx', '--no-install', 'tsc', '-p', 'tsconfig.app.json'], cwd=ROOT/'frontend')
        run(['npx', '--no-install', 'vite', 'build'], cwd=ROOT/'frontend')
        env = {**os.environ, 'INDIEBIZ_OFFICE_LIVE_TEST':'1', 'INDIEBIZ_BASE_PATH':str(ROOT)}
        run([sys.executable, 'data/scripts/시험.py'], payload={'files':TESTS, 'timeout':600},
            env=env, timeout=660, structured=True)
        run([sys.executable, 'data/scripts/빌드검증.py'],
            payload={'gates':['build','layers','size'], 'timeout':180}, structured=True)
    if options.commit or options.commit_only:
        branch = run(['git', 'branch', '--show-current']).strip()
        if branch != 'main' or '.worktrees' in ROOT.parts:
            raise RuntimeError('정본 main에서만 커밋합니다')
        # Existing files are not necessarily versioned: Android node output is
        # deliberately ignored. Respect Git's tracked/unignored policy, without
        # force-adding generated runtime data or sweeping other work.
        listed = subprocess.check_output(
            ['git', 'ls-files', '-z', '--cached', '--others',
             '--exclude-standard', '--', *PATHS], cwd=ROOT, text=True)
        paths = list(dict.fromkeys(p for p in listed.split('\0') if p))
        run(['git', 'add', '--', *paths])
        # The core manifest derives its file set from the index, so regenerate
        # after staging our new modules. Never sweep unrelated pending changes.
        run([sys.executable, 'scripts/build_ibl_nodes.py'])
        run([sys.executable, 'scripts/build_body_bundle.py', 'android'])
        run(['git', 'add', '--', *paths])
        run(['git', 'commit', *paths, '-m',
             'Add spreadsheet workspace with shared office sessions and guarded engine edits'], timeout=1200)
        run(['git', 'log', '-1', '--oneline'])
    print(json.dumps({'activated':True, 'phase_verified':not options.commit_only,
                      'acceptance_reused':options.commit_only, 'release_complete':False,
                      'remaining':'SPREADSHEET_APP_DESIGN_2026_10_02.md §14'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
