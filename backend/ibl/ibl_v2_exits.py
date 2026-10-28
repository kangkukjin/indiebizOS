"""Value-producing control flow: normal values and nonlocal returns stay apart.

A continuation consumes only normal exits. Function/each/parallel frames consume
returns; recovery consumes Faults, never returns. These are abstract transfers,
not execution receipts or an evaluation of business values.
"""
from ibl_v2_types import NEVER, UNKNOWN, UNIT_T, join
from ibl_v2_recovery import Exits, guarded, join_exits


def value_control(node):
    if node is None:
        return False
    d, kind = node.data, node.kind
    if kind in ('sequence', 'if', 'case', 'try', 'repeat', 'fallback'):
        return True
    if kind in ('bind', 'return'):
        return value_control(d['value'])
    if kind == 'pipe':
        return value_control(d['left']) or value_control(d['right'])
    if kind == 'named_call':
        return value_control(d['fn'])
    return False


def continue_exits(exits, follow):
    if exits.returned == NEVER and exits.normal is not None:
        return follow(*exits.normal)
    result = Exits(returned=exits.returned, state=exits.state)
    if exits.normal is not None:
        result = join_exits(result, follow(*exits.normal))
    return result


def transform_exit(exits, *, binding=None, returned=False):
    def follow(value, env):
        local = env.copy()
        if returned:
            return Exits(returned=value, state=local)
        local[binding] = value
        return Exits((UNIT_T, local), state=local)
    return continue_exits(exits, follow)


def exit_type(exits):
    return join(exits.returned, exits.normal[0] if exits.normal is not None else NEVER)


def source_exits(compiler, node, local, names, readonly, final):
    outer, compiler.returns = compiler.returns, []
    try:
        value = compiler.visit(node, local, names, readonly, final)
        returned = NEVER
        for item in compiler.returns:
            returned = join(returned, item)
        return Exits(None if value == NEVER else (value, local.copy()), returned, local.copy())
    finally:
        compiler.returns = outer


def export_source(compiler, exits, env):
    if exits.returned != NEVER:
        compiler.returns.append(exits.returned)
    if exits.normal is None:
        return NEVER
    value, bindings = exits.normal
    env.clear()
    env.update(bindings)
    return value


def fallback_exits(compiler, env, left, right, mutated):
    first = guarded(compiler, lambda: left(env.copy()), catches=True)
    # A fault may happen after any partial assignment in the left operand.
    recovery = env.copy()
    recovery.update(dict.fromkeys(set(mutated) & env.keys(), UNKNOWN))
    second = guarded(compiler, lambda: right(recovery))
    return join_exits(first, second)


def source_fallback(compiler, node, env, names, readonly, final):
    from ibl_v2_analysis import assigned_names
    d = node.data
    exits = fallback_exits(compiler, env,
        lambda local: source_exits(compiler, d['left'], local, names, readonly, final),
        lambda local: source_exits(compiler, d['right'], local, names, readonly, final),
        assigned_names(d['left']))
    return export_source(compiler, exits, env)
