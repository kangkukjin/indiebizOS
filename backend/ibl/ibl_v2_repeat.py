"""Finite repeat-state transfer, shared by source and stored abilities.

This computes an inductive abstract state, never iterations of business values.
Changing shapes widen; stable record fields, callable/ref ownership and effects
remain available to callers. Runtime alone owns actual termination and receipts.
"""
from dataclasses import replace

from ibl_v2_types import Type, UNKNOWN, NEVER, NUMBER, BOOL, UNIT_T, join
from ibl_v2_recovery import Exits, guarded


def widen(previous, following, depth=0):
    if previous == following:
        return previous
    if depth >= 8:
        return UNKNOWN
    if previous.kind == following.kind == 'Record':
        left, right = dict(previous.fields), dict(following.fields)
        return Type('Record', tuple((k, widen(left[k], right[k], depth + 1))
                                   for k in sorted(left.keys() & right.keys())),
                    open=previous.open or following.open or left.keys() != right.keys())
    if previous.kind == following.kind == 'List':
        if previous.positions == ():
            return Type('List', item=following.item)
        if following.positions == ():
            return Type('List', item=previous.item)
        return Type('List', item=widen(previous.item, following.item, depth + 1))
    if previous.kind == following.kind and previous.kind in ('Text', 'Number', 'Bool'):
        return replace(previous, literal=None, choices=None)
    return join(previous, following)


def repeat_exits(compiler, site, env, mode, condition, body, *, unreachable=None):
    """condition(local) -> Type, body(local) -> Exits; both retain obligations."""
    count = None
    if mode == 'count':
        typ = condition(env.copy())
        compiler.need(site, typ, NUMBER)
        count = typ.literal
        if count is not None and (type(count) is not int or count < 0):
            compiler.issue(site, 'REPEAT_COUNT', 'repeat 횟수는 0 이상의 정수입니다.')
            count = None
    initial = {**env, 'i': NUMBER}
    guaranteed = mode == 'until' or type(count) is int and count > 0
    if count == 0:
        if unreachable is not None:
            unreachable(initial.copy())
        return Exits((UNIT_T, env.copy()), state=env.copy())

    def step(state):
        local = state.copy()
        if mode == 'while':
            compiler.need(site, condition(local), BOOL)
        outcome = body(local) if guaranteed else guarded(compiler, lambda: body(local))
        if mode == 'until' and outcome.normal is not None:
            compiler.need(site, condition(outcome.normal[1]), BOOL)
        return outcome

    state = initial
    returned = NEVER
    for turn in range(10):
        outcome = step(state)
        returned = join(returned, outcome.returned)
        if count == 1 or outcome.normal is None:
            break
        after = outcome.normal[1]
        # Only names available before the first round are loop-head inputs.
        # Body-local names are still exported from the final normal round.
        candidate = {k: widen(state[k], after.get(k, state[k])) for k in initial}
        if candidate == state:
            break
        if turn == 8:
            candidate = {k: state[k] if candidate[k] == state[k] else UNKNOWN for k in initial}
        state = candidate
    else:
        # UNKNOWN is absorbing; this guard protects future domain extensions.
        state = {k: UNKNOWN for k in initial}
        outcome = step(state)
        returned = join(returned, outcome.returned)

    def restore(local):
        local = local.copy()
        if 'i' in env:
            local['i'] = env['i']
        else:
            local.pop('i', None)
        return local

    normal = None
    if outcome.normal is not None:
        after = restore(outcome.normal[1])
        if not guaranteed:
            after = {k: join(env[k], after[k]) for k in env.keys() & after.keys()}
        normal = UNIT_T, after
    elif not guaranteed:
        normal = UNIT_T, env.copy()
    end_state = restore(outcome.state)
    if not guaranteed:
        end_state = {k: join(env[k], end_state[k]) for k in env.keys() & end_state.keys()}
    return Exits(normal, returned, end_state)


def source_repeat(compiler, node, env, names, readonly, final):
    d = node.data
    compiler.pure(d['value'])
    if d['mode'] == 'count' and d['value'].kind == 'literal':
        count = d['value'].data['value']
        if type(count) is not int or count < 0:
            compiler.issue(d['value'], 'REPEAT_COUNT', 'repeat 횟수는 0 이상의 정수입니다.')

    from ibl_v2_exits import source_exits, export_source

    def body(local):
        return source_exits(compiler, d['body'], local, names, readonly, final)

    exits = repeat_exits(compiler, node, env, d['mode'],
                         lambda local: compiler.visit(d['value'], local, names, readonly, final), body,
                         unreachable=lambda local: compiler.visit_branch(d['body'], local, names, readonly, final, False))
    return export_source(compiler, exits, env)


def relation_repeat(compiler, term, captured, site, apply):
    return repeat_exits(compiler, site, captured, term['mode'],
                        lambda local: apply(compiler, term['condition'], local, site),
                        lambda local: apply(compiler, term['body'], local, site))
