"""Conditional input requirements and consumer wire obligations.

Requirements are analysis data, never values or authority. A symbolic input is
distinct from an unconstrained Unknown; concrete calls still analyze the body.
"""
from ibl_v2_types import Type, UNKNOWN, describe_type
from ibl_v2_ir import Node


def parameter(sid, name):
    return Type('Unknown', item=('parameter', sid, name))


def origin(typ):
    if typ.kind == 'Unknown' and isinstance(typ.item, tuple) and typ.item[0] in ('parameter', 'application'):
        return typ.item
    return None


def require(compiler, node, actual, expected):
    identity = origin(actual)
    if not identity:
        return
    kind, sid, name = identity
    entry = compiler.requirements.setdefault(sid, {}).setdefault(name, [])
    condition = {'kind': 'result' if kind == 'application' else 'value',
                 'expected': describe_type(expected),
                 'at': node.start, 'conditional': bool(compiler.requirement_depth)}
    if condition not in entry:
        entry.append(condition)


def application(compiler, node, typ, types, pure=False):
    identity = origin(typ)
    if not identity or identity[0] != 'parameter':
        return None
    _, sid, name = identity
    entry = compiler.requirements.setdefault(sid, {}).setdefault(name, [])
    named = isinstance(types, Type)
    condition = {'kind': 'callable', 'argument_style': 'named' if named else 'positional',
                 'arguments': describe_type(types) if named else [describe_type(t) for t in types],
                 'effects': ['pure'] if pure else ['input-dependent'],
                 'at': node.start, 'conditional': bool(compiler.requirement_depth)}
    entry.append(condition)
    compiler.required_calls[node.id] = condition
    return Type('Unknown', item=('application', sid, name))


def wire_obligations(typ, protocols=('ibl-value/1', 'ibl-value/2'), *, typed_paths=False):
    """Bounded recursive wire check. Unknown/mixed alternatives remain duties."""
    failures, pending = [], []
    budget = [2048]

    def walk(value, path, ancestors=frozenset()):
        budget[0] -= 1
        if budget[0] < 0 or id(value) in ancestors:
            pending.append(path)
            return
        ancestors = ancestors | {id(value)}
        if value.kind == 'Callable' or value.kind == 'ForeignRef' and 'ibl-value/2' not in protocols:
            failures.append(path)
        elif value.kind == 'Unknown':
            pending.append(path)
        elif value.kind == 'Union':
            for member in value.item:
                walk(member, path, ancestors)
        elif value.kind == 'Record':
            for name, member in value.fields:
                walk(member, path + (name,), ancestors)
            if value.open:
                pending.append(path + ('*',))
        elif value.kind == 'List':
            if value.positions is not None:
                for i, member in enumerate(value.positions):
                    walk(member, path + (i,), ancestors)
            else:
                # Empty lists are possible: an element obligation is conditional.
                before = len(failures)
                walk(value.item or UNKNOWN, path + ('[*]',), ancestors)
                pending.extend(failures[before:])
                del failures[before:]
        elif value.kind == 'Result':
            before = len(failures)
            walk(value.item or UNKNOWN, path + ('value',), ancestors)
            pending.extend(failures[before:])
            del failures[before:]

    walk(typ, ())
    if typed_paths:
        return list(dict.fromkeys(failures)), list(dict.fromkeys(pending))
    return sorted({wire_path(p) for p in failures}), sorted({wire_path(p) for p in pending})


def wire_path(path):
    return '$' + ''.join(f'[{p}]' if isinstance(p, int) else p if p == '[*]' else '.' + p for p in path)


def require_wire(plan, protocols=None):
    from ibl_v2_ir import span
    from dataclasses import replace
    plan = replace(plan, issues=[i for i in plan.issues if i.get('boundary') != 'top-level-wire'],
                   guards=[g for g in plan.guards if g.get('boundary') != 'top-level-wire'])
    protocols = sorted(protocols or ('ibl-value/1', 'ibl-value/2'))
    failures, pending = wire_obligations(plan.result_type, protocols, typed_paths=True)
    for path in failures:
        item = {'boundary': 'top-level-wire', 'code': 'VALUE_PROTOCOL', 'message': '최상위 반환을 전송할 수 없습니다: ' + wire_path(path),
                'path': wire_path(path), 'details': {'path': list(path), 'protocols': protocols}, 'protocols': list(protocols), 'source_span': span(plan.source, plan.root)}
        if item not in plan.issues:
            plan.issues.append(item)
    if pending:
        item = {'boundary': 'top-level-wire', 'expected': '최상위 값의 전송 가능성을 실행 경계에서 확인합니다.',
                'paths': [wire_path(p) for p in pending[:24]], 'paths_omitted': max(0, len(pending) - 24),
                'source_span': span(plan.source, plan.root)}
        if item not in plan.guards:
            plan.guards.append(item)
    return plan


def annotation(compiler, node, actual, expected):
    """Use the same Type and callable application engine for explicit contracts."""
    from ibl_v2_types import NEVER, declared
    if expected.kind != 'Callable' or not expected.item or expected.item[0] != 'requirement':
        compiler.need(node, actual, expected)
        return
    if actual.kind == 'Unknown':
        compiler.need(node, actual, expected)
        return
    _, params, result, effects = expected.item
    old_effects, compiler.effects = compiler.effects, set()
    old_accesses, compiler.access_log = compiler.access_log, set()
    try:
        args = list(params) if isinstance(params, tuple) else params
        nodes = [node] * len(args) if isinstance(args, list) else Node('record', node.start, node.end, {'fields': {}})
        returned = compiler.apply_callable(node, actual, args, nodes, require_pure=effects == ('pure',))
        compiler.need(node, returned, result)
        if compiler.effects - set(effects) - {'pure'}:
            compiler.issue(node, 'CALLABLE_REQUIREMENT', '콜백 효과가 명시 계약을 넘습니다.',
                           expected=list(effects), actual=sorted(compiler.effects))
    finally:
        compiler.effects = old_effects  # checking a latent body does not execute it
        compiler.access_log = old_accesses


def runtime_annotations(runtime, definition, values):
    from ibl_v2_compile import Compiler
    from ibl_v2_access import runtime_type
    from ibl_v2_analysis import constant_value
    from ibl_v2_types import declared
    from ibl_v2_ir import Fault
    compiler = Compiler(runtime.plan.source, runtime.plan.registry, {}, runtime.plan.definitions)
    compiler.functions = runtime.plan.functions
    compiler.function_scopes = runtime.plan.function_scopes
    for name, node in definition.data.get('annotations', {}).items():
        expected = declared(constant_value(node))
        actual = runtime_type(values[name].value, compiler)
        annotation(compiler, node, actual, expected)
    if compiler.issues or compiler.guards:
        raise Fault('CALLABLE_REQUIREMENT', '함수 입구의 명시 계약을 충족했는지 확인할 수 없습니다.',
                    definition, kind='protocol', details={'issues': compiler.issues, 'guards': compiler.guards})
