"""Invocation-owned completion state using the existing evaluator and receipts."""
import copy
from uuid import uuid4
from ibl_v2_ir import Fault


def bind_targets(specs, args):
    bound = copy.deepcopy(specs)
    for spec in bound:
        for source in spec['sources']:
            for key, target in source['targets'].items():
                if isinstance(target, dict):
                    try:
                        value = args[target['parameter']]
                        for part in target.get('path', []):
                            value = value[part]
                    except (KeyError, IndexError, TypeError) as exc:
                        raise Fault('COMPONENT_TARGET', '완료 원천의 입력 경로를 바인딩할 수 없습니다.', kind='protocol') from exc
                    if not isinstance(value, str):
                        raise Fault('COMPONENT_TARGET', '완료 원천 대상은 Text여야 합니다.', kind='protocol')
                    source['targets'][key] = value
    return bound


def execute(runtime, key, node, args, operation, *, contract=None):
    definition = contract or runtime.plan.components.get(key)
    if not definition or not definition['completion']:
        return operation()
    specs = bind_targets(definition['completion'], args)
    instance = uuid4().hex + ':'
    parents = getattr(runtime.local, 'obligations', ())
    runtime.local.obligations = (*parents, (instance, specs))
    result, success = None, False
    try:
        result = operation()
        success = True
    finally:
        runtime.local.obligations = parents
        from ibl_v2_completion import evaluate, undetermined
        try:
            outcome = evaluate(runtime, result, success, specs=specs)
        except Exception as exc:
            outcome = undetermined(specs, exc)
        outcome.update(component=key, identity=definition['identity'], instance=instance)
        with runtime.lock:
            runtime.component_outcomes.append(outcome)
        runtime.event(node, 'component_outcome', result.evidence if result else (),
                      component=key, instance=instance, status=outcome['status'])
        with runtime.commit_scope.lock:
            for duty in outcome['obligations']:
                if duty['status'] == 'satisfied':
                    name = instance + duty['id']
                    runtime.commit_scope.certified.add(name)
                    runtime.commit_scope.certified_evidence[name] = duty['evidence_refs']
        if success:
            from dataclasses import replace
            certificates = tuple(dict(d) for d in outcome['obligations'] if d['status'] == 'satisfied')
            result = replace(result, certificates=result.certificates + certificates)
    return result



def observation_duties(runtime, key, args, eid):
    scopes = ((runtime.completion_scope, runtime.completion), *getattr(runtime.local, 'obligations', ()))
    return {instance + duty['id']: eid for instance, specs in scopes for duty in specs
            if any(s['action'] == key and all(args.get(k) == v for k, v in s['targets'].items())
                   for s in duty['sources'])}


def report(runtime, out, result=None):
    if not runtime.component_outcomes:
        return
    required = [d for o in runtime.component_outcomes for d in o['obligations'] if d['required']]
    status = ('satisfied' if required and all(d['status'] == 'satisfied' for d in required)
              else 'unsatisfied' if any(d['status'] == 'unsatisfied' for d in required) else 'undetermined')
    out['component_completion'] = {'protocol': 'ibl-component-outcomes/1', 'status': status,
                                   'instances': runtime.component_outcomes}


def export_certificates(runtime, result):
    """Export only certificates attached to this actual result, with exact paths.

    Bounded traversal never infers provenance from equal values. Omitted paths
    have no certificate; the original instance outcomes remain in the journal.
    """
    from ibl_v2_ir import pack, digest
    from ibl_v2_completion import selected_events
    pending = [(result, ())] if result is not None else []
    certificates, inspected = [], 0
    while pending and inspected < 2048:
        binding, path = pending.pop()
        inspected += 1
        unsafe = any(e.get('incomplete') for e in selected_events(runtime.trace, binding.control))
        if not unsafe:
            for cert in binding.certificates:
                try:
                    value = binding.value
                    for part in cert['scope']:
                        value = value[part]
                    if digest(pack(value)) == cert['value_hash']:
                        certificates.append({**cert, 'scope': [*path, *cert['scope']]})
                except (KeyError, IndexError, TypeError, Fault):
                    pass
        pending.extend((child.controlled(binding.control), (*path, key))
                       for key, child in (binding.parts or {}).items())
    return {'protocol': 'ibl-component-certificates/1', 'obligations': certificates,
            'uninspected': len(pending)}
