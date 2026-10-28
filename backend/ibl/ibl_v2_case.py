"""Ordered first-match transfer shared by source and stored case relations.

Selectors and comparisons are pure but can fail. Only the unmatched path
reaches the next comparison; normal exits and nonlocal returns stay separate.
No provider or business callback executes during this abstract transfer.
"""
from ibl_v2_types import NEVER
from ibl_v2_ir import pack
from ibl_v2_narrow import predicate, known_predicate, branch_environment, narrow_predicate
from ibl_v2_recovery import Exits, join_exits
from ibl_v2_exits import source_exits, export_source


def equality_paths(env, selector, expected, left, right):
    guard = {'kind': 'binary', 'op': '==', 'left': left, 'right': right}
    known = known_predicate(guard, env)
    if known is None:
        # The selector is a snapshot, not a second application of its producer.
        snapshot = {**env, '@case': selector, '@when': expected}
        known = known_predicate({'kind': 'binary', 'op': '==',
            'left': {'kind': 'path', 'keys': ['@case']},
            'right': {'kind': 'path', 'keys': ['@when']}}, snapshot)
    if expected.kind in ('Null', 'Bool', 'Text') and (expected.kind == 'Null' or expected.literal is not None):
        guard['right'] = {'kind': 'literal', 'wire': pack(expected.literal)}
    paths = []
    for truth in (True, False):
        local, possible = branch_environment(env, guard, truth)
        if selector.kind == 'Bool' and expected.kind == 'Bool' and expected.literal is not None:
            local = narrow_predicate(local, left, truth == expected.literal)
        possible = (possible and (known is None or known == truth)
                    and selector != NEVER and expected != NEVER
                    and not any(v == NEVER for v in local.values()))
        paths.append((local, possible))
    return paths


def case_exits(compiler, env, selector, guard, comparisons, evaluate, branch):
    """Callbacks receive reachability; source still diagnoses dead syntax."""
    remaining, possible, result = env.copy(), selector != NEVER, NEVER
    compiler.requirement_depth += 1
    try:
        for index, expected_guard in enumerate(comparisons):
            expected = evaluate(index, remaining.copy(), possible)
            yes, no = equality_paths(remaining, selector, expected, guard, expected_guard)
            selected = branch(index, yes[0], possible and yes[1])
            if possible and yes[1]:
                result = join_exits(result, selected)
            remaining, possible = no[0], possible and no[1]
        otherwise = branch(len(comparisons), remaining, possible)
        if possible:
            result = join_exits(result, otherwise)
    finally:
        compiler.requirement_depth -= 1
    return Exits() if result == NEVER else result


def source_case(compiler, node, env, names, readonly, final):
    d = node.data
    compiler.pure(d['value'])
    selector = compiler.visit(d['value'], env, names, readonly, final)
    paths = []
    bodies = [body for _, body in d['branches']] + [d['otherwise']]

    def evaluate(index, local, possible):
        return compiler.visit_branch(d['branches'][index][0], local, names, readonly, final, possible, pure=True)

    def branch(index, local, possible):
        body = bodies[index]
        if possible:
            result = source_exits(compiler, body, local, names, readonly, final)
        else:
            compiler.visit_branch(body, local, names, readonly, final, False)
            result = Exits()
        paths.append((body, local))
        return result

    exits = case_exits(compiler, env, selector, predicate(d['value']),
                       [predicate(test) for test, _ in d['branches']], evaluate, branch)
    lexical = env.copy()
    compiler.merge_continuations(lexical, paths)
    result = export_source(compiler, exits, env)
    # Actual input refinement does not relax lexical definite assignment.
    if exits.normal is not None:
        for name in set(env) - lexical.keys():
            del env[name]
    return result


def relation_case(compiler, term, env, selector, site, apply):
    return case_exits(compiler, env, selector, term['guard'],
        [part['guard'] for part in term['branches']],
        lambda index, local, possible: apply(compiler, term['branches'][index]['expected'], local, site) if possible else NEVER,
        lambda index, local, possible: apply(compiler,
            term['branches'][index]['body'] if index < len(term['branches']) else term['otherwise'],
            local, site) if possible else Exits())
