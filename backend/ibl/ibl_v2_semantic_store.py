"""Certified interface persistence and the separate execution-body boundary."""
import copy
import json

from ibl_v2_ir import Node, digest, unpack
from ibl_v2_semantic import PROTOCOL, Unsupported, derive, edition


def interface_digest(interface):
    # Mapping order is not relation semantics; YAML canonicalizes mappings.
    # Ordered record entries and application arguments remain explicit lists.
    return digest(json.dumps(interface, ensure_ascii=False, sort_keys=True))


def certify(row, library, registry):
    try:
        interface = derive(row['source'])
        dependencies = {}
        for name in interface['functions']:
            lower = library.interfaces.get(name)
            if lower is None:
                raise Unsupported('dependency needs source checking: ' + name)
            dependencies[name] = {'source_hash': lower['source_hash'],
                                  'interface_hash': interface_digest(lower),
                                  'function_ref': library.references.get(name)}
        missing = set(interface['actions']) - set(registry)
        if missing:
            raise Unsupported('primitive contract unavailable: ' + ', '.join(sorted(missing)))
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
    def valid(item, seen):
        if item['name'] in seen:
            return False
        lower_interface = item.get('semantic_interface') or {}
        if (lower_interface.get('semantics') != edition() or lower_interface.get('protocol') != PROTOCOL
                or lower_interface.get('source_hash') != digest(item['source'])):
            return False
        for name, dependency in lower_interface.get('dependencies', {}).items():
            lower = current.get(name)
            if (lower is None or digest(lower['source']) != dependency['source_hash']
                    or interface_digest(lower.get('semantic_interface')) != dependency.get('interface_hash')
                    or not valid(lower, seen | {item['name']})):
                return False
        return True
    if not valid(row, set()):
        library.interface_limits[row['name']] = 'dependency changed: revalidation required'
        return
    library.interfaces[row['name']] = copy.deepcopy(interface)


def contracts_current(interface, library, registry, seen=frozenset()):
    name = interface['name']
    if name in seen or any(key not in registry or digest(registry[key].contract) != revision
                           for key, revision in interface['contracts'].items()):
        return False
    return all(lower in library.interfaces and contracts_current(
        library.interfaces[lower], library, registry, seen | {name}) for lower in interface['dependencies'])


def resolve(compiler, name):
    interface = getattr(compiler.definitions, 'interfaces', {}).get(name)
    if interface is None:
        return None
    if not contracts_current(interface, compiler.definitions, compiler.registry):
        compiler.definitions.interface_limits[name] = 'primitive contract changed: revalidation required'
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
    from ibl_v2_binding import bind
    return bind(plan)


def application_view(interface, contract):
    """A compact discovery view, derived from the very interface being applied.

    This is not a replacement relation or proof for every input. Discovery uses
    this view; check substitutes actual arguments in the complete saved relation.
    """
    names = ('params', 'required', 'pipe_input', 'default_expressions', 'result',
             'result_contract', 'effects', 'requirements', 'actions')
    return {'protocol': 'ibl-ability-view/1', 'relation_hash': digest(interface),
            'status': 'parameterized',
            **{k: copy.deepcopy(contract[k]) for k in names if k in contract},
            **{k: copy.deepcopy(interface[k]) for k in ('completion', 'failure', 'lifetime')},
            'apply': {'edition': 2, 'check': True, 'code': '[fn:' + interface['name'] + ']{'
                + ','.join(k + ':$' + k for k in interface['params'] if k not in interface['defaults']) + '}'},
            'note': '결과·효과·조건은 인자와 하위 능력에 따라 달라집니다. apply에 실제 inputs를 넣어 검사하세요. 완료는 실행 증거로 확인합니다.'}
