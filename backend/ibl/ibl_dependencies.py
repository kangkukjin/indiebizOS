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
    import_root = root / str(entry.get('file') or '') if entry else root
    # Python의 스크립트 검색 경로는 링크 이름이 아니라 실제 진입 파일의 디렉터리다.
    import_root = import_root.resolve().parent if entry else root
    if not dynamic:
        pending = [root / str(entry.get('file') or '')]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            files[str(path)] = 'missing'
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
            module_root = import_root
            if isinstance(node, ast.Import):
                modules = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    module_root = path.parent
                    for _ in range(node.level - 1):
                        module_root = module_root.parent
                modules = [node.module or ''] + [node.module + '.' + n.name if node.module else n.name for n in node.names]
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                if name in {'eval', 'exec', '__import__', 'import_module', 'load_sibling', 'load_singleton', 'run_path', 'spec_from_file_location', 'run', 'Popen', 'system'}:
                    dynamic = True
            modules = sorted({'.'.join(parts[:i]) for m in modules if m
                              for parts in [m.split('.')] for i in range(1, len(parts)+1)})  # path-ok: Python 패키지 초기화 모듈도 의존성
            for module in modules:
                candidate = module_root.joinpath(*module.split('.'))  # path-ok: Python import 모듈명 해소, 데이터 필드 경로 아님
                for target in (candidate.with_suffix('.py'), candidate / '__init__.py'):
                    # Absent local imports are dependencies too: adding one may
                    # change Python's resolution order on the next execution.
                    files[str(target)] = digest(target.read_bytes().hex()) if target.is_file() else 'missing'
                    if target.is_file():
                        pending.append(target)
    if dynamic:
        files.update({str(p): digest(p.read_bytes().hex()) for p in sorted(root.rglob('*'))
                      if p.is_file() and p.suffix in {'.py', '.sh', '.js'} and '__pycache__' not in p.parts})
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


def legacy_runtime_snapshot():
    """Legacy function effects are opaque: pin their declared interpreter realm."""
    from runtime_utils import get_base_path
    from ibl_registry import load_nodes_installed
    root = get_base_path()
    paths = list(Path(__file__).parent.glob('*.py'))
    paths += [p for p in (root/'data/packages/installed/tools').rglob('*.py')
              if '__pycache__' not in p.parts and not p.name.startswith('test_')]
    return digest({'files': {str(p): digest(p.read_bytes().hex()) for p in sorted(paths)},
                   'vocabulary': load_nodes_installed(), 'scripts': script_snapshot({})})
