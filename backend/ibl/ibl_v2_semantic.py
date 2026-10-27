"""Finite, parameterized relations for separately checked IBL abilities.

These are type/effect transfer equations, not invocation observations or source
ASTs. Bindings disappear; unused pure values disappear; calls remain effect
roots. Application never evaluates a business value or an implementation body.
Unsupported control flow stays on the explicitly reported source-check boundary.
"""
from pathlib import Path

from ibl_v2_ir import Node, digest, record_fields, pack, unpack
from ibl_v2_types import (Type, UNKNOWN, UNIT_T, BOOL, NUMBER, TEXT, NULL,
                          infer, ordered_list, concat_lists, describe_type, alternatives)

PROTOCOL = 'ibl-semantic/1'


def edition():
    root = Path(__file__).parent
    return digest({name: (root / name).read_text() for name in (
        'ibl_v2_semantic.py', 'ibl_v2_semantic_store.py', 'ibl_v2_types.py',
        'ibl_v2_analysis.py', 'ibl_v2_call_analysis.py', 'ibl_v2_adapters.py',
        'ibl_v2_requirements.py')})


class Unsupported(ValueError):
    pass


class Derivation:
    def __init__(self):
        self.terms, self.index, self.effects, self.checks = [], {}, [], []
        self.actions, self.functions = set(), set()

    def term(self, op, **fields):
        value = {'op': op, **fields}
        key = digest(value)
        if key not in self.index:
            self.index[key] = len(self.terms)
            self.terms.append(value)
        return self.index[key]

    def checked(self, op, **fields):
        result = self.term(op, **fields)
        self.checks.append(result)
        return result

    def ability(self, params, body, defaults=None, completion=None):
        env = {k: self.term('input', name=k) for k in params}
        result = self.sequence(body, env) if body.kind == 'sequence' else self.expr(body, env)
        return {'protocol': PROTOCOL, 'params': list(params), 'defaults': defaults or {},
                'terms': self.terms, 'result': result, 'effects': self.effects, 'checks': self.checks,
                'actions': sorted(self.actions), 'functions': sorted(self.functions),
                'completion': completion or [],
                'failure': 'propagate-Fault; collect-is-Result',
                'lifetime': 'preserve-input-and-call-result-owners',
                'evidence': 'derived; runtime-receipts-required'}

    def sequence(self, body, env):
        result = self.term('unit')
        for statement in body.data['statements']:
            if statement.kind == 'bind':
                env[statement.data['name']] = self.expr(statement.data['value'], env)
                result = self.term('unit')
            elif statement.kind == 'return':
                return self.expr(statement.data['value'], env)
            else:
                result = self.expr(statement, env)
        return result

    def nested(self, params, body, env):
        # Lexical captures are ordinary input relations, never observed values.
        inner = Derivation()
        from ibl_v2_expr import free_names
        needed = free_names(body, frozenset(params))
        captures = {k: v for k, v in env.items() if k in needed}
        interface = inner.ability([*captures, *params], body)
        self.actions.update(inner.actions)
        self.functions.update(inner.functions)
        return self.term('ability', interface=interface, captures=captures, params=list(params))

    def expr(self, node, env, piped=None):
        d, kind = node.data, node.kind
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
            if any(k is None for k, _ in entries):
                raise Unsupported('record spread')
            return self.term('record', fields={k: self.expr(v, env) for k, v in entries})
        if kind in ('field', 'index'):
            key = d['key']
            if isinstance(key, Node):
                if key.kind != 'literal':
                    raise Unsupported('dynamic projection')
                key = key.data['value']
            return self.checked('project', base=self.expr(d['base'], env), key=key)
        if kind == 'binary':
            if d['op'] in ('and', 'or', '&&', '||'):
                raise Unsupported('short circuit refinement')
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
            if items is None or options['parallel'] != 1:
                raise Unsupported('parallel iteration admission')
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
            result = self.term('apply', target=target, arguments=args, style=style, piped=piped)
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
    from ibl_v2_analysis import access_type, numeric_operand
    from ibl_v2_types import rows_type
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
            out = Type('Record', tuple((k, value(v)) for k, v in term['fields'].items()), open=False)
        elif op == 'list':
            out = ordered_list(value(v) for v in term['members'])
        elif op == 'project':
            out = access_type(compiler, site, value(term['base']), term['key'])
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
            out = compiler.apply_callable(call, target, supplied, nodes, piped=piped)
        elif op == 'map':
            rows = rows_type(value(term['items']))
            compiler.need(site, rows, Type('List', item=UNKNOWN))
            element = rows.item if rows.kind == 'List' else UNKNOWN
            returned = compiler.apply_callable(site, value(term['callback']),
                                                [element, NUMBER], [site, site])
            if term['mode'] == 'effect':
                out = UNIT_T
            elif term['mode'] == 'flat_map':
                compiler.need(site, returned, Type('List', item=UNKNOWN))
                out = returned
            else:
                if term['on_error'] == 'collect':
                    returned = Type('Result', item=returned)
                out = Type('List', item=returned)
        elif op == 'scalar':
            operands = [value(i) for i in term['operands']]
            operator = term['operator']
            if operator in ('==', '!=', '<', '>', '<=', '>=', 'in'):
                out = BOOL
            elif operator in ('!', 'not'):
                compiler.need(site, operands[0], BOOL)
                out = BOOL
            elif operator == '+' and len(operands) == 2 and operands[0].kind == operands[1].kind == 'List':
                out = concat_lists(*operands)
            elif operator == '+' and all(v.kind == 'Text' for v in operands):
                from ibl_v2_types import static_text
                from common.value_semantics import normalized_text
                texts = [static_text(v) for v in operands]
                out = (Type('Text', literal=normalized_text(''.join(texts)))
                       if all(v is not None for v in texts) else TEXT)
            elif operator == '+' and any(v.kind in ('Unknown', 'Union') for v in operands) and all(
                    member.kind in ('Unknown', 'List', 'Text', 'Number')
                    for operand in operands for member in alternatives(operand)):
                compiler.need(site, UNKNOWN, UNKNOWN)
                out = UNKNOWN
            else:
                for operand in operands:
                    numeric_operand(compiler, site, operand)
                out = NUMBER
        else:
            raise ValueError('Unknown semantic relation: ' + op)
        memo[index] = out
        return out

    for condition in interface.get('checks', []):
        value(condition)
    for effect in interface['effects']:
        value(effect)
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
