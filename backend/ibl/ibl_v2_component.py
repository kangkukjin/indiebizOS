"""Definition contracts shared by vocabulary, scripts and composed functions.

Descriptions are inert data. Instance state, failure capabilities and receipts
belong to the evaluator; copying this record cannot certify a business value.
Child definitions remain references rather than recursively expanded contracts.
"""
import copy
from ibl_v2_ir import Fault, digest

PROTOCOL = 'ibl-component/1'


def completion_templates(specs, params):
    from ibl_v2_completion import validate
    check = copy.deepcopy(specs)
    if not isinstance(check, list):
        return validate(check)
    for spec in check:
        if not isinstance(spec, dict):
            continue
        for source in spec.get('sources', []) if isinstance(spec.get('sources'), list) else []:
            if not isinstance(source, dict) or not isinstance(source.get('targets'), dict):
                continue
            for key, value in source['targets'].items():
                if isinstance(value, dict):
                    if (set(value) - {'parameter', 'path'} or value.get('parameter') not in params
                            or not isinstance(value.get('path', []), list)
                            or len(value.get('path', [])) > 64
                            or any(type(k) not in (str, int) for k in value.get('path', []))):
                        raise Fault('COMPONENT_CONTRACT', '대상 관계는 선언 인자의 parameter·path입니다.', kind='compile')
                    source['targets'][key] = '<bound-parameter>'
    validate(check)
    return copy.deepcopy(specs or [])


def declaration(node):
    from ibl_v2_analysis import constant_value
    if 'contract' not in node.data:
        return {'completion': []}
    try:
        value = constant_value(node.data['contract'])
    except (ValueError, Fault) as exc:
        raise Fault('COMPONENT_CONTRACT', '부품 계약은 실행하지 않는 상수 Record입니다.', kind='compile') from exc
    if not isinstance(value, dict) or set(value) - {'completion'}:
        raise Fault('COMPONENT_CONTRACT', '정의 계약의 선언 필드는 completion입니다.', kind='compile')
    return {'completion': completion_templates(value.get('completion', []), node.data['params'])}


def normalize(identity, contract, *, producer, completion=None):
    """One finite schema, including explicit unknowns instead of invented proofs."""
    effects = sorted(set(contract.get('effects') or ['unknown']))
    obligations = completion_templates(completion if completion is not None else contract.get('completion', []),
                                       contract.get('params', {}))
    return {'protocol': PROTOCOL, 'identity': identity, 'producer': producer,
            'inputs': {'types': copy.deepcopy(contract.get('param_contracts', contract.get('params', {}))),
                       'required': list(contract.get('required', contract.get('params', {}))),
                       'relations': copy.deepcopy(contract.get('requirements', {})),
                       'style': contract.get('argument_style', 'named'),
                       'pipe_input': contract.get('pipe_input'),
                       'defaults': copy.deepcopy(contract.get('defaults', contract.get('default_expressions', {}))),
                       'aliases': copy.deepcopy(contract.get('aliases', {})),
                       'variants': copy.deepcopy(contract.get('variants', []))},
            'output': copy.deepcopy(contract.get('result_contract', contract.get('result', 'Unknown'))),
            'effects': effects,
            'resources': copy.deepcopy(contract.get('accesses', {
                'read': contract.get('read_resources'), 'write': contract.get('write_resources')})),
            'failures': {'channel': 'Fault', 'catchable': 'runtime-only', 'result': 'explicit',
                         'propagation': 'runtime-capability', 'transport': 'diagnostic-only',
                         'alternatives': copy.deepcopy(contract.get('failures', [])), 'open': True},
            'completion': obligations,
            'lifecycle': {'definition': 'revision-bound', 'instance': 'invocation',
                          'foreign_values': 'owning-session', 'evidence': 'runtime-sidecar',
                          'adapter': copy.deepcopy(contract.get('adapter', {})),
                          'background': 'receipt-is-not-completion', 'cancellation': 'noncatchable'},
            'reuse': {'effects': 'receipts-only', 'repair': 'effect-dependency-proof'},
            'dependencies': [],
            'evidence': {'state': 'derived' if producer in ('function', 'lambda', 'program') else 'declared',
                         'certified': False}}


def compiled_contracts(compiler):
    result = {}
    for name in sorted(compiler.used_actions):
        contract = compiler.registry[name].contract
        result[name] = normalize({'name': name, 'revision': digest(contract)}, contract,
                                 producer=(contract.get('adapter') or {}).get('protocol', 'vocabulary'))
    for name, variants in compiler.component_variants.items():
        for revision, contract in variants.items():
            if contract == compiler.registry[name].contract:
                continue
            key = name + '@' + revision[:16]
            result[key] = normalize({'name': name, 'revision': revision}, contract,
                                    producer=(contract.get('adapter') or {}).get('protocol', 'vocabulary'))
            result[name]['dependencies'].append(key)
    for sid, contract in compiler.function_contracts.items():
        result[sid] = normalize({'name': contract['name'], 'revision': contract['source_hash']}, contract,
                                producer='function', completion=compiler.component_declarations[sid].get('completion'))
        if 'semantic_interface' in contract:
            result[sid]['semantic_interface'] = contract['semantic_interface']
    from ibl_v2_learning import walk_nodes
    from ibl_v2_types import describe_type
    for lid, typ in compiler.lambda_contracts.items():
        node = compiler.lambda_nodes[lid]
        result[lid] = normalize({'name': lid, 'revision': digest(compiler.source[node.start:node.end])},
                                {'params': {name: 'Unknown' for name in node.data['params']},
                                 'result': 'Unknown', 'effects': sorted(compiler.node_effects.get(node.data['body'].id, {'unknown'})) or ['pure'],
                                 'argument_style': 'positional'}, producer='lambda')
        result[lid]['captures'] = {name: describe_type(value) for name, value in typ.item[2]}
    for sid, node in {**compiler.functions, **compiler.lambda_nodes}.items():
        # Keep a finite graph. References preserve nested obligations without
        # expanding the same subtree at every promotion level.
        dependencies = set()
        for child in walk_nodes(node.data['body']):
            if child.kind == 'def':
                continue
            target = child.data.get('symbol')
            if target in result and target != sid:
                dependencies.add(target)
            key = str(child.data.get('node', '')) + ':' + str(child.data.get('action', ''))
            if key in result:
                dependencies.add(key)
        result[sid]['dependencies'] = sorted(dependencies)
    return result


def lift_completion(specs, parameter):
    """Substitute a nested input boundary without naming a script or action."""
    result = copy.deepcopy(specs)
    for spec in result:
        for source in spec['sources']:
            for key, target in source['targets'].items():
                if isinstance(target, dict):
                    source['targets'][key] = {'parameter': parameter,
                                              'path': [target['parameter'], *target.get('path', [])]}
    return result
