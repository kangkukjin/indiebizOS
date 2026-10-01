"""Verify the UI release after deferred RED apply; optionally commit its paths only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    'backend/surface/launcher_app_common.py',
    'backend/surface/launcher_app_appmode.py',
    'frontend/src/components/GenericInstrument.tsx',
    'frontend/src/components/VocabularyView.tsx',
    'frontend/src/components/chat/ActionGrimoire.tsx',
    'data/bodies/android.engine.json', 'helper/member_app.html',
    'frontend/i18n/README.md', 'frontend/i18n/catalog.json',
    'frontend/i18n/remote.json', 'frontend/i18n/runtime.mjs',
    'frontend/i18n/translations.json',
    'frontend/scripts/ui-browser-check.py', 'frontend/scripts/ui-catalog.mjs',
    'frontend/scripts/ui-compiler.mjs', 'frontend/scripts/ui-i18n.test.mjs',
    'frontend/scripts/ui-source-check.mjs', 'frontend/scripts/ui-translate.py',
    'frontend/scripts/ui-static-values.mjs', 'frontend/scripts/ui-system-sources.py',
    'frontend/scripts/ui-post-apply.py', 'frontend/scripts/ui-live-check.py',
    'frontend/src/components/ActionDesktop.tsx', 'frontend/src/components/Launcher.tsx',
    'frontend/src/components/ManualMode.tsx',
    'frontend/src/components/launcher-components/ModelGearLever.tsx',
    'frontend/src/components/launcher-components/NodePresence.tsx',
    'frontend/src/i18n/ui.tsx',
]


RECEIPT = ROOT / 'data/system_ai_state/ui_release_verification.json'
CHECKS = []


def run(*args, cwd=ROOT):
    result = subprocess.run(args, cwd=cwd, env=os.environ, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end='', flush=True)
    CHECKS.append({'command': list(args), 'cwd': str(cwd), 'exit_code': result.returncode, 'output': result.stdout})
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps({'root': str(ROOT), 'checks': CHECKS, 'success': all(c['exit_code'] == 0 for c in CHECKS)}, ensure_ascii=False, indent=2))
    result.check_returncode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--live-url', help='Running owner backend origin after RED restart')
    parser.add_argument('--read-only', action='store_true',
                        help='Pre-activation checks; defer selection and commit until active')
    args = parser.parse_args()
    if args.read_only and args.commit:
        parser.error('--read-only cannot be combined with --commit')
    os.environ.setdefault('INDIEBIZ_BASE_PATH', str(ROOT))
    os.environ.setdefault('INDIEBIZ_PYTHON', sys.executable)
    frontend = ROOT / 'frontend'
    run(sys.executable, 'scripts/build_member_shell.py')
    run(sys.executable, 'scripts/build_member_shell.py', '--check')
    run(sys.executable, 'scripts/build_body_bundle.py', 'android')
    run(sys.executable, 'scripts/build_body_bundle.py', 'android', '--check')
    run('npm', 'run', 'build', cwd=frontend)
    run('node', '--test', 'scripts/ui-i18n.test.mjs', cwd=frontend)
    run('node', 'scripts/ui-source-check.mjs', cwd=frontend)
    run(sys.executable, 'scripts/ui-server-check.py', cwd=frontend)
    browser_args = ['--live-url', args.live_url] if args.live_url else []
    run(sys.executable, 'scripts/ui-browser-check.py', *browser_args, cwd=frontend)
    if args.live_url:
        live_args = ['--read-only'] if args.read_only else []
        run(sys.executable, 'scripts/ui-live-check.py', '--live-url', args.live_url, *live_args, cwd=frontend)
        with urlopen(args.live_url.rstrip('/') + '/launcher/app', timeout=10) as response:
            live = response.read().decode('utf-8')
        assert 'window.__ui=' in live and 'data-ui-text=' in live, 'live remote has no i18n bundle'
        print('live /launcher/app: compiled language runtime served', flush=True)
    if args.commit:
        branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
        assert branch == 'main' and '.worktrees' not in ROOT.parts, 'commit requires canonical main'
        run('git', 'add', '--', *FILES)
        changed = subprocess.run(['git', 'diff', '--cached', '--quiet', '--', *FILES], cwd=ROOT)
        if changed.returncode == 1:
            run('git', 'commit', '--only', '-m', 'Fix UI metadata localization and preserve source identifiers', '--', *FILES)
        elif changed.returncode != 0:
            raise RuntimeError('Unable to inspect staged UI paths')
        run('git', 'log', '-1', '--format=%H %s')
    print(json.dumps({'ui_release_verified': True, 'commit_requested': args.commit, 'receipt': str(RECEIPT)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps({'root': str(ROOT), 'checks': CHECKS, 'success': False, 'completed': True, 'error': str(error)}, ensure_ascii=False, indent=2))
        raise
    else:
        RECEIPT.write_text(json.dumps({'root': str(ROOT), 'checks': CHECKS, 'success': True, 'completed': True}, ensure_ascii=False, indent=2))
