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
    'frontend/i18n/runtime.mjs', 'frontend/scripts/ui-compiler.mjs',
    'frontend/scripts/ui-catalog.mjs', 'frontend/scripts/ui-catalog.d.mts',
    'frontend/i18n/languages.json', 'frontend/i18n/translations.json',
    'frontend/i18n/catalog.json', 'frontend/src/i18n/ui.tsx',
    'frontend/vite.config.ts', 'frontend/src/components/Launcher.tsx',
    'frontend/i18n/remote.json', 'frontend/package.json',
    'backend/surface/launcher_surface_remote.py',
    'frontend/scripts/ui-i18n.test.mjs', 'frontend/scripts/ui-source-check.mjs',
    'frontend/scripts/ui-browser-check.py', 'frontend/scripts/ui-server-check.py',
    'frontend/scripts/ui-translate.py', 'frontend/i18n/README.md',
    'frontend/src/components/ManualMode.tsx', 'frontend/scripts/ui-post-apply.py',
]


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, env=os.environ, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--live-url', help='Running owner backend origin after RED restart')
    args = parser.parse_args()
    os.environ.setdefault('INDIEBIZ_BASE_PATH', str(ROOT))
    os.environ.setdefault('INDIEBIZ_PYTHON', sys.executable)
    frontend = ROOT / 'frontend'
    run('npm', 'run', 'build', cwd=frontend)
    run('node', '--test', 'scripts/ui-i18n.test.mjs', cwd=frontend)
    run('node', 'scripts/ui-source-check.mjs', cwd=frontend)
    run(sys.executable, 'scripts/ui-server-check.py', cwd=frontend)
    run(sys.executable, 'scripts/ui-browser-check.py', cwd=frontend)
    if args.live_url:
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
            run('git', 'commit', '--only', '-m', 'Add Korean-source UI localization and automatic translation refresh', '--', *FILES)
        elif changed.returncode != 0:
            raise RuntimeError('Unable to inspect staged UI paths')
        run('git', 'log', '-1', '--format=%H %s')
    print(json.dumps({'ui_release_verified': True, 'commit_requested': args.commit}))


if __name__ == '__main__':
    main()
