"""Compare warm loader lookups on identical synthetic packages; no live data writes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import contextlib
import io
import json
import statistics
import subprocess
import tempfile
import time
import types
from unittest.mock import patch

import runtime_utils
import tool_loader
import vocabulary_state

BASELINE = '47ed150e'


def measure(outer_scope=False):
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:backend/ibl/tool_loader.py'],
                                     cwd=ROOT, text=True)
    old = types.ModuleType('baseline_tool_loader')
    old.__file__ = str(ROOT / 'backend/ibl/tool_loader.py')
    exec(compile(source, old.__file__, 'exec'), old.__dict__)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / 'data').mkdir()
        (root / 'data/vocabulary_policy.yaml').write_text('version: 1\nstandard_nodes: [self, others, table]\nrequired_packages: {pkg19: core}\n')
        for index in range(20):
            pkg = root / 'data/packages/installed/tools' / f'pkg{index}'
            pkg.mkdir(parents=True)
            (pkg / 'tool.json').write_text(json.dumps({'tools': [{'name': f'tool{index}'}]}))
            (pkg / 'handler.py').write_text('def execute(args, context): return 1\n')
        result = {}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(vocabulary_state, 'get_base_path', lambda: root))
            stack.enter_context(patch.object(runtime_utils, 'get_base_path', lambda: root))
            stack.enter_context(patch.object(runtime_utils, 'get_installed_packages_root',
                                            lambda: root / 'data/packages/installed'))
            vocabulary_state.invalidate_inventory()
            vocabulary_state.read_state()
            for label, module in [('before', old), ('after', tool_loader)]:
                stack.enter_context(patch.object(module, 'get_base_path', lambda: root))
                stack.enter_context(patch.object(module, 'get_tools_path',
                                                lambda: root / 'data/packages/installed/tools'))
                module.build_tool_package_map(force=True)
                ref = object()
                module._package_handlers_cache['pkg0'] = ref
                module._package_handler_mtimes['pkg0'] = (
                    root / 'data/packages/installed/tools/pkg0/handler.py').stat().st_mtime
                if hasattr(module, '_tool_handlers_cache'):
                    module._tool_handlers_cache['tool0'] = ref
                times, stats = [], []
                original_stat = Path.stat
                for _ in range(5):
                    count = [0]
                    def stat(path, *args, **kwargs):
                        count[0] += 1
                        return original_stat(path, *args, **kwargs)
                    start = time.perf_counter()
                    with patch.object(Path, 'stat', stat), contextlib.redirect_stdout(io.StringIO()):
                        for _ in range(50):
                            with vocabulary_state.inventory_scope() if outer_scope else contextlib.nullcontext():
                                assert module.load_tool_handler('tool0') is ref
                    times.append((time.perf_counter() - start) * 1000)
                    stats.append(count[0])
                result[label] = {'batch_ms': times, 'median_ms': statistics.median(times),
                                 'stat_calls_per_batch': stats}
            vocabulary_state.invalidate_inventory()
        return {'baseline': BASELINE, 'packages': 20, 'calls_per_batch': 50,
                'scope': 'Synthetic warm lookup only, not execution or model latency',
                'outer_inventory_scope': outer_scope, **result}


if __name__ == '__main__':
    print(json.dumps({'direct': measure(), 'engine_scope': measure(True)}, indent=2))
