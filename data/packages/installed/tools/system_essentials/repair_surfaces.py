"""수리 검증의 판본 지문을 라이브 활성화까지 잇는다. 별도 수리 원장은 만들지 않는다."""
import importlib.util
import json
from pathlib import Path
import os
import re
import subprocess


def touched(rels, root=None):
    """Use the builder's input authority; prefixes also catch newly added/deleted sources."""
    root = Path(root) if root else Path(__file__).resolve().parents[5]
    source = root / 'backend/surface/surface_assets.py'
    inputs = set()
    if source.is_file():
        spec = importlib.util.spec_from_file_location('repair_surface_inputs', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        inputs = {path.relative_to(root).as_posix() for path in module.source_files()}
    return any(rel in inputs or rel.startswith(('frontend/src/', 'frontend/surfaces/')) or
               rel == 'scripts/build_surfaces.py' or
               (rel.startswith('backend/surface/') and
                rel.rsplit('/', 1)[-1].startswith(('launcher_', 'member_', 'surface_')))
               for rel in rels)


def build(root, python, runner=subprocess.run, env=None, expected=None):
    script = os.path.join(root, 'scripts', 'build_surfaces.py')
    if not os.path.isfile(script):
        return {'gate': 'surface_build', 'passed': False, 'detail': '화면 빌더가 없습니다'}
    command = [python, script]
    if expected:
        command += ['--activate', '--expect', expected]
    try:
        process = runner(command, cwd=root, env=env, capture_output=True, text=True, timeout=180)
        output = (process.stdout or '').strip().splitlines()
        version = output[-1] if output else ''
        passed = process.returncode == 0 and bool(re.fullmatch('[a-f0-9]{64}', version))
        result = {'gate': 'surface_activation' if expected else 'surface_build',
                  'passed': passed, 'version': version if passed else None,
                  'detail': ((process.stderr or '') + (process.stdout or ''))[-1200:]}
        if expected and passed:
            pointer = os.path.join(root, 'frontend', 'dist-surfaces', 'active.json')
            with open(pointer) as stream:
                result['passed'] = json.load(stream)['version'] == expected
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {'gate': 'surface_activation' if expected else 'surface_build',
                'passed': False, 'detail': str(error)}
