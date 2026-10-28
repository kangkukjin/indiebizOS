"""Bind certified implementation bytes to an already checked semantic plan.

No type/effect analysis, contract specialization or tool invocation happens here.
Application metadata is a product of interface substitution in the checker.
"""
import copy

from ibl_v2_ir import Node, Fault, digest


def merge(target, source):
    """Accumulate dependency alternatives across abstract applications."""
    for key, value in source.items():
        if key in ('dependency_args', 'dependency_snapshot'):
            target[key] = copy.deepcopy(value)
        elif isinstance(value, dict):
            merge(target.setdefault(key, {}), value)
        elif isinstance(value, list) and key == 'dependency_bindings':
            alternatives = target.setdefault(key, [])
            for item in value:
                if item not in alternatives:
                    alternatives.append(copy.deepcopy(item))
        else:
            target[key] = copy.deepcopy(value)


def record_application(compiler, interface, term, call):
    owner = interface.get('implementation')
    if owner is None:
        return
    key = (owner, *term['origin'])
    entry = compiler.implementation_bindings.setdefault(key, {'effects': set(), 'data': {}})
    entry['effects'].update(compiler.call_effects.get(call.id, {'unknown'}))
    # The virtual arguments were only abstract-analysis inputs, not executable IR.
    applications = {target: {k: v for k, v in data.items() if k in (
        'dependency_args', 'dependency_snapshot', 'dependency_bindings')}
        for target, data in call.data.get('applications', {}).items()}
    merge(entry['data'], {'applications': applications})


def bind(plan):
    if not plan.semantic_functions or getattr(plan, 'implementation_bound', False):
        return plan
    from ibl_v2_parser import Parser
    from ibl_v2_semantic import edition, PROTOCOL
    result = copy.deepcopy(plan)
    external = {interface['name']: sid for sid, interface in plan.semantic_functions.items()}
    pending = list(external)
    loaded = set()

    def resolve(name):
        if name in external:
            return external[name]
        interface = getattr(result.definitions, 'interfaces', {}).get(name)
        if interface is None:
            if 'fn:' + name in result.registry:
                return None
            raise Fault('IMPLEMENTATION_REQUIRED', '검사한 하위 함수 인터페이스가 없습니다: ' + name, kind='protocol')
        sid = Node('semantic:' + name + ':' + interface['source_hash'], 0, 0).id
        external[name] = sid
        result.semantic_functions[sid] = interface
        pending.append(name)
        return sid

    def link(value, owner, offset):
        if isinstance(value, Node):
            d = value.data
            if value.kind in ('call', 'callable_ref') and d.get('node') == 'fn':
                sid = resolve(d['action'])
                if sid:
                    d['symbol'] = sid
            entry = result.implementation_bindings.get((owner, value.kind, value.start - offset, value.end - offset))
            if entry:
                result.node_effects[value.id] = set(entry['effects'])
                merge(d, entry['data'])
                if value.kind == 'call' and not d.get('symbol'):
                    target = d['node'] + ':' + d['action']
                    merge(d, entry['data'].get('applications', {}).get(target, {}))
            # Metadata is not source AST. Visiting it could alter checked inputs.
            for key, child in list(d.items()):
                if key not in ('applications', 'dependency_args', 'dependency_snapshot', 'dependency_bindings'):
                    link(child, owner, offset)
        elif isinstance(value, dict):
            for child in value.values():
                link(child, owner, offset)
        elif isinstance(value, (tuple, list)):
            for child in value:
                link(child, owner, offset)

    while pending:
        name = pending.pop(0)
        if name in loaded:
            continue
        loaded.add(name)
        sid = external[name]
        interface = result.semantic_functions[sid]
        code = result.definitions.get(name)
        if code is None:
            raise Fault('IMPLEMENTATION_REQUIRED', '실행에는 검사한 판본의 구현 본문이 필요합니다.', kind='protocol')
        if (digest(code) != interface['source_hash'] or interface.get('semantics') != edition()
                or interface.get('protocol') != PROTOCOL):
            raise Fault('DEFINITION_CHANGED', '검사 이후 함수 구현·의미 판본이 바뀌었습니다.', kind='protocol')
        if any(key not in result.registry or digest(result.registry[key].contract) != revision
               for key, revision in interface['contracts'].items()):
            raise Fault('DEFINITION_CHANGED', '검사 이후 어휘 계약이 바뀌었습니다.', kind='protocol')
        offset = len(result.source) + 1
        result.source += '\n' + code
        body = Parser(code, offset=offset).program()
        definition, = body.data['statements']
        definition.data['symbol'] = sid
        result.functions[sid] = definition
        result.dependencies['source_map'].append({'name': name, 'start': offset, 'end': len(result.source),
            'function_ref': getattr(result.definitions, 'references', {}).get(name)})
        link(definition, interface['source_hash'], offset)

    # Check assets against the original snapshots, never acquire new snapshots
    # as a second source-level suitability judgment.
    for entry in result.implementation_bindings.values():
        for target, data in entry['data'].get('applications', {}).items():
            spec = result.registry.get(target)
            if spec and spec.dependency:
                for binding in data.get('dependency_bindings', []):
                    snapshot = binding['snapshot']
                    deferred = isinstance(snapshot, dict) and snapshot.get('binding') == 'invocation'
                    if not deferred and spec.dependency(binding['args']) != snapshot:
                        raise Fault('DEFINITION_CHANGED', '검사 이후 실행 의존 판본이 바뀌었습니다.', kind='protocol')
    symbols = {sid: result.functions[sid].id for sid in external.values()}
    def relocate_symbol(data):
        symbol = data.get('symbol')
        if isinstance(symbol, str) and symbol in symbols:
            data['symbol'] = symbols[symbol]

    def relocate(value):
        if isinstance(value, Node):
            relocate_symbol(value.data)
            if 'applications' in value.data:
                value.data['applications'] = {symbols.get(k, k): v for k, v in value.data['applications'].items()}
                for metadata in value.data['applications'].values():
                    relocate_symbol(metadata)
            relocate(value.data)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key not in ('dependency_args', 'dependency_snapshot', 'dependency_bindings'):
                    relocate(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                relocate(child)
    relocate([result.root, result.functions])
    for field in ('functions', 'function_scopes', 'function_contracts', 'components', 'semantic_functions'):
        setattr(result, field, {symbols.get(k, k): v for k, v in getattr(result, field).items()})
    result.function_scopes = {key: {name: symbols.get(sid, sid) for name, sid in scope.items()}
                              for key, scope in result.function_scopes.items()}
    result.implementation_bound = True
    return result
