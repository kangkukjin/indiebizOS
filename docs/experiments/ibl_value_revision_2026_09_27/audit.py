"""Read-only migration inventory. Never execute stored user expressions.

Run from repository root. Aggregate counts/hashes only; source may be private.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import ast
import collections
import hashlib
import json
import sqlite3
import yaml
from ibl_parser import parse
from common.safe_expr import compile_expr
from common.expression_parser import Parser


def audit(baseline_compile=None):
    counts = collections.Counter()
    expressions, seen_sources = {}, set()
    def collect(value, origin):
        if isinstance(value, str):
            if value not in seen_sources and ('[table:' in value or '[def:' in value):
                seen_sources.add(value)
                counts['programs_inspected'] += 1
                try:
                    visit(parse(value), origin)
                except Exception:
                    counts['programs_not_legacy_parseable'] += 1
        elif isinstance(value, dict):
            for v in value.values():
                collect(v, origin)
        elif isinstance(value, list):
            for v in value:
                collect(v, origin)
    def leaves(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from leaves(v)
        elif isinstance(value, list):
            for v in value:
                yield from leaves(v)
    def visit(value, origin):
        if isinstance(value, dict):
            if value.get('_node') == 'table':
                action, params = value.get('action'), value.get('params', {})
                target = params.get('set') if action == 'compute' else params.get('step') if action == 'reduce' else params.get('columns') if action == 'select' and isinstance(params.get('columns'), dict) else None
                for expr in leaves(target):
                    expressions.setdefault(expr, set()).add(origin)
            for v in value.values():
                visit(v, origin)
        elif isinstance(value, list):
            for v in value:
                visit(v, origin)
        elif isinstance(value, str):
            collect(value, origin)
    db = ROOT / 'data/world_pulse.db'
    with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as conn:
        for code, edition in conn.execute('select code, edition from ibl_code_corpus'):
            counts[f'corpus_edition_{edition}'] += 1
            if edition == 1:
                collect(code, 'observed')
    for folder in ('data/workflows', 'data/idioms'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.suffix not in ('.yaml', '.json', '.ibl'):
                continue
            counts['stored_files_inspected'] += 1
            try:
                text = path.read_text()
                data = json.loads(text) if path.suffix == '.json' else yaml.safe_load(text) if path.suffix == '.yaml' else text
                collect(data, 'stored')
            except (ValueError, yaml.YAMLError):
                counts['unreadable_stored_files'] += 1
    records = []
    for expr, origins in sorted(expressions.items()):
        item = {'sha256': hashlib.sha256(expr.encode()).hexdigest(), 'origins': sorted(origins)}
        try:
            compile_expr(expr)
            item['compatibility'] = 'accepted'
        except Exception as exc:
            item['compatibility'] = type(exc).__name__
        if baseline_compile is not None:
            try:
                baseline_compile(expr)
                item['baseline'] = 'accepted'
            except Exception as exc:
                item['baseline'] = type(exc).__name__
            counts['baseline:' + item['baseline']] += 1
            if item['baseline'] == 'accepted' and item['compatibility'] != 'accepted':
                counts['previously_valid_rejected'] += 1
        try:
            p = Parser(expr)
            tree = p.expr()
            p.pop('<eof>')
            # Bare field names parse as builtin identifiers but are not resolved.
            from common.expression_ops import BUILTINS
            def unresolved(node):
                from common.expression_ir import Node
                if isinstance(node, Node):
                    return (node.kind == 'builtin' and node.data['name'] not in BUILTINS) or unresolved(node.data)
                if isinstance(node, dict):
                    return any(unresolved(x) for x in node.values())
                if isinstance(node, (list, tuple)):
                    return any(unresolved(x) for x in node)
                return False
            item['direct_current'] = 'requires_binding_adapter' if unresolved(tree) else 'syntax_accepted_not_semantic_proof'
        except Exception:
            item['direct_current'] = 'requires_syntax_adapter'
        try:
            old = ast.parse(expr, mode='eval')
            item['coercion_sensitive'] = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'str','split','replace','strip','upper','lower','join'} for n in ast.walk(old))
        except SyntaxError:
            item['coercion_sensitive'] = False
        for key in ('compatibility', 'direct_current', 'coercion_sensitive'):
            counts[f'{key}:{item[key]}'] += 1
        records.append(item)
    counts['unique_expressions'] = len(records)
    return {'scope': 'read-only stored workflows/idiom files and observed edition-1 table compute/reduce/select expressions; no execution; not all future expressions', 'counts': dict(counts), 'expressions': records}


if __name__ == '__main__':
    import argparse
    import importlib.util
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', help='Trusted previous safe_expr.py snapshot (compile only)')
    args = parser.parse_args()
    baseline_compile = None
    if args.baseline:
        spec = importlib.util.spec_from_file_location('_expression_baseline', args.baseline)
        baseline = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = baseline
        spec.loader.exec_module(baseline)
        baseline_compile = baseline.compile_expr
    result = audit(baseline_compile)
    (Path(__file__).parent / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['counts'], ensure_ascii=False, indent=2))
