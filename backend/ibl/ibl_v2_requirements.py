"""Conditional input requirements and consumer wire obligations.

Requirements are analysis data, never values or authority. A symbolic input is
distinct from an unconstrained Unknown; concrete calls still analyze the body.
"""
from ibl_v2_types import Type, UNKNOWN, describe_type
from ibl_v2_ir import Node


def parameter(sid, name):
    return Type('Unknown', item=('parameter', sid, name, ()))


def origin(typ):
    if typ.kind == 'Unknown' and isinstance(typ.item, tuple) and typ.item[0] in ('parameter', 'application'):
        return typ.item
    return None



def project(typ, key):
    """Keep a finite projection on the same symbolic input or application."""
    identity = origin(typ)
    if not identity or not isinstance(key, (str, int)) or isinstance(key, bool):
        return UNKNOWN
    kind, sid, name, *tail = identity
    path = tail[0] if tail else ()
    if len(path) >= 64:
        return UNKNOWN
    return Type('Unknown', item=(kind, sid, name, (*path, key), *tail[1:]))


def emit(compiler, sid, name, condition, expected, depth):
    key = (sid, name, repr(condition), expected, depth)
    compiler.requirement_log.setdefault(key, (sid, name, condition, expected, depth))


def require(compiler, node, actual, expected):
    identity = origin(actual)
    if not identity or not compiler.reachable:
        return
    kind, sid, name, *tail = identity
    condition = {'kind': 'result' if kind == 'application' else 'value',
                 'expected': describe_type(expected),
                 'at': node.start, 'conditional': bool(compiler.requirement_depth),
                 'path': list(tail[0]) if tail else [],
                 **({'application': tail[1]} if kind == 'application' and len(tail) > 1 else {})}
    emit(compiler, sid, name, condition, expected, compiler.requirement_depth)


def application(compiler, node, typ, types, pure=False):
    identity = origin(typ)
    if not identity:
        return None
    _, sid, name, *tail = identity
    named = isinstance(types, Type)
    condition = {'kind': 'callable', 'argument_style': 'named' if named else 'positional',
                 'arguments': describe_type(types) if named else [describe_type(t) for t in types],
                 'effects': ['pure'] if pure else ['input-dependent'],
                 'at': node.start, 'conditional': bool(compiler.requirement_depth),
                 'path': list(tail[0]) if tail else []}
    emit(compiler, sid, name, condition, Type('Callable'), compiler.requirement_depth)
    compiler.required_calls[node.id] = condition
    return Type('Unknown', item=('application', sid, name, (),
        __import__('ibl_v2_ir').digest([node.id, identity,
            types._key.hex() if named else [t._key.hex() for t in types]])))


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
            alternatives = []
            for member in value.item:
                before = len(failures)
                walk(member, path, ancestors)
                alternatives.append(failures[before:])
                del failures[before:]
            if alternatives and all(alternatives):
                # All alternatives fail, possibly at different nested paths.
                failures.append(path)
            else:
                pending.extend(p for paths in alternatives for p in paths)
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
    from ibl_v2_types import NEVER, compatible
    if actual == NEVER or expected.kind == 'Unknown':
        return
    if actual.kind == 'Union':
        for member in actual.item:
            annotation(compiler, node, member, expected)
        return
    if expected.kind == 'Union':
        choices = [v for v in expected.item if compatible(actual, v)]
        failures = []
        for choice in choices:
            old_issues, old_guards = compiler.issues, compiler.guards
            old_log = compiler.requirement_log
            compiler.issues, compiler.guards, compiler.requirement_log = [], [], {}
            try:
                annotation(compiler, node, actual, choice)
                issues, guards, requirements = compiler.issues, compiler.guards, compiler.requirement_log
            finally:
                compiler.issues, compiler.guards, compiler.requirement_log = old_issues, old_guards, old_log
            if not issues:
                compiler.guards.extend(guards)
                compiler.requirement_log.update(requirements)
                return
            failures.extend(issues)
        if failures:
            compiler.issue(node, 'CALLABLE_REQUIREMENT', '어느 계약 대안도 충족하지 않습니다.', issues=failures)
        else:
            compiler.need(node, actual, expected)
        return
    if actual.kind == 'Unknown' or actual.kind != expected.kind:
        compiler.need(node, actual, expected)
        return
    if expected.kind == 'Record':
        fields = dict(actual.fields)
        for key, member in expected.fields:
            if key in fields:
                annotation(compiler, node, fields[key], member)
            else:
                compiler.need(node, actual, expected)
        return
    if expected.kind in ('List', 'Result'):
        members = actual.positions if actual.kind == 'List' and actual.positions is not None else (actual.item or UNKNOWN,)
        for member in members:
            annotation(compiler, node, member, expected.item or UNKNOWN)
        return
    if expected.kind != 'Callable' or not expected.item or expected.item[0] != 'requirement':
        compiler.need(node, actual, expected)
        return
    _, params, result, effects = expected.item
    old_effects, compiler.effects = compiler.effects, set()
    old_accesses, compiler.access_log = compiler.access_log, set()
    try:
        args = list(params) if isinstance(params, tuple) else params
        nodes = [node] * len(args) if isinstance(args, list) else Node('record', node.start, node.end, {'fields': {}})
        returned = compiler.apply_callable(node, actual, args, nodes, require_pure=effects == ('pure',))
        annotation(compiler, node, returned, result)
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


def intersection(left, right):
    """A bounded satisfiability meet; empty Lists/failed Results remain possible."""
    from ibl_v2_types import NEVER, join
    if left.kind == 'Unknown':
        return right
    if right.kind == 'Unknown' or left == right:
        return left
    if left.kind == 'Union' or right.kind == 'Union':
        choices = left.item if left.kind == 'Union' else (left,)
        others = right.item if right.kind == 'Union' else (right,)
        result = NEVER
        for a in choices:
            for b in others:
                result = join(result, intersection(a, b))
        return result
    if left.kind != right.kind:
        return NEVER
    if left.kind == 'Record':
        fields = dict(left.fields)
        for key, value in right.fields:
            member = intersection(fields.get(key, UNKNOWN), value)
            if member == NEVER:
                return NEVER
            fields[key] = member
        return Type('Record', tuple(sorted(fields.items())), open=left.open and right.open)
    # Callable signature/effect implications are checked by application, not by
    # pretending nominal compatibility proves a higher-order contract.
    return left


def finish(compiler):
    """Publish the same compositional constraints to check/describe/storage."""
    from ibl_v2_types import NEVER
    unconditional = {}
    for sid, name, entry, expected, depth in compiler.requirement_log.values():
        condition = {**entry, 'conditional': bool(depth)}
        bucket = compiler.requirements.setdefault(sid, {}).setdefault(name, [])
        if condition not in bucket:
            bucket.append(condition)
        # Different callback applications need not return the same type.
        if depth:
            continue
        key = sid, name, tuple(entry.get('path', ())), entry.get('application')
        previous = unconditional.get(key, UNKNOWN)
        merged = intersection(previous, expected)
        if merged == NEVER and previous != NEVER:
            node = compiler.functions.get(sid) or Node('requirement', entry['at'], entry['at'])
            compiler.issue(node, 'REQUIREMENT_CONFLICT', '같은 입력의 무조건 요구를 함께 만족시킬 수 없습니다.',
                           parameter=name, requirements=bucket)
        unconditional[key] = merged
    for sid, contract in compiler.function_contracts.items():
        contract['requirements'] = compiler.requirements.get(sid, {})
