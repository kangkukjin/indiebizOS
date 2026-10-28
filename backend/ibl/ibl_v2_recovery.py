"""Failure/return/continuation transfer shared by source and stored relations.

This describes possible normal exits, not observed successes. Catchable faults
may enter recovery after partial assignments; no state or effect is rolled back.
Runtime alone decides catchability, cleanup precedence and receipt reuse.
"""
from dataclasses import dataclass, field

from ibl_v2_types import Type, UNKNOWN, NEVER, join


def has_return(value):
    from ibl_v2_ir import Node
    if isinstance(value, Node):
        if value.kind in ('lambda', 'def', 'parallel'):
            return False
        if value.kind == 'call' and (value.data['node'], value.data['action']) == ('table', 'each'):
            return has_return(value.data['params'])
        return value.kind == 'return' or has_return(value.data)
    children = value.values() if isinstance(value, dict) else value if isinstance(value, (tuple, list)) else ()
    return any(has_return(v) for v in children)


@dataclass
class Exits:
    normal: tuple | None = None  # (value type, continuing bindings)
    returned: Type = field(default_factory=lambda: NEVER)
    state: dict = field(default_factory=dict)


def join_exits(a, b):
    if a == NEVER:
        return b
    if b == NEVER:
        return a
    if not isinstance(a, Exits):
        return join(a, b)
    normal = a.normal or b.normal
    if a.normal is not None and b.normal is not None:
        av, ae = a.normal
        bv, be = b.normal
        normal = (join(av, bv), {k: join(ae[k], be[k]) for k in ae.keys() & be.keys()})
    state = {k: join(a.state[k], b.state[k]) for k in a.state.keys() & b.state.keys()}
    return Exits(normal, join(a.returned, b.returned), state)


def guarded(compiler, analyze, *, catches=False):
    previous = compiler.catch_value_faults
    compiler.catch_value_faults = previous or catches
    compiler.requirement_depth += 1
    try:
        return analyze()
    finally:
        compiler.catch_value_faults = previous
        compiler.requirement_depth -= 1


def fallback_type(compiler, left, right):
    return join(guarded(compiler, left, catches=True), guarded(compiler, right))


def recovery_exits(compiler, env, analyze, *, caught, cleanup, final_mutated, mutated, catch_mutated):
    """analyze(part, env) exports exits; partial state is deliberately widened.

    Cleanup sees returning and failing paths too. It cannot justify facts from
    just the normal end of the protected body, even without a catch clause.
    """
    body_env = env.copy()
    # Preserve the language's deferred value-fault checks inside try, even
    # without catch; execution still propagates the fault after cleanup.
    body = guarded(compiler, lambda: analyze('body', body_env), catches=True)
    catch_env = {**env, 'error': Type('Record')}
    catch_env.update(dict.fromkeys(set(mutated) & env.keys(), UNKNOWN))
    result = body
    if caught:
        recovered = guarded(compiler, lambda: analyze('catch', catch_env))
        bindings_to_restore = [catch_env, recovered.state]
        if recovered.normal is not None:
            bindings_to_restore.append(recovered.normal[1])
        for bindings in bindings_to_restore:
            if 'error' in env:
                bindings['error'] = env['error']
            else:
                bindings.pop('error', None)
        result = join_exits(body, recovered)
    if cleanup:
        # The adapter supplies the final environment even for returning paths.
        final_env = body_env.copy()
        if caught:
            final_env = {k: join(body_env[k], catch_env[k])
                         for k in body_env.keys() & catch_env.keys()}
        final_env.update(dict.fromkeys((set(mutated) | set(catch_mutated)) & env.keys(), UNKNOWN))
        final = analyze('final', final_env)
        if final.normal is not None and result.normal is not None:
            value, bindings = result.normal
            # Only assignments owned by finally replace continuing bindings.
            for name in final_mutated:
                bindings[name] = final_env.get(name, UNKNOWN)
            result.normal = value, bindings
        result.state = final_env
    return result


def source_recovery(compiler, node, env, names, readonly, final):
    from ibl_v2_analysis import assigned_names
    d = node.data

    def analyze(part, local):
        outer, compiler.returns = compiler.returns, []
        try:
            value = compiler.visit(d[part], local, names, readonly, final or part == 'final')
            returned = NEVER
            for item in compiler.returns:
                returned = join(returned, item)
            return Exits(None if compiler.returns_unconditionally(d[part]) else (value, local.copy()), returned, local.copy())
        finally:
            compiler.returns = outer

    exits = recovery_exits(compiler, env, analyze, caught=d['catch'] is not None,
                           cleanup=d['final'] is not None, final_mutated=assigned_names(d['final']),
                           mutated=assigned_names(d['body']), catch_mutated=assigned_names(d['catch']))
    if exits.returned != NEVER:
        compiler.returns.append(exits.returned)
    if exits.normal is not None:
        value, local = exits.normal
        env.clear()
        env.update(local)
        return join(value, exits.returned)
    return exits.returned


def relation_recovery(compiler, term, captured, site, apply):
    def analyze(part, local):
        exits = apply(compiler, term[part], local, site)
        # Export final bindings for cleanup, including a returning branch.
        local.clear()
        local.update(exits.state)
        return exits
    return recovery_exits(compiler, captured, analyze, caught=term['catch'] is not None,
                           cleanup=term['final'] is not None, final_mutated=term['final_mutated'], mutated=term['mutated'],
                           catch_mutated=term['catch_mutated'])
