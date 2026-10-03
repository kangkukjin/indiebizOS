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


def status_sources():
    """Catalog source-owned health messages; interpolated diagnostics stay opaque."""
    class Messages(ast.NodeVisitor):
        def __init__(self):
            self.values = set()

        def visit_Constant(self, node):
            if isinstance(node.value, str) and re.search('[가-힣]', node.value):
                self.values.add(node.value)

        def visit_JoinedStr(self, node):
            parts = []
            index = 0
            for part in node.values:
                if isinstance(part, ast.Constant):
                    parts.append(part.value)
                else:
                    parts.append('{' + str(index) + '}')
                    index += 1
            value = ''.join(parts)
            if re.search('[가-힣]', value):
                self.values.add(value)
            # Never collect f-string fragments or interpolated/user values.

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Constant):
                return  # docstring
            self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'logger':
                return
            self.generic_visit(node)

    collector = Messages()
    sources = {
        'backend/cognition/world_pulse_health.py': {'get_ibl_health_status', 'run_ibl_health_check'},
        'backend/cognition/ibl_description_audit.py': {'run_description_drift_check'},
    }
    for filename, functions in sources.items():
        tree = ast.parse((ROOT / filename).read_text())
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in functions:
                continue
            collector.visit(node)
            # The audit composes optional source-owned notes with a literal separator.
            # Register each composition as a whole so diagnostics inside slots stay opaque.
            appends = {}
            joins = []
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                if not isinstance(call.func, ast.Attribute) or len(call.args) != 1:
                    continue
                owner = call.func.value
                if call.func.attr == 'append' and isinstance(owner, ast.Name):
                    part = Messages()
                    part.visit(call.args[0])
                    if len(part.values) == 1:
                        appends.setdefault(owner.id, []).append(next(iter(part.values)))
                if call.func.attr == 'join' and isinstance(owner, ast.Constant) and isinstance(owner.value, str) and isinstance(call.args[0], ast.Name):
                    joins.append((call.args[0].id, owner.value))
            from itertools import combinations
            for name, separator in joins:
                parts = appends.get(name, [])
                if not 1 < len(parts) <= 4:
                    continue
                for count in range(2, len(parts) + 1):
                    for group in combinations(parts, count):
                        offset = 0
                        combined = []
                        for part in group:
                            combined.append(re.sub(r'\{(\d+)\}', lambda m: '{' + str(int(m[1]) + offset) + '}', part))
                            offset += len(re.findall(r'\{\d+\}', part))
                        collector.values.add(separator.join(combined))
    return sorted(collector.values)


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
            'instruments': specs, 'status_messages': status_sources()}


if __name__ == '__main__':
    print(json.dumps(sources(), ensure_ascii=False))
