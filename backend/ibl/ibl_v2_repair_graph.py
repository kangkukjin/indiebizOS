"""Compiler-proven repair frontier, independent of call syntax or nesting depth.

Keep the effect-bearing execution prefix and its definition dependencies fixed.
Only the remaining computation may change. Unknown summaries are barriers.
This is deliberately not a solver for arbitrary program equivalence.
"""
from ibl_v2_ir import Node, digest
from ibl_v2_parser import parse


def walk(value):
    if isinstance(value, Node):
        yield value
        yield from walk(value.data)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from walk(item)


def frontier(plan, source):
    from ibl_v2_repair import structural, node_paths
    parsed = parse(source)
    statements = parsed.data['statements']
    expanded = parse(plan.source).data['statements']
    definitions = {n.data['name']: n for n in expanded if n.kind == 'def'}
    summaries = {c['name']: c for sid, c in plan.function_contracts.items()
                 if sid in {n.id for n in expanded if n.kind == 'def'}}
    executable = [n for n in statements if n.kind != 'def']
    pure = lambda n: n.id in plan.node_effects and not (plan.node_effects[n.id] - {'pure'})
    last_effect = max((i for i, n in enumerate(executable) if not pure(n)), default=-1)
    prefix = executable[:last_effect + 1]
    suffix = executable[last_effect + 1:]
    locked = {name for name, n in definitions.items()
              if name not in summaries or set(summaries[name]['effects']) - {'pure'}
              or n.data.get('contract') is not None}

    def references(nodes):
        # Named reference dependencies include defaults, captures and callbacks.
        # A computed callable is conservative: it can depend on any definition.
        refs = set()
        for n in walk(nodes):
            if n.data.get('node') == 'fn' and 'action' in n.data:
                refs.add(n.data['action'])
            if n.kind in ('pure_call', 'named_call'):
                refs.update(definitions)
        return refs & definitions.keys()

    locked |= references(prefix)
    pending = list(locked)
    while pending:
        name = pending.pop()
        for target in references(definitions[name]) - locked:
            locked.add(target)
            pending.append(target)
    retained = {f'prefix:{i}': n for i, n in enumerate(prefix)}
    retained.update({f'definition:{name}': definitions[name] for name in sorted(locked)})
    return {'protocol': 'ibl-repair-frontier/1',
            'retained': {key: structural(n) for key, n in retained.items()},
            'nodes': {key: [[list(path), nid] for path, nid in node_paths(n)] for key, n in retained.items()},
            'suffix_proven': bool(suffix) and all(pure(n) for n in suffix),
            'completion': {name: digest(structural(n.data.get('contract')))
                           for name, n in definitions.items() if n.data.get('contract') is not None}}


def mapping(before, after):
    from ibl_v2_ir import Fault
    if (not before or not after or not before['suffix_proven'] or not after['suffix_proven']
            or before['retained'] != after['retained'] or before['completion'] != after['completion']):
        raise Fault('REPAIR_UNSUPPORTED', '효과 접두부·의존 정의·완료 의무를 보존하는 순수 계산 수정만 계승합니다.', kind='protocol')
    result = {}
    for key, entries in before['nodes'].items():
        previous = {tuple(path): nid for path, nid in entries}
        for path, nid in after['nodes'][key]:
            result[nid] = previous[tuple(path)]
    return result
