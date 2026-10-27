"""One access summary for static checks and whole-branch runtime admission.

Admission precedes fanout, so reservations last for the entire branch, including
read/compute/write. Unknown internal targets require an explicit sequence. No
thread waits for a resource: cancellation and approval cannot strand locks.
"""
from dataclasses import dataclass
import copy

from ibl_v2_ir import Fault, Node
from ibl_v2_types import Type, UNKNOWN, infer, ordered_list


@dataclass(frozen=True)
class Access:
    mode: str
    resources: tuple | None
    action: str
    declared: bool
    relations: tuple = ()


def accesses(spec, contract, args, action, *, runtime=False, argument_types=None):
    from ibl_callable_contract import resource_values
    from ibl_run_journal import call_resources
    effects = set(contract['effects'])
    result = set()
    for mode in ('read', 'write'):
        declaration = contract.get(mode + '_resources')
        needed = (mode + '_external' in effects or mode == 'write' and 'unknown' in effects)
        if not declaration and not needed:
            continue
        if runtime:
            values = call_resources(spec, contract, args, mode,
                                    allow_bare=spec.resource_identity is None)
            resources = None if values is None else tuple(
                (r, p, tuple(i) if i else None) for r, p, i in values)
        else:
            values = resource_values(declaration, args, spec.resource_identity) if declaration else None
            resources = None if values is None else tuple((r, p, None) for r, p in values)
        from ibl_v2_requirements import origin
        relations = []
        for realm, selector in (declaration or {}).items():
            params = selector if isinstance(selector, list) else [selector] if isinstance(selector, str) else [selector['param'], selector.get('fallback')]
            for name in params:
                typ = (argument_types or {}).get(name, UNKNOWN)
                if (variable := origin(typ)):
                    relations.append((realm, name, variable))
        result.add(Access(mode, resources, action, bool(declaration), tuple(relations)))
    return result


def conflicts(left, right, *, unresolved=False, strict=False):
    from ibl_run_journal import resources_overlap
    result = set()
    for a in left:
        for b in right:
            if a.mode == b.mode == 'read':
                continue
            if a.resources is None or b.resources is None:
                if not unresolved or not (strict or a.declared and b.declared):
                    continue
            if resources_overlap(a.resources, b.resources):
                result.add((a.action, b.action))
    return result


def runtime_type(value, compiler):
    """Retain actual bindings once per shared value DAG; exhaustion stays unknown."""
    from common.expression_ops import CallableRef, Closure
    # Dataset structure is bounded; known scalar targets and callable identities
    # must not disappear merely because an earlier binding consumed that budget.
    if isinstance(value, str):
        return Type('Text', literal=value)
    if isinstance(value, CallableRef):
        node = Node('callable_ref', 0, 0, {'node': value.node, 'action': value.action})
        return compiler.reference_type(node, {value.action: value.symbol} if value.symbol else {})
    if not isinstance(value, (list, dict, Closure)):
        return infer(value)
    memo = getattr(compiler, 'runtime_types', None)
    if memo is None:
        compiler.runtime_types = memo = {}
    key = id(value)
    if key in memo:
        return memo[key]
    if len(memo) >= 4096:
        return UNKNOWN
    memo[key] = UNKNOWN  # cycle guard, never a proof of absent effects/resources
    if isinstance(value, list):
        result = ordered_list(runtime_type(v, compiler) for v in value)
    elif isinstance(value, dict):
        result = Type('Record', tuple((k, runtime_type(v, compiler)) for k, v in value.items()), open=False)
    elif isinstance(value, Closure):
        node = Node('lambda', value.body.start, value.body.end,
                    {'params': value.params, 'body': value.body})
        result = compiler.lambda_type(node, {k: runtime_type(v.value, compiler) for k, v in value.env.items()}, {}, frozenset())
    else:
        result = infer(value)
    memo[key] = result
    return result


def with_unknown(access_log, effects):
    result = set(access_log)
    if 'unknown' in effects:
        result.add(Access('write', None, '<input-dependent>', False))
    return result


def describe_accesses(access_log, effects=()):
    from ibl_v2_ir import digest
    rows = []
    for access in with_unknown(access_log, effects):
        rows.append({'mode': access.mode, 'action': access.action,
                     'resource_state': 'unresolved' if access.resources is None else 'resolved',
                     'resource_hash': digest(access.resources) if access.resources is not None else None,
                     'declared': access.declared,
                     'relations': [{'realm': realm, 'argument': name, 'variable': list(variable)}
                                   for realm, name, variable in access.relations]})
    rows.sort(key=lambda row: (row['action'], row['mode'], str(row['resource_hash']), str(row['relations'])))
    return {'protocol': 'ibl-access/1', 'entries': rows[:24], 'omitted': max(0, len(rows) - 24)}


def admit(runtime, node, branches):
    """Analyze actual bindings without invoking tools or applying user callbacks."""
    from ibl_v2_compile import Compiler
    plan = runtime.plan
    if plan.effects <= {'pure', 'read_external', 'model'}:
        return []
    summaries = set()
    for branch, env in branches:
        runtime.check()
        compiler = Compiler(plan.source, plan.registry, {}, plan.definitions)
        compiler.resource_runtime = True
        compiler.functions = copy.deepcopy(plan.functions)
        compiler.function_scopes = copy.deepcopy(plan.function_scopes)
        types = {k: runtime_type(v.value, compiler) for k, v in env.items()}
        compiler.visit(copy.deepcopy(branch), types, {})
        if compiler.issues:
            raise Fault('PARALLEL_RESOURCE_UNKNOWN', '병렬 구간의 접근 요약을 확정할 수 없습니다.',
                        node, kind='protocol', details={'issues': compiler.issues[:4]})
        current = frozenset(with_unknown(compiler.access_log, compiler.effects))
        for previous in summaries:
            overlap = conflicts(previous, current, unresolved=True, strict=runtime.strict_composition)
            if overlap:
                raise Fault('PARALLEL_RESOURCE_CONFLICT',
                            '병렬 가지의 읽기/쓰기 자원 독립성을 확보할 수 없습니다. 순서를 명시하세요.',
                            node, kind='protocol', details={'actions': sorted(overlap)})
        summaries.add(current)
        if len(summaries) > 1024:
            raise Fault('PARALLEL_RESOURCE_LIMIT', '자원 구간이 1024개를 넘습니다. 명시적으로 묶음을 나누세요.', node, kind='budget')
    return summaries
