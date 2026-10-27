"""Dependency snapshots for declared scripts and JSON handler boundaries."""
import ast
from contextlib import contextmanager
from contextvars import ContextVar
import copy
from pathlib import Path
import yaml
from ibl_v2_ir import digest


_check_metadata = ContextVar("ibl_check_metadata", default=None)


@contextmanager
def compilation_dependencies():
    """One check observes one metadata snapshot; execution never inherits it."""
    token = _check_metadata.set({})
    try:
        yield
    finally:
        _check_metadata.reset(token)


def _check_value(key, read):
    cache = _check_metadata.get()
    if cache is None:
        return read()
    if key not in cache:
        cache[key] = read()
    return cache[key]


def _script_registry(path):
    return _check_value(
        ("registry", str(path)),
        lambda: (yaml.safe_load(path.read_text()) or {}) if path.is_file() else {},
    )


def script_snapshot(args, root=None, *, binding=False, invocation=False):
    if 'path' in args and args.get('op', 'run') == 'run':
        # A preceding write may create this file. Pin bytes in the receipt at invocation.
        return {'scope': 'invocation-file', 'protocol': 'file-script/1'}
    from runtime_utils import get_base_path
    from thread_context import get_repair_workspace
    root = Path(root) if root else Path(get_repair_workspace(create=bool(args)) or get_base_path()) / 'data/scripts'
    sid = args.get('id')
    operation = args.get('op', 'run' if sid else 'list')
    registry = _script_registry(root / 'registry.yaml')
    if binding and (operation != 'run' or not isinstance(sid, str) or sid not in registry):
        # Management reads the current registry. New/dynamic IDs cannot have an
        # executable definition pinned yet, just like a file created earlier in
        # the program. Pin the resolved bytes/contract at invocation instead.
        return {'binding': 'invocation', 'scope': 'registered-script', 'protocol': 'registered-json/1'}
    if invocation and operation != 'run':
        return {'scope': 'script-management', 'registry': digest(registry)}
    key = ("snapshot", str(root), digest([sid, operation]))
    # Call sites own their snapshots. Do not let one mutate another's evidence.
    return copy.deepcopy(_check_value(key, lambda: _script_snapshot(root, sid, operation, registry)))


def script_dependency(args):
    """Compiler binding policy; raw namespace snapshots retain their full evidence."""
    return script_snapshot(args, binding=True)


def script_invocation_snapshot(args):
    return script_snapshot(args, invocation=True)


def _script_snapshot(root, sid, operation, registry=None):
    if registry is None:
        registry = _script_registry(root / 'registry.yaml')
    entry = registry.get(sid) if isinstance(sid, str) else None
    # Dynamic selection and list/register/remove observe the whole namespace.
    dynamic = not entry or operation != 'run'
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
    snapshot = {'scope': 'script-namespace' if dynamic else 'script-closure',
                'registry': digest(registry if dynamic else {sid: entry}), 'files': files}
    if entry and entry.get('interpreter') == 'python':
        from python_environment_lock import fingerprint
        from runtime_utils import get_python_cmd
        environment = _check_value(("environment", str(import_root)),
                                   lambda: fingerprint(import_root))
        snapshot.update(environment=environment, interpreter=get_python_cmd())
    return snapshot


def script_contract(base, args):
    """Resolve a registered script's value/effect contract for check and run alike.

    Dynamic/remote/file calls retain the conservative outer contract. Background
    run returns a receipt; only its later task result has the script value type.
    """
    from member_runtime import is_member
    from ibl_callable_contract import UNRESOLVED
    if is_member() or args.get('op', 'run' if args.get('id') else 'list') != 'run':
        return base
    sid = args.get('id')
    if not isinstance(sid, str) or args.get('background', False) is UNRESOLVED:
        return base
    from runtime_utils import get_base_path
    from thread_context import get_repair_workspace
    path = Path(get_repair_workspace() or get_base_path()) / 'data/scripts/registry.yaml'
    registry = _script_registry(path)
    contract = ((registry or {}).get(sid) or {}).get('callable_contract')
    if not contract or contract.get('adapter', {}).get('protocol') == 'ibl-script-session/1':
        return base
    from ibl_v2_adapters import validate_contract
    validate_contract(contract)
    from ibl_callable_contract import normalize, selected
    nested = args.get('args')
    if isinstance(nested, dict):
        contract = selected(contract, normalize(contract, nested))
    elif nested is None:
        contract = selected(contract, {})
    if args.get('background'):
        return {**base, 'result': 'Record', 'effects': ['write_external'],
                'nested_contracts': {'args': contract}}
    # Nested input aliases/defaults use the same boundary resolver as the runner.
    from ibl_v2_component import lift_completion
    completion = lift_completion(contract.get('completion', []), 'args')
    return {**base, 'nested_contracts': {'args': contract}, 'completion': completion,
            'result': contract['result'], 'effects': contract['effects'],
            'per_run': contract.get('per_run', False) or contract['effects'] != ['pure'],
            'script_contract': contract}
