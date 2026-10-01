"""Extract source-owned model UI metadata without loading runtime/user settings."""
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "backend/services/model_settings_view.py": None,
    "backend/base/model_resolver.py": {"resolve_image_execution"},
}


def sources():
    values = {"절약", "균형", "최대", "경량", "중급", "고급", "분류", "평가", "실행", "의식"}
    for filename, functions in SOURCES.items():
        tree = ast.parse((ROOT / filename).read_text())
        roots = [tree] if functions is None else [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in functions]
        for root in roots:
            for node in ast.walk(root):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                    node.body[0].value.value = ""  # Exclude docstrings from the UI catalog.
            for node in ast.walk(root):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search('[가-힣]', node.value):
                    values.add(node.value)
    # Read only source definitions, never user records or endpoint responses.
    import sys
    sys.path.insert(0, str(ROOT / 'backend'))
    import boot_paths  # noqa: F401
    import yaml
    nodes = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())['nodes']
    for node in nodes.values():
        values.add(node.get('description', ''))
        for action in node.get('actions', {}).values():
            values.update(action.get(key, '') for key in ('description', 'target_description', 'implementation'))
            values.update((action.get('ops') or {}).get('values', {}).values())
    import api_launcher_web as launcher
    launcher.IBL_NODES_PATH = str(ROOT / 'data/ibl_nodes.yaml')
    launcher.INSTRUMENTS_DIR = str(ROOT / 'data/instruments')
    instruments = launcher._derive_instruments()['instruments']
    display = {'label', 'title', 'placeholder', 'description', 'hint', 'empty',
               'confirm', 'tooltip', 'submit_label', 'run_label', 'note', 'empty_text', 'unit', 'sub', 'k'}
    excluded = {'action', 'args', 'params', 'default', 'value', 'code', 'script', 'data', 'init'}
    specs = {}
    def collect(value, path=()):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in excluded:
                    continue
                visible = key in display or (key == 'name' and (not path or (len(path) == 2 and path[0] == 'modes')))
                if visible and isinstance(item, str) and re.search('[가-힣]', item):
                    found.append({'path': list(path + (key,)), 'source': item})
                    values.add(item)
                elif isinstance(item, (dict, list)):
                    found.extend(collect(item, path + (key,)))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.extend(collect(item, path + (index,)))
        return found
    for instrument in instruments:
        specs[instrument['id']] = {'name': instrument['name'], 'fields': collect(instrument)}
    return {'messages': sorted(v for v in values if isinstance(v, str) and re.search('[가-힣]', v)),
            'instruments': specs}


if __name__ == '__main__':
    print(json.dumps(sources(), ensure_ascii=False))
