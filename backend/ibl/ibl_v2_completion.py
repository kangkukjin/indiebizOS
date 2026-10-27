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
        if (not isinstance(spec, dict) or set(spec) - {'id', 'predicate', 'sources', 'required', 'scope'}
                or not isinstance(spec.get('id'), str) or not spec['id'] or spec['id'] in names
                or not isinstance(spec.get('predicate'), str)
                or type(spec.get('required', True)) is not bool):
            raise Fault('COMPLETION_CONTRACT', '의무는 고유 id·순수 predicate·sources를 가집니다.', kind='compile')
        scope = spec.get('scope', [])
        if (not isinstance(scope, list) or len(scope) > 64
                or any(not isinstance(k, str) and type(k) is not int for k in scope)):
            raise Fault('COMPLETION_CONTRACT', 'scope는 반환값 안의 필드/인덱스 경로입니다.', kind='compile')
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


def condition_hash(spec):
    # Local id/required/output location are placement policy. The proposition
    # and permitted sources remain identical when a certified part is moved.
    return digest({'predicate': spec['predicate'], 'sources': spec['sources']})


def reference_binding(runtime, value, note):
    """Bind verified reference coordinates; business JSON cannot mint origins."""
    from common.expression_eval import Binding
    if 'refs' not in note:
        eid = runtime.event(runtime.plan.root, 'input_ref', origin=note,
                            incomplete=(note.get('evidence') or {}).get('incomplete') is True)
        path = tuple(note.get('path', ()))
        if path == ('value_wire',):
            path = ('value',)
        certificates = []
        evidence = note.get('evidence') or {}
        if evidence.get('execution_success') is True:
            for cert in (evidence.get('component_certificates') or {}).get('obligations', []):
                origin = ('value', *cert.get('scope', []))
                if origin[:len(path)] == path and cert.get('status') == 'satisfied':
                    relative = origin[len(path):]
                    try:
                        selected = value
                        for key in relative:
                            selected = selected[key]
                        if digest(pack(selected)) == cert.get('value_hash'):
                            certificates.append({**cert, 'scope': list(relative)})
                    except (KeyError, IndexError, TypeError, Fault):
                        pass
        return Binding(value, frozenset({eid}), origins=((eid, path),), certificates=tuple(certificates))
    trie = {}
    for ref in note['refs']:
        branch = trie
        for key in ref.get('at', []):
            branch = branch.setdefault(key, {})
        branch[None] = ref

    def bind(item, branch):
        if None in branch:
            return reference_binding(runtime, item, branch[None])
        if isinstance(item, dict):
            return Binding.record({k: bind(v, branch[k]) if k in branch else Binding(v) for k, v in item.items()})
        if isinstance(item, list):
            return Binding.sequence([bind(v, branch[k]) if k in branch else Binding(v) for k, v in enumerate(item)])
        return Binding(item)

    return bind(value, trie)


class PredicateEvaluator:
    """Use the existing pure evaluator with the caller's budget and provenance."""
    @staticmethod
    def run(runtime, source, binding):
        from common.expression_eval import ValueEvaluator
        from ibl_v2_compile import compile_program
        plan = compile_program('return ' + source, inputs={'value': binding.value})
        if plan.issues or plan.effects - {'pure'}:
            raise Fault('COMPLETION_PREDICATE', '완료 판정식을 적용할 수 없습니다.', kind='protocol')

        class Evaluator(ValueEvaluator):
            def check(self):
                runtime.check()

            expression_tick = check

            def expression_row(self):
                runtime.budget.tick(row=True)

        node = plan.root.data['statements'][0].data['value']
        return Evaluator().eval(node, {'value': binding})


def undetermined(specs, error):
    """Completion infrastructure failures never erase an execution receipt."""
    return {'protocol': 'ibl-completion/1', 'status': 'undetermined',
            'diagnostic': {'code': getattr(error, 'code', 'COMPLETION_EVALUATION'), 'message': str(error)},
            'obligations': [{'id': s['id'], 'required': s.get('required', True),
                             'status': 'undetermined', 'reason': 'evaluation_failed',
                             'condition_hash': condition_hash(s), 'value_hash': None, 'evidence_refs': []}
                            for s in specs]}


def evaluate(runtime, result, success, *, specs=None):
    # An unresolved mutation is global even when its output was discarded.
    unsafe = any(e.get('kind') == 'assertion' and e.get('passed') is False for e in runtime.trace) or any(e['kind'] == 'tool_failure' and any(
        p.get('kind') == 'invoke' and p['id'] in e['parents'] and
        set(p.get('effects', [])) - {'pure', 'read_external', 'model'}
        for p in runtime.trace) for e in runtime.trace)
    obligations, selected = [], set()
    for spec in runtime.completion if specs is None else specs:
        status, reason, value_hash, sources = 'undetermined', 'execution_failed', None, []
        diagnostic = None
        try:
            if success and result is not None:
                scoped = result
                for key in spec.get('scope', []):
                    scoped = scoped.select(key)
                value_hash = digest(pack(scoped.value))
                checked = PredicateEvaluator.run(runtime, spec['predicate'], scoped)
                # An explicit scope covers that whole component. Otherwise the
                # predicate's actual value/control reads define its dependencies.
                roots = scoped.evidence if 'scope' in spec else checked.evidence or scoped.evidence
                events = selected_events(runtime.trace, roots)
                selected.update(e['id'] for e in events)
                failed = {p for e in events if e['kind'] == 'tool_failure' for p in e['parents']}
                sources = [e['id'] for e in events if e['kind'] == 'invoke' and e['id'] not in failed
                           and any(e.get('action') == s['action'] and all(
                               e.get('targets', {}).get(k) == v for k, v in s['targets'].items()) for s in spec['sources'])]
                inherited = []
                by_id = {event['id']: event for event in events}
                for origin_id, origin_path in scoped.origins:
                    event = by_id.get(origin_id)
                    if not event or event['kind'] != 'input_ref':
                        continue
                    evidence = (event.get('origin') or {}).get('evidence') or {}
                    old = evidence.get('completion') or {}
                    certificates = (evidence.get('component_certificates') or {}).get('obligations', [])
                    if evidence.get('execution_success') is True and any(
                            o.get('status') == 'satisfied' and o.get('condition_hash') == condition_hash(spec)
                            and origin_path == ('value', *o.get('scope', []))
                            and o.get('value_hash') == value_hash for o in [*old.get('obligations', []), *certificates]):
                        inherited.append(event['id'])
                sources.extend(inherited)
                incomplete = any(e.get('incomplete') and e['id'] not in inherited for e in events)
                reason = 'unsafe_effect' if unsafe else 'incomplete_source' if incomplete else 'missing_evidence'
                if sources and not incomplete and not unsafe and type(checked.value) is bool:
                    status, reason = ('satisfied' if checked.value else 'unsatisfied'), 'predicate'
        except Exception as exc:
            reason = 'evaluation_failed'
            diagnostic = {'code': getattr(exc, 'code', 'COMPLETION_EVALUATION'), 'message': str(exc)}
        obligations.append({'id': spec['id'], 'required': spec.get('required', True),
                            'status': status, 'reason': reason, 'condition_hash': condition_hash(spec),
                            'scope': spec.get('scope', []), 'value_hash': value_hash,
                            'evidence_refs': sources, **({'diagnostic': diagnostic} if diagnostic else {})})
    required = [o for o in obligations if o['required']]
    status = ('satisfied' if success and required and all(o['status'] == 'satisfied' for o in required)
              else 'unsatisfied' if any(o['status'] == 'unsatisfied' for o in required) else 'undetermined')
    return {'protocol': 'ibl-completion/1', 'status': status, 'obligations': obligations,
            'selected_evidence': sorted(selected), 'audit_events': len(runtime.trace),
            'plan_hash': runtime.plan.fingerprint}
