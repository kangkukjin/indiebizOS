"""Effect dependencies and result-only computation in a repair lineage.

This is a source-coordinate projection of an already checked execution plan, not
another type/effect checker or an evaluator. Values carry dependency sets; only
external effects demand those sets. Calls substitute arguments (including lexical
callbacks), so a returned computation is fixed only when an effect depends on it.
Unknown control/targets retain their whole implementation conservatively.
"""
from dataclasses import dataclass, field

from ibl_v2_ir import Node, Fault, digest, record_fields, parallel_branches
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


@dataclass
class Value:
    deps: set = field(default_factory=set)
    target: object = None
    fields: dict | None = None
    members: list | None = None
    evaluation: set | None = None

    @property
    def evaluated(self):
        return self.deps if self.evaluation is None else self.evaluation

    def with_deps(self, deps):
        return Value(self.deps | deps, self.target, self.fields, self.members,
                     None if self.evaluation is None else self.evaluation | deps)


@dataclass
class Flow:
    value: Value = field(default_factory=Value)
    returns: list = field(default_factory=list)
    continues: bool = True


class Projection:
    def __init__(self, plan):
        from ibl_v2_repair import node_paths
        self.plan = plan
        self.root = parse(plan.source)
        self.nodes, self.paths = {}, {}
        self.resolved = {n.id: n for n in walk([plan.root, plan.functions])}
        self.definitions = {n.id: n for n in walk(self.root) if n.kind == 'def'}
        self.effects, self.retained, self.active = {}, set(), set()
        self.emissions, self.exits = [], []
        self.iterations, self.iteration_effects = [], set()
        self.remaining = 8192
        # Definitions have their own stable address; body edits never shift a
        # caller's executable index. Nested nodes retain their structural paths.
        executable = 0
        for n in self.root.data['statements']:
            key = ('definition', n.data['name']) if n.kind == 'def' else ('program', executable)
            if n.kind != 'def':
                executable += 1
            for path, nid in node_paths(n, key):
                self.paths[nid] = path
            self.nodes.update({v.id: v for v in walk(n)})

    def atom(self, node):
        return {node.id} if node is not None else set()

    def full(self, node, seen=None):
        """Opaque boundaries retain transitive definitions and callback bodies."""
        seen = set() if seen is None else seen
        result = set()
        for n in walk(node):
            self.remaining -= 1
            if self.remaining < 0:
                raise ValueError('repair dependency budget exceeded')
            result.add(n.id)
            resolved = self.resolved.get(n.id, n)
            symbol = resolved.data.get('symbol')
            targets = [symbol] if symbol in self.definitions else []
            # Builtins have a fixed target. Their argument/callback nodes are
            # still walked below, including any dynamic calls they contain.
            # Treating len/max inside an opaque record or callback as an unknown
            # user function would freeze every unrelated result computation.
            if (n.kind in ('named_call', 'pure_call')
                    and n.data['fn'].kind != 'builtin'):
                targets = list(self.definitions)
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    result |= self.full(self.definitions[target], seen)
        return result

    def complete(self, value, seen=None):
        seen = set() if seen is None else seen
        if id(value) in seen:
            return set()
        seen.add(id(value))
        self.remaining -= 1
        if self.remaining < 0:
            raise ValueError('repair dependency budget exceeded')
        deps = set(value.deps)
        if value.target and isinstance(value.target, tuple):
            node, env = value.target
            deps |= self.full(node)
            for captured in env.values():
                deps |= self.complete(captured, seen)
        for child in (value.fields or {}).values():
            deps |= self.complete(child, seen)
        for child in value.members or []:
            deps |= self.complete(child, seen)
        return deps

    def opaque(self, node, env, control):
        deps = self.boundary(node, env)
        if self.plan.node_effects.get(node.id, {'unknown'}) - {'pure'}:
            self.sink(node, deps | control)
        return Value(deps)

    def boundary(self, node, env):
        """All possible failure causes, including captured callable bodies."""
        deps = self.full(node)
        for n in walk(node):
            if n.kind == 'ref' and n.data['name'] in env:
                deps |= self.complete(env[n.data['name']])
        return deps

    def sink(self, node, deps):
        self.emissions.append(node.id)
        self.iteration_effects.update((loop, node.id) for loop in self.iterations)
        self.effects.setdefault(node.id, set()).update(deps | self.atom(node))
        self.retained.update(deps | self.atom(node))

    def expr(self, node, env, control=frozenset(), piped=None):
        if node is None:
            return Value()
        self.remaining -= 1
        if self.remaining < 0:
            raise ValueError('repair dependency budget exceeded')
        d, kind, own = node.data, node.kind, self.atom(node)
        if kind in ('sequence', 'if', 'case', 'try', 'repeat', 'fallback', 'bind', 'return'):
            outcome = self.flow(node, env, control)
            return self.merge([*outcome.returns, *([outcome.value] if outcome.continues else [])])
        if kind == 'ref':
            held = env.get(d['name'], Value())
            # Reading a carried value does not execute its producer again.
            return Value(held.deps | own, held.target, held.fields, held.members, own)
        if kind in ('literal', 'builtin'):
            return Value(own)
        if kind == 'lambda':
            return Value(own, (node, env.copy()))
        if kind == 'callable_ref':
            resolved = self.resolved.get(node.id, node)
            definition = self.definitions.get(resolved.data.get('symbol'))
            return Value(own, (definition, {}) if definition else d['node'] + ':' + d['action'])
        if kind == 'record' and not any(k is None for k, _ in d.get('entries', [])):
            fields, prior = {}, set()
            for key, child in record_fields(node).items():
                fields[key] = self.expr(child, env, control | prior)
                prior |= fields[key].evaluated
            return Value(own | set().union(*(v.deps for v in fields.values())), fields=fields, evaluation=own | prior)
        if kind == 'list':
            members, prior = [], set()
            for child in d['values']:
                value = self.expr(child, env, control | prior)
                members.append(value)
                prior |= value.evaluated
            return Value(own | set().union(*(v.deps for v in members)), members=members, evaluation=own | prior)
        if kind in ('field', 'index'):
            base = self.expr(d['base'], env, control)
            key = d['key']
            selector = self.expr(key, env, control | base.deps) if isinstance(key, Node) else Value()
            literal = key.data['value'] if isinstance(key, Node) and key.kind == 'literal' else key
            selected = (base.fields or {}).get(literal) if isinstance(literal, str) else None
            # Keep evaluation dependencies too: projecting one field still
            # evaluates the full record and its failure conditions first.
            if selected is None:
                # Losing the selected target must not lose callable bodies held
                # by the container. Unknown selection is an opaque dependency.
                return Value(own | self.complete(base) | selector.deps)
            return selected.with_deps(own | base.deps | selector.deps)
        if kind == 'pipe':
            left = self.expr(d['left'], env, control)
            return self.expr(d['right'], env, control | left.deps, left).with_deps(own)
        if kind == 'parallel':
            exit_scope = len(self.exits)
            values = [self.expr(branch, env.copy(), control | own) for branch in parallel_branches(node)]
            del self.exits[exit_scope:]
            return Value(own | set().union(*(v.deps for v in values)), members=values)
        if kind == 'call' and (d['node'], d['action']) == ('table', 'each'):
            args = self.expr(d['params'], env, control)
            items = (args.fields or {}).get('items', piped)
            if items is None:
                return self.opaque(node, env, control)
            local = {**env, 'it': Value(self.complete(items)), 'i': Value(items.deps)}
            self.iterations.append(node.id)
            exit_scope = len(self.exits)
            try:
                result = self.expr(d['body'], local, control | own | args.deps | items.deps)
            finally:
                del self.exits[exit_scope:]
                self.iterations.pop()
            # Completion between rounds/batches is enforced by execution, not
            # equality of result-only code. Selection and inputs remain fixed.
            return Value(own | args.deps | items.deps | self.complete(result))
        if kind in ('call', 'named_call', 'pure_call'):
            return self.apply(node, env, control, piped)
        if kind in ('binary', 'unary', 'format', 'conditional', 'slice'):
            # Pure expression semantics are checked by the compiler. All inputs
            # remain dependencies; no constant folding or business evaluation.
            values, prior = [], set()
            for child in self.children(d):
                value = self.expr(child, env, control | prior)
                values.append(value)
                prior |= value.evaluated
            return Value(own | set().union(*(self.complete(v) for v in values)))
        return self.opaque(node, env, control)

    def merge(self, values):
        if not values:
            return Value()
        if all(value is values[0] for value in values):
            return values[0]
        # A join with no unique callable target is opaque, but the possible
        # implementations remain dependencies when its value is consumed.
        return Value(set().union(*(self.complete(value) for value in values)))

    def flow(self, node, env, control, piped=None):
        """Join continuing paths once; returned paths cannot gate later effects.

        Conditions and evaluation completion belong to each path. We do not
        evaluate a condition or infer that an observed branch is the only one.
        The suffix is analyzed once after joining continuing bindings, avoiding
        exponential duplication across consecutive independent conditionals.
        """
        if node is None:
            return Flow()
        self.remaining -= 1
        if self.remaining < 0:
            raise ValueError('repair dependency budget exceeded')
        d, own = node.data, self.atom(node)
        if node.kind == 'sequence':
            prior, result, returned = set(), Value(), []
            for statement in d['statements']:
                if statement.kind == 'def':
                    continue
                outcome = self.flow(statement, env, control | prior)
                returned.extend(value.with_deps(prior) for value in outcome.returns)
                if not outcome.continues:
                    return Flow(returns=returned, continues=False)
                result = outcome.value.with_deps(prior)
                prior |= outcome.value.evaluated
            return Flow(result, returned)
        if node.kind in ('bind', 'return'):
            if node.kind == 'return':
                self.exits.append(own | control)
            outcome = self.flow(d['value'], env, control | own)
            if outcome.continues:
                value = outcome.value.with_deps(own)
                if node.kind == 'return':
                    outcome.returns.append(value)
                    outcome.continues = False
                else:
                    env[d['name']] = value
                    outcome.value = Value(value.deps, evaluation=value.evaluated)
            return outcome
        if node.kind == 'pipe':
            outcome = self.flow(d['left'], env, control | own)
            if outcome.continues:
                following = self.flow(d['right'], env, control | own | outcome.value.evaluated,
                                      outcome.value)
                outcome.returns.extend(following.returns)
                outcome.continues = following.continues
                outcome.value = following.value.with_deps(own)
            return outcome
        if node.kind == 'named_call':
            from ibl_v2_exits import value_control
            if value_control(d['fn']):
                outcome = self.flow(d['fn'], env, control | own)
                if outcome.continues:
                    outcome.value = self.apply(node, env, control | own, piped, target=outcome.value)
                return outcome
        if node.kind == 'fallback':
            from ibl_v2_analysis import assigned_names
            left_env = env.copy()
            left = self.flow(d['left'], left_env, control | own)
            failure = self.flow_dependencies(left)
            right_env = env.copy()
            for name in assigned_names(d['left']) & env.keys():
                right_env[name] = Value(failure | self.complete(env[name]))
            right = self.flow(d['right'], right_env, control | own | failure)
            right.value = right.value.with_deps(failure)
            right.returns = [v.with_deps(failure) for v in right.returns]
            return self.join_flows([(left, left_env), (right, right_env)], env, own)
        if node.kind == 'repeat':
            return self.repeat(node, env, control)
        if node.kind == 'try':
            from ibl_v2_analysis import assigned_names
            body_env = env.copy()
            body = self.flow(d['body'], body_env, control | own)
            failure = self.flow_dependencies(body)
            branches = [(body, body_env)]
            if d['catch'] is not None:
                caught_env = env.copy()
                for name in assigned_names(d['body']) & env.keys():
                    caught_env[name] = Value(failure | self.complete(env[name]))
                caught_env['error'] = Value(failure)
                caught = self.flow(d['catch'], caught_env, control | own | failure)
                caught.value = caught.value.with_deps(failure)
                caught.returns = [v.with_deps(failure) for v in caught.returns]
                if 'error' in env:
                    caught_env['error'] = env['error']
                else:
                    caught_env.pop('error', None)
                branches.append((caught, caught_env))
            result = self.join_flows(branches, env, own)
            if d['final'] is not None:
                # Cleanup runs on returns and faults alike: the body's result
                # does not select it. Reads of partially assigned bindings do
                # depend on all possible body/catch completion paths.
                cleanup_deps = set().union(*(self.flow_dependencies(flow) for flow, _ in branches))
                cleanup_env = env.copy()
                for name in assigned_names(d['body']) | assigned_names(d['catch']):
                    cleanup_env[name] = Value(cleanup_deps | self.complete(env.get(name, Value())))
                cleanup = self.flow(d['final'], cleanup_env, control | own)
                for name in assigned_names(d['final']):
                    if name in cleanup_env:
                        env[name] = cleanup_env[name]
                result.value = result.value.with_deps(cleanup.value.deps)
                result.returns = [v.with_deps(cleanup.value.deps) for v in result.returns]
            return result
        if node.kind == 'case':
            selector = self.expr(d['value'], env, control | own)
            guard = own | self.complete(selector)
            branches = []
            for expected, body in [*d['branches'], (None, d['otherwise'])]:
                if expected is not None:
                    guard |= self.complete(self.expr(expected, env, control | guard))
                local = env.copy()
                flow = self.flow(body, local, control | guard)
                flow.value = flow.value.with_deps(guard)
                flow.returns = [value.with_deps(guard) for value in flow.returns]
                local = {name: value.with_deps(guard) for name, value in local.items()}
                branches.append((flow, local))
            return self.join_flows(branches, env, own)
        if node.kind == 'if':
            condition = self.expr(d['value'], env, control | own)
            guard = own | condition.deps
            branches = []
            for body in (d['body'], d['otherwise']):
                local = env.copy()
                branches.append((self.flow(body, local, control | guard), local))
            return self.join_flows(branches, env, guard)
        return Flow(self.expr(node, env, control, piped))

    def repeat(self, node, env, control):
        from ibl_v2_analysis import assigned_names
        d, own = node.data, self.atom(node)
        initial = env.copy()
        mutated = assigned_names(d['body']) - {'i'}
        state = {**env, 'i': Value(own)}
        guard = set(own)
        if d['mode'] == 'count':
            guard |= self.complete(self.expr(d['value'], env, control | own))
        before, exits_before = len(self.emissions), len(self.exits)
        self.iterations.append(node.id)
        try:
            while True:
                local = state.copy()
                if d['mode'] == 'while':
                    guard |= self.complete(self.expr(d['value'], local, control | guard))
                body = self.flow(d['body'], local, control | guard)
                if d['mode'] == 'until' and body.continues:
                    guard |= self.complete(self.expr(d['value'], local, control | guard))
                candidate = state.copy()
                for name in mutated & initial.keys():
                    candidate[name] = self.merge([state[name], local.get(name, state[name])])
                stable = all(self.complete(candidate[k]) == self.complete(state[k]) for k in state)
                state = candidate
                if stable or not body.continues:
                    break
            # Early return selection also determines which later rounds exist.
            # Return values themselves remain result computations.
            guard |= set().union(*self.exits[exits_before:])
            for key in set(self.emissions[before:]):
                self.sink(self.nodes[key], control | guard)
        finally:
            self.iterations.pop()
        count = d['value'].data.get('value') if d['mode'] == 'count' and d['value'].kind == 'literal' else None
        guaranteed = d['mode'] == 'until' or type(count) is int and count > 0
        for name in mutated:
            if name in local and (guaranteed or name in initial):
                env[name] = (local[name] if guaranteed else self.merge([initial[name], local[name]])).with_deps(guard)
        # Later caller effects still depend on completion of the whole loop.
        result = Value(self.flow_dependencies(body) | guard)
        return Flow(result, body.returns, body.continues or not guaranteed)

    def join_flows(self, branches, env, guard):
        continuing = [(flow, local) for flow, local in branches if flow.continues]
        returned = [value.with_deps(guard) for flow, _ in branches for value in flow.returns]
        if not continuing:
            return Flow(returns=returned, continues=False)
        names = set.intersection(*(set(local) for _, local in continuing))
        merged = {name: self.merge([local[name] for _, local in continuing]).with_deps(guard) for name in names}
        env.clear()
        env.update(merged)
        result = self.merge([flow.value for flow, _ in continuing]).with_deps(guard)
        return Flow(result, returned)

    def flow_dependencies(self, flow):
        return self.complete(self.merge([*flow.returns, *([flow.value] if flow.continues else [])]))

    @staticmethod
    def children(data):
        if isinstance(data, Node):
            yield data
        elif isinstance(data, dict):
            for value in data.values():
                yield from Projection.children(value)
        elif isinstance(data, (list, tuple)):
            for value in data:
                yield from Projection.children(value)

    def apply(self, node, env, control, piped, target=None):
        d, own = node.data, self.atom(node)
        if target is not None:
            pass
        elif node.kind == 'call':
            definition = self.definitions.get(self.resolved.get(node.id, node).data.get('symbol'))
            target = Value(own, (definition, {}) if definition else d['node'] + ':' + d['action'])
        else:
            target = self.expr(d['fn'], env, control)
        if node.kind == 'pure_call':
            values, prior = [], set()
            for child in d['args']:
                value = self.expr(child, env, control | target.deps | prior)
                values.append(value)
                prior |= value.evaluated
            if piped is not None:
                values.insert(0, piped)
            args = Value(set().union(*(v.deps for v in values)), members=values)
        else:
            args = self.expr(d['params'], env, control | target.deps)
        entry = own | target.deps | args.deps
        if isinstance(target.target, tuple):
            definition, captured = target.target
            if definition.id in self.active:
                return self.opaque(node, env, control)
            params = definition.data['params']
            local = captured.copy()
            if args.fields is not None:
                local.update(args.fields)
                if piped is not None and params:
                    local[next(iter(params))] = piped
            elif args.members is not None:
                local.update(zip(params, args.members))
            else:
                return self.opaque(node, env, control)
            if definition.kind == 'def':
                for key, default in params.items():
                    if key not in local:
                        local[key] = self.expr(default, {}, control)
                        entry |= local[key].deps
                if definition.data.get('contract') is not None or definition.data.get('annotations'):
                    return self.opaque(node, env, control)
            entry |= self.atom(definition)
            self.active.add(definition.id)
            exit_scope = len(self.exits)
            try:
                value = self.expr(definition.data['body'], local, control | entry)
            finally:
                del self.exits[exit_scope:]
                self.active.remove(definition.id)
            return value.with_deps(entry)
        # Primitive and unresolved calls consume their whole argument values.
        # Passing a callable to an opaque provider never certifies it as inert.
        deps = entry | self.complete(target)
        if piped is not None:
            deps |= self.complete(piped)
        for value in (args.fields or {}).values():
            deps |= self.complete(value)
        for value in args.members or []:
            deps |= self.complete(value)
        if self.plan.node_effects.get(node.id, {'unknown'}) - {'pure'}:
            self.sink(node, control | deps)
        return Value(deps)

    def signature(self, node):
        from ibl_v2_repair import structural
        def shape(value):
            if isinstance(value, Node):
                return '<node>'
            if isinstance(value, dict):
                return {key: shape(child) for key, child in value.items()}
            if isinstance(value, (tuple, list)):
                return [shape(child) for child in value]
            return structural(value)
        # Statement count and body implementation are represented by demanded
        # child coordinates, not by the enclosing frame's complete source.
        data = {} if node.kind == 'sequence' else node.data
        return [node.kind, shape(data)]


def frontier(plan):
    from ibl_v2_repair import structural
    projection = Projection(plan)
    try:
        projection.expr(projection.root, {})
        supported = True
    except (ValueError, RecursionError):
        supported = False
    address = lambda nid: repr(projection.paths[nid])
    return {'protocol': 'ibl-repair-frontier/7', 'supported': supported,
            'retained': {address(nid): projection.signature(projection.nodes[nid])
                         for nid in projection.retained},
            'iteration_effects': sorted([address(loop), address(call)] for loop, call in projection.iteration_effects),
            'effects': sorted(address(nid) for nid in projection.effects),
            'nodes': {address(nid): nid for nid in projection.paths},
            'completion': {address(nid): digest(structural(n.data.get('contract')))
                           for nid, n in projection.definitions.items() if n.data.get('contract') is not None}}


def mapping(before, after):
    if (not before or not after or before.get('protocol') != 'ibl-repair-frontier/7'
            or after.get('protocol') != before.get('protocol')
            or not before.get('supported') or not after.get('supported')
            or before['retained'] != after['retained'] or before['effects'] != after['effects']
            or before.get('iteration_effects') != after.get('iteration_effects')
            or before['completion'] != after['completion']):
        raise Fault('REPAIR_UNSUPPORTED', '효과의 입력·계산·조건·호출 좌표·완료 의무를 보존하는 수정만 계승합니다.', kind='protocol')
    return {nid: before['nodes'][path] for path, nid in after['nodes'].items() if path in before['nodes']}
