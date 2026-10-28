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

    def with_deps(self, deps):
        return Value(self.deps | deps, self.target, self.fields, self.members)


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
        self.emissions = []
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
            if n.kind in ('named_call', 'pure_call'):
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
        deps = self.full(node)
        for n in walk(node):
            if n.kind == 'ref' and n.data['name'] in env:
                deps |= self.complete(env[n.data['name']])
        if self.plan.node_effects.get(node.id, {'unknown'}) - {'pure'}:
            self.sink(node, deps | control)
        return Value(deps)

    def sink(self, node, deps):
        self.emissions.append(node.id)
        self.effects.setdefault(node.id, set()).update(deps | self.atom(node))
        self.retained.update(deps | self.atom(node))

    def expr(self, node, env, control=frozenset(), piped=None):
        if node is None:
            return Value()
        self.remaining -= 1
        if self.remaining < 0:
            raise ValueError('repair dependency budget exceeded')
        d, kind, own = node.data, node.kind, self.atom(node)
        if kind == 'sequence':
            flow = self.flow(node, env, control)
            return self.merge([*flow.returns, *([flow.value] if flow.continues else [])])
        if kind in ('bind', 'return'):
            value = self.expr(d['value'], env, control | own).with_deps(own)
            if kind == 'bind':
                env[d['name']] = value
            return value
        if kind == 'ref':
            return env.get(d['name'], Value()).with_deps(own)
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
                prior |= fields[key].deps
            return Value(own | prior, fields=fields)
        if kind == 'list':
            members, prior = [], set()
            for child in d['values']:
                value = self.expr(child, env, control | prior)
                members.append(value)
                prior |= value.deps
            return Value(own | prior, members=members)
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
            values = [self.expr(branch, env.copy(), control | own) for branch in parallel_branches(node)]
            return Value(own | set().union(*(v.deps for v in values)), members=values)
        if kind == 'call' and (d['node'], d['action']) == ('table', 'each'):
            args = self.expr(d['params'], env, control)
            items = (args.fields or {}).get('items', piped)
            if items is None:
                return self.opaque(node, env, control)
            local = {**env, 'it': Value(self.complete(items)), 'i': Value(items.deps)}
            before = len(self.emissions)
            result = self.expr(d['body'], local, control | own | args.deps | items.deps)
            fields = record_fields(d['params'])
            parallel = fields.get('parallel')
            concurrency = parallel.data['value'] if parallel and parallel.kind == 'literal' else 1
            # A later batch/iteration may depend on completion of the previous
            # one. Only a statically bounded single fanout can separate its tails.
            if not (items.members is not None and len(items.members) <= concurrency):
                for key in set(self.emissions[before:]):
                    self.sink(self.nodes[key], result.deps)
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
                prior |= self.complete(value)
            return Value(own | prior)
        return self.opaque(node, env, control)

    def merge(self, values):
        if not values:
            return Value()
        if all(value is values[0] for value in values):
            return values[0]
        # A join with no unique callable target is opaque, but the possible
        # implementations remain dependencies when its value is consumed.
        return Value(set().union(*(self.complete(value) for value in values)))

    def flow(self, node, env, control):
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
                prior |= outcome.value.deps
            return Flow(result, returned)
        if node.kind == 'return':
            value = self.expr(d['value'], env, control | own).with_deps(own)
            return Flow(returns=[value], continues=False)
        if node.kind == 'if':
            condition = self.expr(d['value'], env, control | own)
            guard = own | condition.deps
            branches = []
            for body in (d['body'], d['otherwise']):
                local = env.copy()
                branches.append((self.flow(body, local, control | guard), local))
            continuing = [(flow, local) for flow, local in branches if flow.continues]
            returned = [value.with_deps(guard) for flow, _ in branches for value in flow.returns]
            if not continuing:
                return Flow(returns=returned, continues=False)
            names = set.intersection(*(set(local) for _, local in continuing))
            merged = {name: self.merge([local[name] for _, local in continuing])
                      for name in names}
            env.clear()
            env.update(merged)
            result = self.merge([flow.value for flow, _ in continuing]).with_deps(guard)
            return Flow(result, returned)
        return Flow(self.expr(node, env, control))

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

    def apply(self, node, env, control, piped):
        d, own = node.data, self.atom(node)
        if node.kind == 'call':
            definition = self.definitions.get(self.resolved.get(node.id, node).data.get('symbol'))
            target = Value(own, (definition, {}) if definition else d['node'] + ':' + d['action'])
        else:
            target = self.expr(d['fn'], env, control)
        if node.kind == 'pure_call':
            values, prior = [], set()
            for child in d['args']:
                value = self.expr(child, env, control | target.deps | prior)
                values.append(value)
                prior |= value.deps
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
            try:
                value = self.expr(definition.data['body'], local, control | entry)
            finally:
                self.active.remove(definition.id)
            return value.with_deps(entry)
        # Primitive and unresolved calls consume their whole argument values.
        # Passing a callable to an opaque provider never certifies it as inert.
        deps = entry | self.complete(target)
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
    return {'protocol': 'ibl-repair-frontier/3', 'supported': supported,
            'retained': {address(nid): projection.signature(projection.nodes[nid])
                         for nid in projection.retained},
            'effects': sorted(address(nid) for nid in projection.effects),
            'nodes': {address(nid): nid for nid in projection.paths},
            'completion': {address(nid): digest(structural(n.data.get('contract')))
                           for nid, n in projection.definitions.items() if n.data.get('contract') is not None}}


def mapping(before, after):
    if (not before or not after or before.get('protocol') != 'ibl-repair-frontier/3'
            or after.get('protocol') != before.get('protocol')
            or not before.get('supported') or not after.get('supported')
            or before['retained'] != after['retained'] or before['effects'] != after['effects']
            or before['completion'] != after['completion']):
        raise Fault('REPAIR_UNSUPPORTED', '효과의 입력·계산·조건·호출 좌표·완료 의무를 보존하는 수정만 계승합니다.', kind='protocol')
    return {nid: before['nodes'][path] for path, nid in after['nodes'].items() if path in before['nodes']}
