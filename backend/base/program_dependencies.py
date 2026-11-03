"""Dependency evidence for a program candidate; no model-authored skip list."""
import ast
import re
import os
import subprocess
from pathlib import Path

from program_boundary import describe, plan, protected_reason

SKIP = {'.git', '.venv', 'node_modules', '__pycache__', '.worktrees', '.pytest_cache'}
SOURCE_ROOTS = ('backend', 'scripts', 'data/scripts', 'data/packages/installed/tools', 'frontend/src', 'frontend/surfaces')
PATH_REFERENCE = re.compile(r'(?:backend|scripts|data|frontend)/[\w./-]+')


def _names(source):
    imports, references, dynamic = set(), set(), False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports, references, True
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(a.name for a in node.names if a.name != '*')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            references.update(PATH_REFERENCE.findall(node.value))
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
            if name in {'__import__', 'import_module', '_load_sibling'}:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    imports.add(node.args[0].value)
                else:
                    dynamic = True
    return imports, references, dynamic


def inventory(root):
    root = Path(root)
    paths = set()
    if (root / '.git').exists():
        listing = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard',
                                  '--', *SOURCE_ROOTS], cwd=root, capture_output=True, check=True, timeout=30)
        return {os.fsdecode(p) for p in listing.stdout.split(b'\0') if p
                and (root / os.fsdecode(p)).is_file() and not (root / os.fsdecode(p)).is_symlink()
                and not set(Path(os.fsdecode(p)).parts) & SKIP}
    for prefix in SOURCE_ROOTS:
        for path in (root / prefix).rglob('*'):
            if path.is_file() and not path.is_symlink() and not set(path.relative_to(root).parts) & SKIP:
                paths.add(path.relative_to(root).as_posix())
    return paths


def analyse(root, changes, *, ownership=None):
    """Program inputs and affected consumers, with unresolved imports visible.

    Package-local dynamic loading watches the entire package directory (including
    additions). A dynamic backend import stays explicitly unresolved; it is not
    silently certified as an isolated program.
    """
    root = Path(root)
    change_plan = ownership if ownership is not None else plan(changes)
    paths = inventory(root)
    modules, graph, reverse, externals, unknown = {}, {}, {}, {}, {}
    for path in paths:
        if path.endswith('.py'):
            modules.setdefault(Path(path).stem, set()).add(path)
    for path in paths:
        if not path.endswith('.py') or Path(path).name == 'conftest.py':
            continue
        names, refs, dynamic = _names((root / path).read_text(errors='replace'))
        edges, external = set(refs) & paths, set()
        for name in names:
            hits = modules.get(name.rsplit('.', 1)[-1], set())
            local = {p for p in hits if Path(p).parent == Path(path).parent}
            backend = {p for p in hits if p.startswith('backend/')}
            if local or backend:
                edges.update(local or backend)
            elif hits:
                edges.update(hits)
            else:
                external.add(name.split('.')[0])  # path-ok: imported Python distribution name
        graph[path], externals[path] = edges, external
        for edge in edges:
            reverse.setdefault(edge, set()).add(path)
        if dynamic:
            unknown[path] = 'dynamic import target'
    def closure(seeds, edges):
        found, stack = set(seeds), list(seeds)
        while stack:
            current = stack.pop()
            # Cross the protected host through its stable interface. Internal
            # host wiring is not an implementation input of every package.
            if current not in seeds and protected_reason(current) and not Path(current).name.startswith('test_'):
                continue
            for p in edges.get(current, set()) - found:
                found.add(p)
                stack.append(p)
        return found
    owned, watch_roots = set(changes), set()
    for program in change_plan['programs']:
        if program.get('root'):
            watch_roots.add(program['root'])
            owned.update(p for p in paths if p.startswith(program['root'] + '/'))
    consumers = closure(set(changes), reverse)
    tests = {p for p in consumers if Path(p).name.startswith('test_')}
    inputs = closure(owned | tests, graph)
    # Configuration controls the interpretation of the selected tests, but
    # conftest's fixture imports are not business dependencies of every program.
    inputs.update(p for p in ('backend/conftest.py', 'pytest.ini', 'pyproject.toml') if (root / p).is_file())
    unresolved = {p: unknown[p] for p in inputs & unknown.keys()
                  if not protected_reason(p)}
    return {**change_plan, 'version': 1, 'inputs': sorted(inputs), 'tests': sorted(tests),
            'consumers': sorted(consumers - set(changes)), 'watch_roots': sorted(watch_roots),
            'external_modules': sorted(set().union(*(externals.get(p, set()) for p in inputs))),
            'unresolved': unresolved}


def watched_paths(root, scope):
    names = set(scope['inputs'])
    from program_versions import source_inventory
    for prefix in scope.get('watch_roots', []):
        names.update(prefix + '/' + p for p in source_inventory(Path(root) / prefix))
    for pattern in scope.get('watch_globs', []):
        names.update(p.relative_to(root).as_posix() for p in Path(root).glob(pattern) if p.is_file())
    return names


def with_derived_inputs(root, scope, outputs):
    """A global dictionary's sources really are shared inputs of its build."""
    vocabulary = set(outputs) - {'data/bodies/android.engine.json'}
    if vocabulary:
        patterns = ['data/ibl_nodes_src/*.yaml', 'scripts/iblbuild*.py', 'scripts/build_ibl_nodes.py',
                    'docs/generated_templates/*', 'data/vocabulary_policy.yaml',
                    'data/packages/*/tools/*/ibl_actions.yaml', 'data/packages/*/tools/*/tool.json',
                    'data/packages/*/tools/*/manifest.json', 'data/packages/*/tools/**/*.py']
        scope['watch_globs'] = patterns
        scope['unresolved']['vocabulary-build'] = 'shared builder environment'
    scope['inputs'] = sorted(set(scope['inputs']) | set(outputs))
    scope['inputs'] = sorted(watched_paths(Path(root), scope))
    return scope
