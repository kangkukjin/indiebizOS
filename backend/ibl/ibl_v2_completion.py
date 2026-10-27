"""Explicit deterministic completion obligations, separate from audit history.

Predicates run in the existing pure value core. Source identities come from the
runtime evidence graph, never flags in business JSON. Legacy calls stay conservative.
"""
from ibl_v2_ir import Fault, digest, pack


def validate(specs):
    if specs is None or specs == []:
        return []
    if not isinstance(specs, list) or not 1 <= len(specs) <= 32:
        raise Fault('COMPLETION_CONTRACT', 'completion은 1~32개의 의무 목록입니다.', kind='compile')
    names = set()
    from ibl_v2_compile import compile_program
    from ibl_v2_types import UNKNOWN, BOOL, compatible
    for spec in specs:
        if (not isinstance(spec, dict) or set(spec) - {'id', 'predicate', 'sources', 'required'}
                or not isinstance(spec.get('id'), str) or not spec['id'] or spec['id'] in names
                or not isinstance(spec.get('predicate'), str)
                or type(spec.get('required', True)) is not bool):
            raise Fault('COMPLETION_CONTRACT', '의무는 고유 id·순수 predicate·sources를 가집니다.', kind='compile')
        names.add(spec['id'])
        sources = spec.get('sources')
        if not isinstance(sources, list) or not sources:
            raise Fault('COMPLETION_CONTRACT', '의무에는 허용하는 원천 action·targets가 필요합니다.', kind='compile')
        for source in sources:
            if (not isinstance(source, dict) or set(source) != {'action', 'targets'}
                    or not isinstance(source['action'], str) or not isinstance(source['targets'], dict)
                    or any(not isinstance(v, str) for v in source['targets'].values())):
                raise Fault('COMPLETION_CONTRACT', '원천은 action과 대상/판본 targets Record입니다.', kind='compile')
        plan = compile_program('return ' + spec['predicate'], input_types={'value': UNKNOWN})
        if plan.issues or plan.effects - {'pure'} or not compatible(plan.result_type, BOOL):
            raise Fault('COMPLETION_CONTRACT', '완료 판정식은 $value만 받는 순수 Bool 식이어야 합니다.', kind='compile')
    return specs


def selected_events(trace, roots):
    by_id = {e['id']: e for e in trace}
    pending, selected = list(roots), set()
    while pending:
        eid = pending.pop()
        if eid in selected or eid not in by_id:
            continue
        event = by_id[eid]
        if event['kind'] == 'recovered':
            continue
        selected.add(eid)
        pending.extend(event.get('selected_parents', event['parents']))
    return [by_id[e] for e in sorted(selected)]


def evaluate(runtime, result, success):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    events = selected_events(runtime.trace, result.evidence) if result else []
    failed_invokes = {parent for e in events if e['kind'] == 'tool_failure' for parent in e['parents']}
    # Any unresolved mutation still blocks completion even if its failed branch
    # was discarded. A source fallback cannot prove that mutation's outcome.
    unsafe = any(e.get('kind') == 'assertion' and e.get('passed') is False for e in runtime.trace) or any(e['kind'] == 'tool_failure' and any(
        p.get('kind') == 'invoke' and p['id'] in e['parents'] and
        set(p.get('effects', [])) - {'pure', 'read_external', 'model'}
        for p in runtime.trace) for e in runtime.trace)
    obligations = []
    for spec in runtime.completion:
        sources = [e['id'] for e in events if e['kind'] == 'invoke' and e['id'] not in failed_invokes
                   and any(e.get('action') == s['action'] and all(
                       e.get('targets', {}).get(k) == v for k, v in s['targets'].items()) for s in spec['sources'])]
        inherited = []
        for event in events:
            if event['kind'] != 'input_ref':
                continue
            evidence = (event.get('origin') or {}).get('evidence') or {}
            old = evidence.get('completion') or {}
            if evidence.get('execution_success') is True and any(
                    o.get('status') == 'satisfied' and o.get('condition_hash') == digest(spec)
                    and o.get('value_hash') == digest(pack(result.value))
                    for o in old.get('obligations', [])):
                inherited.append(event['id'])
        sources.extend(inherited)
        incomplete = any(e.get('incomplete') and e['id'] not in inherited for e in events)
        status, reason = 'undetermined', 'missing_evidence'
        if success and sources and not incomplete and not unsafe:
            plan = compile_program('return ' + spec['predicate'], inputs={'value': result.value})
            if not plan.issues and not plan.effects - {'pure'}:
                checked = Runtime(plan, {'value': result.value}, budget=runtime.budget,
                                  cancel_check=runtime.cancel_check).run()
                if checked.get('success') and type(checked.get('value')) is bool:
                    status = 'satisfied' if checked['value'] else 'unsatisfied'
                    reason = 'predicate'
        obligations.append({'id': spec['id'], 'required': spec.get('required', True),
                            'status': status, 'reason': reason, 'condition_hash': digest(spec),
                            'value_hash': digest(pack(result.value)) if result else None,
                            'evidence_refs': sources})
    required = [o for o in obligations if o['required']]
    status = ('satisfied' if success and required and all(o['status'] == 'satisfied' for o in required)
              else 'unsatisfied' if any(o['status'] == 'unsatisfied' for o in required) else 'undetermined')
    return {'protocol': 'ibl-completion/1', 'status': status, 'obligations': obligations,
            'selected_evidence': [e['id'] for e in events], 'audit_events': len(runtime.trace),
            'plan_hash': runtime.plan.fingerprint}
