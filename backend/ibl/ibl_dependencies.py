"""Dependency snapshots for declared script and legacy callable boundaries."""
import ast
from pathlib import Path
import yaml
from ibl_v2_ir import digest


def script_snapshot(args, root=None):
    from runtime_utils import get_base_path
    root = Path(root) if root else get_base_path() / 'data/scripts'
    registry_path = root / 'registry.yaml'
    registry = yaml.safe_load(registry_path.read_text()) if registry_path.exists() else {}
    registry = registry or {}
    sid = args.get('id')
    entry = registry.get(sid) if isinstance(sid, str) else None
    # Dynamic selection and list/register/remove observe the whole namespace.
    dynamic = not entry or args.get('op', 'run' if sid else 'list') != 'run'
    files, pending, seen = {}, [], set()
    if not dynamic:
        pending = [root / str(entry.get('file') or '')]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        if path.is_symlink() or not path.is_file():
            files[str(path)] = 'missing-or-symlink'
            continue
        files[str(path)] = digest(path.read_bytes().hex())
        if path.suffix != '.py':
            dynamic = True
            break
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeError):
            dynamic = True
            break
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ''] + [node.module + '.' + n.name if node.module else n.name for n in node.names]
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                if name in {'eval', 'exec', '__import__', 'import_module', 'load_sibling', 'load_singleton', 'run_path', 'spec_from_file_location', 'run', 'Popen', 'system'}:
                    dynamic = True
            for module in modules:
                candidate = root.joinpath(*module.split('.'))  # path-ok: Python import 모듈명 해소, 데이터 필드 경로 아님
                for target in (candidate.with_suffix('.py'), candidate / '__init__.py'):
                    # Absent local imports are dependencies too: adding one may
                    # change Python's resolution order on the next execution.
                    files[str(target)] = digest(target.read_bytes().hex()) if target.is_file() else 'missing'
                    if target.is_file():
                        pending.append(target)
    if dynamic:
        files = {str(p): digest(p.read_bytes().hex()) for p in sorted(root.rglob('*'))
                 if p.is_file() and not p.is_symlink() and p.suffix in {'.py', '.sh', '.js'} and '__pycache__' not in p.parts}
    return {'scope': 'script-namespace' if dynamic else 'script-closure',
            'registry': digest(registry if dynamic else {sid: entry}), 'files': files}


def legacy_snapshot(name, assets):
    """Resolve static transitive calls; opaque generated source stays conservative."""
    from ibl_parser import parse
    selected, pending, dynamic = {}, [name], False
    strings = set()
    def scan(value):
        nonlocal dynamic
        if isinstance(value, dict):
            if value.get('_node') == 'fn':
                target = value.get('action')
                if target in assets:
                    pending.append(target)
                else:
                    dynamic = True
            for v in value.values():
                scan(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                scan(v)
        elif isinstance(value, str) and '[' in value and ':' in value and value not in strings:
            strings.add(value)
            try:
                parsed = parse(value)
            except Exception:
                dynamic = True
                return
            # Only visit parsed structure, not its original string again.
            for step in parsed:
                scan(step)
    while pending and not dynamic:
        key = pending.pop()
        if key in selected:
            continue
        selected[key] = assets.get(key)
        if selected[key] is None:
            continue
        scan(selected[key])
    return digest(assets if dynamic else selected)
