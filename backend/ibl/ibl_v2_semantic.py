"""Finite, parameterized relations for separately checked IBL abilities.

These are type/effect transfer equations, not invocation observations or source
ASTs. Bindings disappear; unused pure values disappear; calls remain effect
roots. Application never evaluates a business value or an implementation body.
Unsupported control flow stays on the explicitly reported source-check boundary.
"""
from pathlib import Path

from ibl_v2_ir import Node, digest, record_fields, parallel_branches, pack, unpack
from ibl_v2_types import (Type, UNKNOWN, UNIT_T, BOOL, NUMBER, TEXT, NULL,
                          infer, ordered_list, concat_lists, describe_type, alternatives, join, NEVER)

PROTOCOL = 'ibl-semantic/1'


def edition():
    root = Path(__file__).parent
    return digest({name: (root / name).read_text() for name in (
        'ibl_v2_semantic.py', 'ibl_v2_semantic_store.py', 'ibl_v2_types.py',
        'ibl_v2_analysis.py', 'ibl_v2_call_analysis.py', 'ibl_v2_adapters.py',
        'ibl_v2_requirements.py', 'ibl_v2_narrow.py', 'ibl_v2_exits.py', 'ibl_v2_recovery.py', 'ibl_v2_repeat.py', 'ibl_v2_compile.py')})


class Unsupported(ValueError):
    pass


def lexical_inputs(node, bound=frozenset()):
    """Free inputs of a continuation; local assignments are not captures."""
    def scan(value, names):
        names = set(names)
        if value is None:
            return set(), names, False
        if not isinstance(value, Node):
            children = value.values() if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else ()
            needed = set()
            for child in children:
                needed.update(scan(child, names)[0])
            return needed, names, False
        d = value.data
        if value.kind == 'ref':
            return {d['name']} - names, names, False
        if value.kind == 'lambda':
            return scan(d['body'], names | set(d['params']))[0], names, False
        if value.kind == 'sequence':
            needed = set()
            for statement in d['statements']:
                free, names, stopped = scan(statement, names)
                needed.update(free)
                if stopped:
                    return needed, names, True
            return needed, names, False
        if value.kind == 'bind':
            free, after, stopped = scan(d['value'], names)
            return free, after | {d['name']}, stopped
        if value.kind == 'return':
            return scan(d['value'], names)[0], names, True
        if value.kind == 'if':
            yes, no = scan(d['body'], names), scan(d['otherwise'], names)
            continuing = [v[1] for v in (yes, no) if not v[2]]
            merged = set.intersection(*continuing) if continuing else names
            return scan(d['value'], names)[0] | yes[0] | no[0], merged, not continuing
        if value.kind == 'pipe':
            left = scan(d['left'], names)
            right = scan(d['right'], left[1])
            return left[0] | (right[0] if not left[2] else set()), right[1], left[2] or right[2]
        if value.kind == 'fallback':
            left, right = scan(d['left'], names), scan(d['right'], names)
            continuing = [v[1] for v in (left, right) if not v[2]]
            merged = set.intersection(*continuing) if continuing else names
            return left[0] | right[0], merged, not continuing
        if value.kind == 'repeat':
            body = scan(d['body'], names | {'i'})
            scope = body[1] if d['mode'] == 'until' else names | ({'i'} if d['mode'] == 'while' else set())
            count = d['value'].data.get('value') if d['value'].kind == 'literal' and d['mode'] == 'count' else None
            guaranteed = d['mode'] == 'until' or type(count) is int and count > 0
            after = ((body[1] - {'i'}) | (names & {'i'})) if guaranteed else names
            return body[0] | scan(d['value'], scope)[0], after, guaranteed and body[2]
        if value.kind == 'try':
            body = scan(d['body'], names)
            caught = scan(d['catch'], names | {'error'})
            catch_names = (caught[1] - {'error'}) | (names & {'error'})
            paths = [body] + ([(caught[0], catch_names, caught[2])] if d['catch'] else [])
            continuing = [path[1] for path in paths if not path[2]]
            merged = set.intersection(*continuing) if continuing else names
            # Cleanup runs on returned paths as well. Source validation owns
            # definite assignment on partial failure; these are lexical names.
            cleanup_scope = set.intersection(*(path[1] for path in paths))
            cleanup = scan(d['final'], cleanup_scope)
            needed = body[0] | (caught[0] if d['catch'] else set()) | cleanup[0]
            return needed, merged | (cleanup[1] - cleanup_scope), not continuing
        if value.kind == 'call' and (d['node'], d['action']) == ('table', 'each'):
            needed = scan(d['params'], names)[0] | scan(d['body'], names | {'it', 'i'})[0]
            return needed, names, False
        return scan(d, names)[0], names, False
    return scan(node, bound)[0]


class Derivation:
    def __init__(self, budget=None, pure=False, exits=False):
        self.budget = budget if budget is not None else [4096]
        self.pure = pure
        self.exits = exits
        self.terms, self.index, self.effects, self.checks = [], {}, [], []
        self.actions, self.functions = set(), set()

    def term(self, op, **fields):
        value = {'op': op, **fields}
        key = digest(value)
        if key not in self.index:
            self.budget[0] -= 1
            if self.budget[0] < 0:
                raise Unsupported('finite relation budget exceeded')
            self.index[key] = len(self.terms)
            self.terms.append(value)
        return self.index[key]

    def checked(self, op, **fields):
        result = self.term(op, **fields)
        self.checks.append(result)
        return result

    def ability(self, params, body, defaults=None, completion=None):
        env = {k: self.term('input', name=k) for k in params}
        from ibl_v2_exits import value_control
        if body.kind == 'sequence':
            result = self.sequence(body, env)
        elif self.exits:
            result = self.outcome(body, env)
        elif value_control(body):
            result = self.term('frame_value', outcome=self.outcome(body, env))
        else:
            result = self.expr(body, env)
        return self.interface(params, result, defaults, completion)

    def interface(self, params, result, defaults=None, completion=None):
        return {'protocol': PROTOCOL, 'params': list(params), 'defaults': defaults or {},
                'terms': self.terms, 'result': result, 'effects': self.effects, 'checks': self.checks,
                'actions': sorted(self.actions), 'functions': sorted(self.functions),
                'completion': completion or [],
                'failure': 'catchable-Fault-only; cleanup-before-exit; collect-is-Result',
                'lifetime': 'preserve-input-and-call-result-owners',
                'evidence': 'derived; runtime-receipts-required'}

    def sequence(self, body, env):
        result = self.term('unit')
        from ibl_v2_exits import value_control
        for index, statement in enumerate(body.data['statements']):
            if value_control(statement):
                outcome = self.outcome(statement, env)
                tail = Node('sequence', statement.end, body.end,
                            {'statements': body.data['statements'][index + 1:]})
                inner = Derivation(self.budget, pure=self.pure, exits=True)
                continuation = inner.ability(sorted(lexical_inputs(tail)), tail)
                self.actions.update(inner.actions)
                self.functions.update(inner.functions)
                result = self.term('continue', outcome=outcome, continuation=continuation,
                                   empty=not tail.data['statements'], exits=self.exits)
                self.effects.append(result)
                return result
            if statement.kind == 'bind':
                env[statement.data['name']] = self.expr(statement.data['value'], env)
                result = self.term('unit')
            elif statement.kind == 'return':
                value = self.expr(statement.data['value'], env)
                return self.finish(value, env, returned=True)
            else:
                result = self.expr(statement, env)
        return self.finish(result, env)

    def finish(self, result, env, returned=False):
        if not self.exits:
            return result
        return self.term('exit', value=result, bindings=dict(env), returned=returned)

    def outcome(self, node, env, piped=None):
        previous, self.exits = self.exits, True
        try:
            return self._outcome(node, env, piped)
        finally:
            self.exits = previous

    def _outcome(self, node, env, piped=None):
        from ibl_v2_analysis import assigned_names
        from ibl_v2_exits import value_control
        d, kind = node.data, node.kind
        if kind == 'sequence':
            return self.sequence(node, env)
        if kind == 'if':
            empty = Node('sequence', node.end, node.end, {'statements': []})
            return self.choice(d['value'], d['body'], d['otherwise'] or empty, env)
        if kind == 'try':
            return self.recovery(node, env)
        if kind == 'repeat':
            return self.repeat(node, env)
        if kind in ('bind', 'return'):
            result = self.term('transform_exit', outcome=self.outcome(d['value'], env),
                               binding=d.get('name'), returned=kind == 'return')
        elif kind == 'fallback':
            parts = {}
            for part in ('left', 'right'):
                inner = Derivation(self.budget, pure=self.pure, exits=True)
                parts[part] = inner.ability(sorted(set(env) | lexical_inputs(d[part])), d[part])
                self.actions.update(inner.actions)
                self.functions.update(inner.functions)
            result = self.term('fallback_exits', captures=dict(env), mutated=sorted(assigned_names(d['left'])), **parts)
        elif kind == 'pipe' or kind == 'named_call' and value_control(d['fn']):
            operand = d['left'] if kind == 'pipe' else d['fn']
            outcome = self.outcome(operand, env)
            inner = Derivation(self.budget, pure=self.pure, exits=True)
            value_param = '@pipe' if kind == 'pipe' else '@callee'
            target = d['right'] if kind == 'pipe' else Node('named_call', node.start, node.end,
                {**d, 'fn': Node('ref', node.start, node.end, {'name': value_param})})
            params = sorted(set(env) | lexical_inputs(target) | {value_param}
                            | ({'@pipe'} if piped is not None else set()))
            local = {k: inner.term('input', name=k) for k in params}
            result = inner.outcome(target, local,
                                   local['@pipe'] if kind == 'pipe' or piped is not None else None)
            interface = inner.interface(params, result)
            self.actions.update(inner.actions)
            self.functions.update(inner.functions)
            result = self.term('continue', outcome=outcome, continuation=interface,
                               empty=False, exits=True, value_param=value_param, piped=piped)
        else:
            return self.finish(self.expr(node, env, piped), env)
        self.effects.append(result)
        return result

    def recovery(self, node, env):
        from ibl_v2_analysis import assigned_names
        d = node.data
        parts = {}
        for part in ('body', 'catch', 'final'):
            inner = Derivation(self.budget, pure=self.pure, exits=True)
            params = sorted(set(env) | lexical_inputs(d[part]) | ({'error'} if part == 'catch' else set()))
            parts[part] = inner.ability(params, d[part]) if d[part] else None
            self.actions.update(inner.actions)
            self.functions.update(inner.functions)
        result = self.term('recover', captures=dict(env), **parts,
                           mutated=sorted(assigned_names(d['body'])),
                           catch_mutated=sorted(assigned_names(d['catch'])),
                           final_mutated=sorted(assigned_names(d['final'])))
        self.effects.append(result)
        return result

    def repeat(self, node, env):
        d = node.data
        parts = {}
        for part, body in (('condition', d['value']), ('body', d['body'])):
            inner = Derivation(self.budget, pure=self.pure or part == 'condition', exits=part == 'body')
            params = sorted(set(env) | lexical_inputs(body, {'i'}) | {'i'})
            parts[part] = inner.ability(params, body)
            self.actions.update(inner.actions)
            self.functions.update(inner.functions)
        result = self.term('repeat', mode=d['mode'], captures=dict(env), **parts)
        self.effects.append(result)
        return result

    def nested(self, params, body, env):
        # Lexical captures are ordinary input relations, never observed values.
        inner = Derivation(self.budget)
        from ibl_v2_expr import free_names
        needed = free_names(body, frozenset(params))
        captures = {k: v for k, v in env.items() if k in needed}
        interface = inner.ability([*captures, *params], body)
        self.actions.update(inner.actions)
        self.functions.update(inner.functions)
        return self.term('ability', interface=interface, captures=captures, params=list(params))

    def pure_expr(self, node, env):
        previous, self.pure = self.pure, True
        try:
            return self.expr(node, env)
        finally:
            self.pure = previous

    def choice(self, condition, yes, no, env, *, pure=False):
        from ibl_v2_narrow import predicate
        test = self.pure_expr(condition, env)
        branches = []
        for body in (yes, no):
            # Pure choice selects a value inside the current exit; it does
            # not create another returning/continuing statement boundary.
            inner = Derivation(self.budget, pure=pure or self.pure, exits=self.exits and not pure)
            interface = inner.ability(env, body)
            self.actions.update(inner.actions)
            self.functions.update(inner.functions)
            branches.append(interface)
        result = self.term('choose', test=test, guard=predicate(condition),
                           captures=dict(env), yes=branches[0], no=branches[1], exits=self.exits and not pure)
        self.effects.append(result)
        return result

    def expr(self, node, env, piped=None):
        result = self._expr(node, env, piped)
        if node.kind in ('binary', 'unary') and node.data['op'] in (
                '==', '!=', '<', '>', '<=', '>=', 'in', 'and', 'or', '&&', '||', 'not', '!'):
            from ibl_v2_narrow import predicate
            result = self.term('predicate_value', value=result, guard=predicate(node), captures=dict(env))
        return result

    def _expr(self, node, env, piped=None):
        d, kind = node.data, node.kind
        if kind == 'sequence':
            return self.sequence(node, env)
        if kind == 'fallback':
            return self.term('normal_value', outcome=self.outcome(node, env))
        if kind in ('if', 'try', 'repeat'):
            # Source validation excludes control blocks from pure/container
            # positions. At value boundaries, outcome/continue owns their exits.
            raise Unsupported('control value requires an exit continuation')
        if kind == 'conditional':
            return self.choice(d['condition'], d['yes'], d['no'], env, pure=True)
        if kind == 'literal':
            return self.term('constant', wire=pack(d['value']))
        if kind == 'ref':
            if d['name'] not in env:
                raise Unsupported('unbound input')
            return env[d['name']]
        if kind == 'list':
            return self.term('list', members=[self.expr(v, env) for v in d['values']])
        if kind == 'record':
            entries = d.get('entries', list(d.get('fields', {}).items()))
            return self.checked('record', entries=[[k, self.expr(v, env)] for k, v in entries])
        if kind in ('field', 'index'):
            key = d['key']
            base = self.expr(d['base'], env)
            selector = self.expr(key, env) if isinstance(key, Node) else self.term('constant', wire=pack(key))
            return self.checked('project', base=base, selector=selector, access=kind)
        if kind == 'format':
            parts = [self.expr(v, env) if isinstance(v, Node) else self.term('constant', wire=pack(v))
                     for v in d['parts']]
            return self.checked('format', parts=parts)
        if kind == 'binary':
            if d['op'] in ('and', 'or', '&&', '||'):
                conjunction = d['op'] in ('and', '&&')
                literal = Node('literal', node.start, node.end, {'value': not conjunction})
                result = self.choice(d['left'], d['right'] if conjunction else literal,
                                     literal if conjunction else d['right'], env, pure=True)
                return self.checked('boolean', value=result)
            return self.checked('scalar', operator=d['op'],
                             operands=[self.expr(d['left'], env), self.expr(d['right'], env)])
        if kind == 'unary':
            return self.checked('scalar', operator=d['op'], operands=[self.expr(d['value'], env)])
        if kind == 'lambda':
            return self.nested(d['params'], d['body'], env)
        if kind == 'builtin':
            return self.term('builtin', name=d['name'])
        if kind == 'callable_ref':
            name = d['node'] + ':' + d['action']
            (self.functions if d['node'] == 'fn' else self.actions).add(
                d['action'] if d['node'] == 'fn' else name)
            return self.term('reference', name=name)
        if kind == 'pipe':
            return self.expr(d['right'], env, self.expr(d['left'], env))
        if kind == 'parallel':
            branches = [self.nested([], branch, env) for branch in parallel_branches(node)]
            result = self.term('parallel', branches=branches)
            self.effects.append(result)
            return result
        if kind == 'call' and d.get('target'):
            raise Unsupported('remote target')
        if kind == 'call' and (d['node'], d['action']) == ('table', 'each'):
            fields = record_fields(d['params'])
            options = {}
            for key, default in [('mode', 'map'), ('on_error', 'stop'), ('parallel', 1)]:
                value = fields.get(key)
                if value and value.kind != 'literal':
                    raise Unsupported('dynamic iteration option')
                options[key] = value.data['value'] if value else default
            items = self.expr(fields['items'], env) if 'items' in fields else piped
            if items is None:
                raise Unsupported('iteration items require a known argument binding')
            callback = self.nested(['it', 'i'], d['body'], env)
            result = self.term('map', items=items, callback=callback, **options)
            self.effects.append(result)
            return result
        if kind in ('call', 'named_call', 'pure_call'):
            if kind == 'call':
                target = self.expr(Node('callable_ref', node.start, node.end,
                                       {'node': d['node'], 'action': d['action']}), env)
                args, style = self.expr(d['params'], env), 'named'
            elif kind == 'named_call':
                target, args, style = self.expr(d['fn'], env), self.expr(d['params'], env), 'named'
            else:
                target, args, style = self.expr(d['fn'], env), [self.expr(v, env) for v in d['args']], 'positional'
            result = self.term('apply', target=target, arguments=args, style=style, piped=piped, pure=self.pure)
            self.effects.append(result)
            return result
        raise Unsupported(kind)


def derive(source):
    from ibl_v2_parser import parse
    from ibl_v2_analysis import constant_value
    from ibl_callable_contract import UNRESOLVED
    from ibl_v2_component import declaration
    statements = parse(source).data['statements']
    if len(statements) != 1 or statements[0].kind != 'def':
        raise Unsupported('single definition required')
    node = statements[0]
    if node.data.get('annotations'):
        raise Unsupported('explicit annotation refinement')
    defaults = {}
    for name, value in node.data['params'].items():
        if value is not None:
            constant = constant_value(value)
            if constant is UNRESOLVED:
                raise Unsupported('nonconstant default')
            defaults[name] = pack(constant)
    result = Derivation().ability(node.data['params'], node.data['body'], defaults,
                                  declaration(node)['completion'])
    result.update(name=node.data['name'], source_hash=digest(source), semantics=edition(),
                  default_expressions={k: source[v.start:v.end] for k, v in node.data['params'].items() if v is not None})
    return result


def constant_type(value):
    if isinstance(value, dict):
        return Type('Record', tuple((k, constant_type(v)) for k, v in value.items()), open=False)
    if isinstance(value, list):
        return ordered_list(constant_type(v) for v in value)
    result = infer(value)
    return Type(result.kind, literal=value) if type(value) in (str, int, bool) else result


def literal_node(typ, site):
    """Only literal selectors cross back into the primitive contract adapter."""
    if typ.kind == 'Record':
        return Node('record', site.start, site.end,
                    {'fields': {k: literal_node(v, site) for k, v in typ.fields}})
    if typ.kind == 'List' and typ.positions is not None:
        return Node('list', site.start, site.end,
                    {'values': [literal_node(v, site) for v in typ.positions]})
    if typ.literal is not None or typ.kind == 'Null':
        return Node('literal', site.start, site.end, {'value': typ.literal})
    return Node('ref', site.start, site.end, {'name': '<semantic-input>'})


def apply(compiler, interface, args, site):
    """Substitute actual values/capabilities in a finite relation DAG."""
    from ibl_v2_analysis import access_type
    memo = {}
    interface_identity = digest(interface)
    args = {**{k: constant_type(unpack(v)) for k, v in interface['defaults'].items()}, **args}

    def value(index):
        if index in memo:
            return memo[index]
        term = interface['terms'][index]
        op = term['op']
        if op == 'input':
            out = args.get(term['name'], UNKNOWN)
        elif op == 'constant':
            out = constant_type(unpack(term['wire']))
        elif op == 'unit':
            out = UNIT_T
        elif op == 'record':
            out = record_type(compiler, [(k, value(v), site) for k, v in term['entries']])
        elif op == 'list':
            out = ordered_list(value(v) for v in term['members'])
        elif op == 'project':
            projection = Node(term.get('access', 'field'), site.start, site.end, {})
            selector = value(term['selector'])
            out = access_type(compiler, projection, value(term['base']), selector.literal, selector)
        elif op == 'format':
            out = format_type(compiler, [(value(v), site) for v in term['parts']])
        elif op == 'builtin':
            out = Type('Callable', item=('builtin', term['name']))
        elif op == 'reference':
            owner, name = term['name'].split(':', 1)
            out = compiler.reference_type(Node('callable_ref', site.start, site.end,
                                              {'node': owner, 'action': name}), {})
        elif op == 'ability':
            key = digest(term['interface'])
            compiler.semantic_abilities[key] = term['interface']
            out = Type('Callable', item=('semantic', key,
                       tuple((k, value(v)) for k, v in term['captures'].items()), tuple(term['params'])))
        elif op == 'apply':
            target = value(term['target'])
            supplied = (value(term['arguments']) if term['style'] == 'named'
                        else [value(v) for v in term['arguments']])
            nodes = (literal_node(supplied, site) if isinstance(supplied, Type)
                     else [literal_node(v, site) for v in supplied])
            piped = value(term['piped']) if term.get('piped') is not None else None
            if piped is not None and term['style'] == 'positional':
                supplied.insert(0, piped)
                nodes.insert(0, literal_node(piped, site))
                piped = None
            # Each relation has its own identity even when multiple calls share a source site.
            call = Node('semantic_apply_' + digest([interface_identity, index])[:16], site.start, site.end, {})
            out = compiler.apply_callable(call, target, supplied, nodes, piped=piped,
                                          require_pure=term.get('pure', False))
        elif op == 'choose':
            from ibl_v2_narrow import branch_environment
            from ibl_v2_recovery import join_exits
            compiler.need(site, value(term['test']), BOOL)
            captured = {k: value(v) for k, v in term['captures'].items()}
            out = NEVER
            compiler.requirement_depth += 1
            try:
                for truth, branch in ((True, 'yes'), (False, 'no')):
                    refined, possible = branch_environment(captured, term['guard'], truth)
                    if not possible:
                        continue
                    out = join_exits(out, apply(compiler, term[branch], refined, site))
            finally:
                compiler.requirement_depth -= 1
            if out == NEVER and term.get('exits'):
                from ibl_v2_recovery import Exits
                out = Exits()
        elif op == 'exit':
            from ibl_v2_recovery import Exits
            bindings = {k: value(v) for k, v in term['bindings'].items()}
            result = value(term['value'])
            out = (Exits(returned=result, state=bindings) if term['returned']
                   else Exits(None if result == NEVER else (result, bindings), state=bindings))
        elif op == 'repeat':
            from ibl_v2_repeat import relation_repeat
            out = relation_repeat(compiler, term, {k: value(v) for k, v in term['captures'].items()}, site, apply)
        elif op == 'recover':
            from ibl_v2_recovery import relation_recovery
            out = relation_recovery(compiler, term, {k: value(v) for k, v in term['captures'].items()}, site, apply)
        elif op == 'transform_exit':
            from ibl_v2_exits import transform_exit
            out = transform_exit(value(term['outcome']), binding=term['binding'], returned=term['returned'])
        elif op == 'normal_value':
            exits = value(term['outcome'])
            out = exits.normal[0] if exits.normal is not None else NEVER
        elif op == 'frame_value':
            from ibl_v2_exits import exit_type
            out = exit_type(value(term['outcome']))
        elif op == 'continue':
            from ibl_v2_exits import continue_exits, exit_type
            def follow(result, bindings):
                from ibl_v2_recovery import Exits
                if term['empty']:
                    return Exits((result, bindings), state=bindings)
                supplied = dict(bindings)
                if term.get('value_param'):
                    supplied[term['value_param']] = result
                if term.get('piped') is not None:
                    supplied['@pipe'] = value(term['piped'])
                return apply(compiler, term['continuation'], supplied, site)
            out = continue_exits(value(term['outcome']), follow)
            if not term['exits']:
                out = exit_type(out)
        elif op == 'fallback_exits':
            from ibl_v2_exits import fallback_exits
            captured = {k: value(v) for k, v in term['captures'].items()}
            out = fallback_exits(compiler, captured,
                lambda local: apply(compiler, term['left'], local, site),
                lambda local: apply(compiler, term['right'], local, site), term['mutated'])
        elif op == 'predicate_value':
            from ibl_v2_narrow import predicate_value
            out = predicate_value(value(term['value']), term['guard'],
                                  {k: value(v) for k, v in term['captures'].items()})
        elif op == 'boolean':
            compiler.need(site, value(term['value']), BOOL)
            out = BOOL
        elif op == 'map':
            out = iteration_type(compiler, site, value(term['items']), term,
                lambda element: compiler.apply_callable(site, value(term['callback']),
                                                        [element, NUMBER], [site, site]))
        elif op == 'parallel':
            out = parallel_type(compiler, site, [
                lambda branch=branch: compiler.apply_callable(site, value(branch), [], [])
                for branch in term['branches']])
        elif op == 'scalar':
            operands = [value(i) for i in term['operands']]
            out = scalar_type(compiler, site, term['operator'], operands,
                              [literal_node(v, site) for v in operands])
        else:
            raise ValueError('Unknown semantic relation: ' + op)
        memo[index] = out
        return out

    # Roots retain derivation order. Evaluating every check first can force a
    # later container/parallel relation to evaluate an earlier captured call
    # inside the wrong effect frame. Values are shared; their effects are not
    # transferred to the frame that happens to project them later.
    for root in sorted(set(interface.get('checks', []) + interface['effects'])):
        value(root)
    return value(interface['result'])


def apply_function(compiler, sid, args, call):
    interface = compiler.semantic_functions[sid]
    node = compiler.functions[sid]
    from ibl_v2_requirements import parameter
    args = {**{k: parameter(sid, k) for k in interface['params'] if k not in interface['defaults']}, **args}
    compiler.checked.add(sid)
    compiler.component_declarations[sid] = {'completion': interface['completion']}
    outer = compiler.effects
    compiler.effects = set()
    try:
        returned = apply(compiler, interface, args, call or node)
        effects = set(compiler.effects)
    finally:
        compiler.effects |= outer
    compiler.call_effects.setdefault((call or node).id, set()).update(effects or {'pure'})
    compiler.function_contracts[sid] = {
        'name': interface['name'], 'params': {k: 'Unknown' for k in interface['params']},
        'required': [k for k in interface['params'] if k not in interface['defaults']],
        'pipe_input': next(iter(interface['params']), None),
        'default_expressions': interface.get('default_expressions', {}),
        'effects': sorted(effects) or ['pure'], 'actions': interface['actions'],
        'result': str(returned), 'result_contract': describe_type(returned),
        'source_hash': interface['source_hash'], 'semantic_interface': interface}
    return returned


def apply_primitive(compiler, node, key, spec, contract, args, fields, values, env, names, readonly):
    """Primitive transfer kernel shared by direct and relational applications.

    Legacy declarations are a narrow ingress. Selection/authorization stays at
    the adapter boundary; all value/effect transfer comes through this kernel.
    The compiler no longer reconstructs the result alongside the interface.
    """
    from ibl_v2_types import declared, static_text
    params = contract['params']
    for k, t in args.items():
        if k in params:
            compiler.need(node, t, declared(params[k]))
    compiler.effects.update(contract["effects"])
    compiler.call_effects.setdefault(node.id, set()).update(contract["effects"])
    # 자원 정체 = 타입 검사가 아는 컴파일 시 값(리터럴·변수·기본값·특수화 인자·정적 보간). 같은 값이면 같은 자원이다.
    from ibl_callable_contract import UNRESOLVED
    resource_args = {k: static_text(t) if static_text(t) is not None else UNRESOLVED
                     for k, t in args.items()}
    from ibl_v2_access import accesses
    if compiler.reachable:
        compiler.access_log.update(accesses(spec, contract, {**contract.get('defaults', {}), **resource_args}, key,
                                       runtime=getattr(compiler, 'resource_runtime', False), argument_types=args))
    result_type = declared(contract["result"])
    from ibl_v2_adapters import observed_result
    # A dynamic shape selector is present, not absent. Keep its marker
    # so observations from the default shape cannot leak into it.
    result_type = observed_result(key, spec.contract, values, result_type)
    from ibl_v2_adapters import declared_rows_result
    result_type = declared_rows_result(spec.contract, values, result_type)
    from ibl_v2_analysis import row_flow_type
    result_type = row_flow_type(compiler, node, contract, args, fields, values,
                                result_type, env, names, readonly)
    if (result_type.kind == "Record" and "items" not in dict(result_type.fields)
            and contract.get("analysis", {}).get("flow", {}).get("emits") == "items"):
        # 출력 형태는 flow.emits가 소유한다. 입력 봉투를 하나 받든 여러
        # 출처를 결합하든 같은 행 목록이다. 문서·건수 Record에는 적용하지
        # 않으며 명시된 items 타입과 실행 시 실제 값 검사는 그대로 둔다.
        result_type = Type("Record", (*result_type.fields, ("items", Type("List", item=UNKNOWN))),
                           open=result_type.open, observed=result_type.observed)
    if result_type.kind == "Unknown":
        compiler.need(node, UNKNOWN, UNKNOWN)
    return result_type


def frame_summary(compiler, analyze):
    """A branch owns returns and access/effect observations, never authority."""
    outer = compiler.returns, compiler.access_log, compiler.effects
    compiler.returns, compiler.access_log, compiler.effects = [], set(), set()
    try:
        result = analyze()
        for returned in compiler.returns:
            result = join(result, returned)
        return result, set(compiler.effects), set(compiler.access_log)
    finally:
        compiler.returns, accesses, effects = outer
        compiler.access_log |= accesses
        compiler.effects |= effects


def parallel_type(compiler, site, branches):
    """Compose independently framed branches with the existing admission law."""
    from ibl_v2_access import conflicts
    types, accesses, conflict, effects = [], set(), set(), set()
    for analyze in branches:
        result, branch_effects, branch_accesses = frame_summary(compiler, analyze)
        types.append(result)
        conflict.update(conflicts(accesses, branch_accesses))
        accesses.update(branch_accesses)
        effects.update(branch_effects)
    if conflict:
        compiler.issue(site, 'PARALLEL_WRITE_CONFLICT',
                       f'병렬 가지가 같은 선언 자원에 씁니다: {sorted(conflict)}')
    if len(types) > 1 and 'unknown' in effects:
        compiler.warn(site, 'PARALLEL_RESOURCE_UNKNOWN',
                      '병렬 가지에 효과 미상 호출이 있어 실행 시 자원 독립성을 확정할 수 없어 거절됩니다. '
                      '순차로 돌리거나 효과를 선언한 등록 스크립트를 쓰세요.')
    return ordered_list(types)


def iteration_type(compiler, site, items, options, analyze):
    """One row/result/effect transfer for source and saved sequential/parallel each.

    Static resource checks are necessary conditions. Runtime admission still
    resolves actual rows and resources before launching any external effect.
    """
    from ibl_v2_types import rows_type
    items = rows_type(items)
    compiler.need(site, items, Type('List', item=UNKNOWN))
    if options['mode'] not in ('map', 'flat_map', 'effect') or options['on_error'] not in ('stop', 'collect'):
        compiler.issue(site, 'EACH_MODE', 'each mode/on_error가 잘못되었습니다.')
    if options['on_error'] == 'collect' and options['mode'] != 'map':
        compiler.issue(site, 'EACH_COLLECT', 'on_error:collect는 map에서만 지원합니다.')
    parallel = options['parallel']
    if type(parallel) is not int or not 1 <= parallel <= 8:
        compiler.issue(site, 'CONCURRENCY', 'parallel은 1~8 정수입니다.')
    element = (items.item or UNKNOWN) if items.kind == 'List' else UNKNOWN
    previous = compiler.reachable
    compiler.reachable = previous and items.positions != ()
    try:
        result, effects, accesses = frame_summary(compiler, lambda: analyze(element))
    finally:
        compiler.reachable = previous
    single = items.positions is not None and len(items.positions) <= 1
    if type(parallel) is int and parallel > 1 and not single:
        if 'unknown' in effects:
            compiler.warn(site, 'PARALLEL_RESOURCE_UNKNOWN',
                          '병렬 반복 안에 효과 미상 호출이 있어 실행 시 가지가 둘 이상이면 자원 독립성을 '
                          '확정할 수 없어 거절됩니다. 순차(parallel:1)로 돌리거나 효과를 선언한 등록 스크립트를 쓰세요.')
        if any(a.mode == 'write' and a.resources for a in accesses):
            compiler.issue(site, 'PARALLEL_WRITE_CONFLICT',
                           f'each 병렬 반복이 모두 같은 선언 자원에 씁니다: {sorted(a.action for a in accesses if a.mode == "write")}')
    if options['mode'] == 'effect':
        return UNIT_T
    if options['mode'] == 'flat_map':
        compiler.need(site, result, Type('List', item=UNKNOWN))
        return result
    if options['on_error'] == 'collect':
        result = Type('Result', item=result)
    return Type('List', item=result)


def record_type(compiler, entries):
    """Ordered record overlay shared by source and independently applied relations.

    An open spread may replace earlier fields; later explicit fields restore
    their guarantees. The field values keep callable/ref ownership information.
    """
    if all(key is not None for key, _, _ in entries):
        return Type('Record', tuple((key, typ) for key, typ, _ in entries), open=False)
    result = Type('Record', open=False)
    for key, typ, site in entries:
        if key is None:
            compiler.need(site, typ, Type('Record'))
        candidates = set()
        for base in alternatives(result):
            for patch in (alternatives(typ) if key is None else (typ,)):
                fields, opened = dict(base.fields), base.open
                if key is not None:
                    fields[key] = patch
                elif patch.kind == 'Record':
                    if patch.open:
                        fields = dict.fromkeys(fields, UNKNOWN)
                    fields.update(dict(patch.fields))
                    opened |= patch.open
                else:
                    fields = dict.fromkeys(fields, UNKNOWN)
                    opened = True
                candidates.add(Type('Record', tuple(fields.items()), open=opened))
        # Keep finite alternatives, including optional fields and discriminants.
        # Beyond the bound retain guaranteed common fields as an open record;
        # do not turn uncertain overwrites into guarantees.
        if len(candidates) > 64:
            common = set.intersection(*(set(dict(v.fields)) for v in candidates))
            fields = dict.fromkeys(common, NEVER)
            for candidate in candidates:
                for name in common:
                    fields[name] = join(fields[name], dict(candidate.fields)[name])
            result = Type('Record', tuple(sorted(fields.items())), open=True)
            compiler.warn(site, 'RECORD_RELATION_LIMIT',
                          '레코드 확장의 후보가 64개를 넘습니다. 공통 필드만 정적으로 보존합니다.')
        else:
            result = NEVER
            for candidate in sorted(candidates, key=lambda v: v._key):
                result = join(result, candidate)
    return result


def format_type(compiler, parts):
    """Scalar interpolation; preserve known resource identity, never run a value."""
    from ibl_v2_types import compatible, static_text
    expected = join(join(TEXT, NUMBER), BOOL)
    known = []
    for typ, site in parts:
        if not compatible(typ, expected):
            compiler.issue(site, 'FORMAT_TYPE', f'보간에는 Text·Number·Bool이 필요하지만 {typ}입니다.',
                           expected=str(expected), actual=str(typ))
        elif typ.kind == 'Unknown':
            compiler.need(site, typ, expected)
        known.append(static_text(typ) if static_text(typ) is not None else
                     (str(typ.literal) if typ.kind == 'Number' and type(typ.literal) is int else None))
    if known and all(isinstance(part, str) for part in known):
        return Type('Text', literal=''.join(known))
    return TEXT


def scalar_type(compiler, node, op, values, operand_nodes):
    """Shared scalar transfer; numeric observation belongs to value_semantics."""
    from ibl_v2_analysis import numeric_operand
    from ibl_v2_types import static_text
    never = next((t for t in values if t.kind == "Never"), None)
    if never is not None:
        # 도달할 수 없는 값이 낀 연산은 통째로 도달 불가다. 남은 피연산자를 숫자로 검사하면
        # 이어 붙이기의 문자열 리터럴이 거짓 NUMBER_REQUIRED 가 된다(긴문장 10회차 L10-3).
        return never
    if op in ("and", "or", "&&", "||", "!", "not"):
        for i, t in enumerate(values):
            compiler.requirement_depth += int(i > 0)
            try:
                compiler.need(node, t, BOOL)
            finally:
                compiler.requirement_depth -= int(i > 0)
        return BOOL
    if op in ("==", "!=", "<", ">", "<=", ">=", "in"):
        return BOOL
    if op == "+" and len(values) == 2 and values[0].kind == values[1].kind and values[0].kind in ("List", "Text"):
        if values[0].kind == "List":
            return concat_lists(*values)
        texts = [static_text(t) for t in values]
        if all(t is not None for t in texts):
            from common.value_semantics import normalized_text
            return Type("Text", literal=normalized_text("".join(texts)))
        return TEXT
    if op == "+" and any(t.kind in ("Unknown", "Union") for t in values):
        # An unknown accumulator/callback operand may concatenate.
        # Do not select numeric addition until both shapes are known.
        if all(member.kind in ("Unknown", "List", "Text", "Number")
               for t in values for member in alternatives(t)):
            compiler.need(node, UNKNOWN, UNKNOWN)
            return UNKNOWN
    for operand, typ in zip(operand_nodes, values):
        numeric_operand(compiler, operand, typ)
    return NUMBER
