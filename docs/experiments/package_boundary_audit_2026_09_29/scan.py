"""One-time static census. Reads installed source; never executes package actions.

This is evidence collection, not a build gate or proof of whole-program safety.
Potential same-name call edges over-approximate reachability; dynamic calls can
remain unresolved. JSONL candidates are hypotheses pending human review.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import ast
import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
import yaml

HERE = Path(__file__).resolve().parent
INSTALLED = ROOT / 'data/packages/installed'
SKIP = {'__pycache__', 'node_modules', '.venv', 'venv', '.git', 'dist', 'build'}
TOKEN = re.compile(r'\[(?:sense|self|limbs|others|engines|table):[a-zA-Z_][\w-]*\]')
PATH_KEY = re.compile(r'(?:path|filename|file_name|output_dir|input_file|output_file)$')


def dump(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def jsonl(name, values):
    (HERE / name).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def direct_nodes(fn):
    def visit(node):
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            yield from visit(child)
    for stmt in fn.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from visit(stmt)


def text_return(node, assigned, seen=()):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            json.loads(node.value)
            return None
        except ValueError:
            return 'literal'
    if isinstance(node, ast.JoinedStr):
        return 'fstring'
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        if text_return(node.left, assigned, seen):
            return 'formatted_or_concatenated'
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ('join', 'format') and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
            return node.func.attr
    if isinstance(node, ast.Name) and node.id not in seen:
        if any(text_return(x, assigned, (*seen, node.id)) for x in assigned.get(node.id, [])):
            return 'text_variable'
    return None


def descriptions(value, location=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from descriptions(child, location + '/' + str(key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from descriptions(child, location + '/' + str(i))
    elif isinstance(value, str) and TOKEN.search(value):
        yield location, value


def snippets(text):
    # Complete quoted fragments only; prose/template fragments stay inventoried.
    found = re.findall(r'```(?:ibl)?\s*\n(.*?)```', text, re.S)
    found += re.findall(r'(?<!`)`([^`\n]+)`(?!`)', text)
    if TOKEN.match(text.strip()) or text.strip().startswith('#!ibl'):
        found.append(text.strip())
    return [x.strip() for x in found if TOKEN.search(x)]


def main():
    inventory, returns, paths, surfaces, examples, non_python = [], [], [], [], [], []
    catalog = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())
    actions = defaultdict(list)
    for node, config in catalog['nodes'].items():
        for name, action in config['actions'].items():
            if action.get('tool'):
                actions[action['tool']].append(node + ':' + name)
    for package in sorted(p for p in INSTALLED.glob('*/*') if p.is_dir()):
        info = {'package':str(package.relative_to(INSTALLED)), 'files':[], 'parse_errors':[],
                'excluded_files':[], 'actions':[], 'entries':[]}
        schema_path = package / 'tool.json'
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            for tool in schema.get('tools', [schema]):
                info['actions'] += actions.get(tool.get('name'), [])
        funcs, sources, name_index = {}, {}, defaultdict(list)
        for folder, dirs, files in os.walk(package):
            dirs[:] = sorted(d for d in dirs if d not in SKIP)
            for name in sorted(files):
                p = Path(folder) / name
                rel = str(p.relative_to(ROOT))
                if name.endswith('.py'):
                    if name.startswith('test_') or name == 'conftest.py':
                        info['excluded_files'].append(rel)
                        continue
                    src = p.read_text(errors='replace')
                    info['files'].append({'path':rel, 'sha256':hashlib.sha256(src.encode()).hexdigest()})
                    try:
                        tree = ast.parse(src)
                    except SyntaxError as exc:
                        info['parse_errors'].append({'path':rel, 'line':exc.lineno, 'message':exc.msg})
                        continue
                    sources[rel] = src
                    for fn in ast.walk(tree):
                        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            key = (rel, fn.name, fn.lineno)
                            funcs[key] = fn
                            name_index[fn.name].append(key)
                    for n in ast.walk(tree):
                        if isinstance(n, ast.Constant) and isinstance(n.value, str) and TOKEN.search(n.value):
                            surfaces.append({'package':info['package'], 'path':rel, 'location':n.lineno,
                                             'text':n.value})
                elif p.suffix in ('.js', '.ts', '.tsx', '.sh', '.kt', '.swift'):
                    non_python.append({'package':info['package'], 'path':rel,
                                       'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                                       'audit':'separate boundary; no Python AST analysis'})
                elif name == 'ibl_actions.yaml' or name.endswith('.md'):
                    text = p.read_text(errors='replace')
                    if name.endswith('.yaml'):
                        for location, content in descriptions(yaml.safe_load(text)):
                            surfaces.append({'package':info['package'], 'path':rel, 'location':location, 'text':content})
                    elif TOKEN.search(text):
                        surfaces.append({'package':info['package'], 'path':rel, 'location':'markdown', 'text':text})
        edges = defaultdict(set)
        for key, fn in funcs.items():
            for n in direct_nodes(fn):
                if isinstance(n, ast.Name):
                    edges[key].update(name_index.get(n.id, []))
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    edges[key].update(name_index.get(n.func.attr, []))
        roots = {key for key in funcs if key[1] in ('execute', 'execute_tool', 'handle', 'on_message')}
        reached, pending = set(), list(roots)
        while pending:
            key = pending.pop()
            if key in reached:
                continue
            reached.add(key)
            pending.extend(edges[key] - reached)
        info['entries'] = [list(k) for k in sorted(roots)]
        info['functions'] = len(funcs)
        info['syntactically_reachable_functions'] = len(reached)
        for key, fn in funcs.items():
            rel, name, line = key
            nodes = list(direct_nodes(fn))
            assigned = defaultdict(list)
            for n in nodes:
                if isinstance(n, ast.Assign):
                    for target in n.targets:
                        if isinstance(target, ast.Name):
                            assigned[target.id].append(n.value)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                    assigned[n.target.id].append(n.value)
            base = {'package':info['package'], 'path':rel, 'function':name,
                    'entry_reachable_heuristic':key in reached}
            resolver_calls = sorted({n.func.attr for n in nodes if isinstance(n, ast.Call)
                                     and isinstance(n.func, ast.Attribute)
                                     and n.func.attr in ('resolve_path', 'resolve_output_path')})
            user_keys = sorted({n.args[0].value for n in nodes if isinstance(n, ast.Call)
                               and isinstance(n.func, ast.Attribute) and n.func.attr == 'get'
                               and n.args and isinstance(n.args[0], ast.Constant)
                               and isinstance(n.args[0].value, str) and PATH_KEY.search(n.args[0].value)})
            for n in nodes:
                if isinstance(n, ast.Return):
                    kind = text_return(n.value, assigned)
                    if kind:
                        returns.append({**base, 'line':n.lineno, 'kind':kind,
                                        'expression':ast.unparse(n.value)[:220]})
                if not isinstance(n, ast.Call):
                    continue
                call = ast.unparse(n.func)
                leaf = call.rsplit('.', 1)[-1]
                kinds = []
                if leaf in ('basename', 'abspath', 'expanduser'):
                    kinds.append('path_transform')
                if leaf in ('open', 'write_text', 'write_bytes', 'save', 'screenshot', 'pdf', 'imwrite', 'write_html'):
                    kinds.append('file_sink')
                if leaf in ('resolve_path', 'resolve_output_path'):
                    kinds.append('resolver')
                if kinds:
                    paths.append({**base, 'line':n.lineno, 'kind':kinds[0], 'call':call,
                                  'user_path_keys_in_function':user_keys, 'resolvers_in_function':resolver_calls,
                                  'expression':ast.unparse(n)[:220]})
        inventory.append(info)
    # Compiler is only called for captured complete snippets; no runtime.run.
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()
    seen = set()
    for surface in surfaces:
        for code in snippets(surface['text']):
            key = (surface['path'], code)
            if key in seen:
                continue
            seen.add(key)
            try:
                report = compile_program(code, registry).report()
                result = {'status':report['status'], 'issues':[{k:i.get(k) for k in ('code','severity','message')}
                                                              for i in report['issues']]}
            except Exception as exc:
                result = {'status':'parse_error','error':str(exc)[:250]}
            examples.append({k:v for k,v in surface.items() if k!='text'} | {'code':code,'result':result})
    jsonl('non_python_inventory.jsonl', non_python)
    jsonl('inventory.jsonl', inventory)
    jsonl('return_candidates.jsonl', returns)
    jsonl('path_candidates.jsonl', paths)
    jsonl('example_checks.jsonl', examples)
    # Save surface locations/counts, not whole source/doc strings.
    jsonl('example_surfaces.jsonl', [{k:v for k,v in row.items() if k!='text'} |
                                   {'captured_snippets':len(snippets(row['text']))} for row in surfaces])
    summary = {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               'non_python_sources':len(non_python), 'packages':len(inventory), 'python_files':sum(len(x['files']) for x in inventory),
               'parse_errors':sum(len(x['parse_errors']) for x in inventory),
               'functions':sum(x['functions'] for x in inventory),
               'text_return_candidates':len(returns), 'path_sites':dict(Counter(x['kind'] for x in paths)),
               'example_surfaces':len(surfaces),'captured_snippets':len(examples),
               'snippet_statuses':dict(Counter(x['result']['status'] for x in examples)),
               'exclusions':sorted(SKIP), 'actions_executed':0,
               'limitations':['Call graph is a same-name over-approximation, not semantic reachability.',
                              'Dynamic subprocess/JS/native/remote writes and unknown return expressions need manual review.',
                              'Captured quoted/standalone snippets include fragments and templates; statuses are not defect counts.']}
    dump('summary.json', summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
