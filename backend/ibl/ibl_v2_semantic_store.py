"""Certified interface persistence and the separate execution-body boundary."""
import copy

from ibl_v2_ir import Node, digest, unpack, Fault
from ibl_v2_semantic import PROTOCOL, Unsupported, derive, edition


def certify(row, library, registry):
    try:
        interface = derive(row['source'])
        dependencies = {}
        for name in interface['functions']:
            lower = library.interfaces.get(name)
            if lower is None:
                raise Unsupported('dependency needs source checking: ' + name)
            dependencies[name] = {'source_hash': lower['source_hash'],
                                  'function_ref': library.references.get(name)}
        interface['dependencies'] = dependencies
        interface['contracts'] = {name: digest(registry[name].contract) for name in interface['actions']}
        # Source bytes use the semantic digest; storage has its independent CAS digest.
        return {'semantic_interface': interface}
    except Unsupported as exc:
        return {'semantic_limit': str(exc)}


def attach(library, row, view):
    interface = row.get('semantic_interface')
    if not interface:
        library.interface_limits[row['name']] = row.get('semantic_limit', 'legacy revision: source checking required')
        return
    if (interface.get('protocol') != PROTOCOL or interface.get('semantics') != edition()
            or interface.get('source_hash') != digest(row['source'])):
        library.interface_limits[row['name']] = 'semantic edition/source changed: revalidation required'
        return
    current = {r['name']: r for r in view['records'].values() if r.get('state') == 'active'}
    for name, dependency in interface.get('dependencies', {}).items():
        if name not in current or digest(current[name]['source']) != dependency['source_hash']:
            library.interface_limits[row['name']] = 'dependency changed: revalidation required'
            return
    library.interfaces[row['name']] = copy.deepcopy(interface)


def resolve(compiler, name):
    interface = getattr(compiler.definitions, 'interfaces', {}).get(name)
    if interface is None:
        return None
    if any(key not in compiler.registry or digest(compiler.registry[key].contract) != revision
           for key, revision in interface['contracts'].items()):
        compiler.guards.append({'source_span': {'start': 0, 'end': 0},
                                'expected': '어휘 계약 변경: 저장 의미 인터페이스를 재검사합니다.'})
        return None
    # Source is deliberately not requested here. The stub contains signature
    # and completion only; preflight cannot silently count its empty body as pure.
    sid = 'semantic:' + name + ':' + interface['source_hash']
    node = Node(sid, 0, 0, {'name': name, 'params': {
        k: None if k not in interface['defaults'] else Node('literal', 0, 0, {'value': unpack(interface['defaults'][k])})
        for k in interface['params']}, 'body': Node('sequence', 0, 0, {'statements': []}),
        'semantic_interface': interface})
    compiler.functions[node.id] = node
    compiler.function_scopes[node.id] = {}
    compiler.external[name] = node.id
    compiler.semantic_functions[node.id] = interface
    compiler.component_declarations[node.id] = {'completion': interface['completion']}
    return node.id


def execution_plan(plan):
    """Bind implementation IR only when execution is requested.

    This transitional binder uses the existing compiler for implementation
    lowering. Public suitability and result/effect substitution have already
    been decided without those bodies. It neither executes tools nor grants
    authority. The existing runtime still owns authorization and receipts.
    """
    if not getattr(plan, 'semantic_functions', None):
        return plan
    from ibl_v2_compile import compile_program
    if any(value is None for value in plan.definitions.values()):
        raise Fault('IMPLEMENTATION_REQUIRED', '실행에는 검사한 판본의 구현 본문이 필요합니다.', kind='protocol')
    library = copy.deepcopy(plan.definitions)
    library.interfaces = {}
    source = plan.source[:plan.dependencies['source_map'][0]['end']]
    for interface in plan.semantic_functions.values():
        if digest(library[interface['name']]) != interface['source_hash']:
            raise Fault('DEFINITION_CHANGED', '검사 이후 함수 구현이 바뀌었습니다.', kind='protocol')
    result = compile_program(source, plan.registry, definitions=library, input_types=plan.input_types,
                             declared_inputs=set(plan.input_types) | set(plan.unspecified))
    previous = {digest(v) for v in plan.dependencies.get('calls', {}).values()}
    current = {digest(v) for v in result.dependencies.get('calls', {}).values()}
    if not previous <= current:
        raise Fault('DEFINITION_CHANGED', '검사 이후 실행 의존 판본이 바뀌었습니다.', kind='protocol')
    result.issues = plan.issues + result.issues
    result.unspecified = plan.unspecified
    # Lowering coordinates are implementation detail; preserve the checked identity.
    result.fingerprint = plan.fingerprint
    return result
