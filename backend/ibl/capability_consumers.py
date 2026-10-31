"""Project existing stored programs into change impact; the compiler owns validity."""
from pathlib import Path


def programs(root=None, functions=None):
    import function_store
    from function_consumers import stored_programs
    catalog = Path(functions) if functions else (Path(root) / 'data/workflows' if root else None)
    view = function_store.snapshot(catalog)
    for row in view['records'].values():
        if row.get('state') == 'active':
            yield 'function:' + row['name'], row['source']
    yield from stored_programs(root=catalog.parent.parent if catalog else root)
    if root and catalog and Path(root).resolve() != catalog.parent.parent.resolve():
        yield from stored_programs(root=root)


def nodes(source):
    from ibl_v2_parser import parse
    from ibl_v2_ir import Node
    pending = [parse(source)]
    while pending:
        value = pending.pop()
        if isinstance(value, Node):
            yield value
            pending.append(value.data)
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)


def references(kind, target, root=None, functions=None):
    """Literal references are evidence, dynamic selection is explicitly unknown."""
    from ibl_v2_ir import Fault
    found, unknown = [], []
    for location, source in programs(root, functions):
        if not isinstance(source, str):
            continue
        try:
            for node in nodes(source):
                if node.kind != 'call':
                    continue
                data = node.data
                if kind == 'action' and target == data['node'] + ':' + data['action']:
                    found.append({'location': location, 'source': source})
                    break
                if kind != 'script' or (data['node'], data['action']) != ('self', 'script'):
                    continue
                params = data['params'].data.get('fields', {})
                op = params.get('op')
                if op and op.kind == 'literal' and op.data['value'] != 'run':
                    continue
                sid = params.get('id')
                if sid is not None and sid.kind == 'literal':
                    if sid.data['value'] == target:
                        found.append({'location': location, 'source': source})
                        break
                elif sid is not None:
                    unknown.append({'location': location, 'reason': 'dynamic script id'})
        except Fault as exc:
            unknown.append({'location': location, 'reason': str(exc)})
    return {'callers': found, 'unknown': unknown,
            'coverage': 'active functions and structured persistent IBL; external Python and inactive consumers excluded'}


def validate_script_change(root, registry_path, before, after, sid, functions=None):
    """Use the same declared contract before/after; never execute consumer programs."""
    import function_library
    from ibl_dependencies import using_script_registry
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_ir import Fault
    from ibl_v2_types import UNKNOWN
    if sid not in before:
        return {'callers': [], 'unknown': []}
    impact = references('script', sid, root, functions)
    if sid not in after and impact['callers']:
        raise ValueError('스크립트 호출자를 먼저 전환하세요: ' + ', '.join(r['location'] for r in impact['callers']))
    if (before.get(sid) or {}).get('callable_contract') == (after.get(sid) or {}).get('callable_contract'):
        return impact
    import function_store
    library = function_library.definitions(function_store.snapshot(functions or Path(root) / 'data/workflows'))
    registry = load_registry()
    broken = []
    for row in impact['callers']:
        code = row['source']
        types = {n.data['name']: UNKNOWN for n in nodes(code) if n.kind == 'ref'}
        def issues(view):
            with using_script_registry(registry_path, view):
                try:
                    return compile_program(code, registry, definitions=library, input_types=types).issues
                except Fault as exc:
                    return [{'message': str(exc)}]
        if not issues(before) and issues(after):
            broken.append(row['location'])
    if broken:
        raise ValueError('스크립트 계약 변경으로 호출자가 깨집니다: ' + ', '.join(broken))
    return impact
