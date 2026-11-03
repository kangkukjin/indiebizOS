"""Adapt existing failure contracts to the execution-local recovery projection."""
import json

from recovery_projection import RecoveryProjection, requires_attention
from workflow_verdict import is_error_result


def observe(recovery, key, name, payload, result, ref, *, error=False, unknown=False):
    from logging_utils import mask_secret_data
    from supervisor_review import ibl_shape_repair_key, ibl_error_render_repair_key
    result = mask_secret_data(result)
    ref = {k: v for k, v in ref.items() if k in {'id', 'path', 'availability', 'call_index'}}
    raw = result
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    raw = raw if isinstance(raw, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    pre = raw.get('executed') is False
    repair_key = (ibl_shape_repair_key(name, payload) or ibl_error_render_repair_key(name, payload))
    failed = bool(error or is_error_result(result))
    facts = []
    if unknown or failed:
        facts.append({'signal': 'result_missing' if unknown else 'failure',
                      'path': [], 'pre_execution': pre})
    summary = raw.get('evidence_summary')
    if summary is None and isinstance(raw.get('evidence'), list) and str(name).endswith('execute_ibl'):
        from model_result_view import execution_evidence_summary
        summary = execution_evidence_summary(raw)
    summary = summary if isinstance(summary, dict) else {}
    outcomes = summary.get('operation_outcomes', raw.get('operation_outcomes', []))
    if isinstance(outcomes, list):
        for index, row in enumerate(outcomes[:256]):
            if isinstance(row, dict) and row.get('status') in {'failed', 'partial', 'unknown', 'interrupted'}:
                facts.append({'signal': 'failure', 'path': ['operation_outcomes', index],
                              'operation_ref': row.get('id'), 'status': row['status']})
        if len(outcomes) > 256:
            facts.append({'signal': 'unobserved_range', 'path': ['operation_outcomes', 'omitted'],
                          'omitted': len(outcomes) - 256})
    for field in ('source_failures', 'tool_failures'):
        count = summary.get(field)
        if type(count) is int and count > 0:
            facts.append({'signal': 'failure', 'path': ['evidence_summary', field], 'count': count})
    changed = recovery.observe(key, facts, ref, name=name, repair_key=repair_key)
    if not facts and not pre and raw.get('mode') != 'check' and raw.get('success') is True:
        recovery.resolve_pre_execution(repair_key, ref, operation=True)
    return changed


def configure(situation, recovery=None):
    if recovery is not None:
        recovery.restore(situation.recovery.snapshot())
        situation.recovery = recovery
    situation.recovery.changed = situation.publish_recovery
    situation.on_recovery = lambda key, name, payload, result, ref, error, unknown: observe(
        situation.recovery, key, name, payload, result, ref, error=error, unknown=unknown)


def view(calls, supervisor=None, *, final=False):
    from execution_turn import current
    binding = current()
    situation = getattr(binding, 'situation', None)
    authoritative = None
    if situation is not None and situation.on_recovery:
        authoritative = situation.recovery_view()
    recovery = getattr(supervisor, 'recovery', None)
    if authoritative is None and recovery is not None and recovery.view():
        authoritative = recovery.view()
    fallback = RecoveryProjection('fallback', getattr(binding, 'task', 'standalone'))
    for index, call in enumerate(calls):
        missing = call.get('_result_received') is False
        if authoritative is not None and not (missing and final):
            continue
        if missing and not final:
            continue
        observe(fallback, call.get('id') or f'call:{index}', call.get('name', ''), call.get('input'),
                call.get('result'), {'call_index': index, 'id': call.get('result_ref')},
                error=bool(call.get('is_error')), unknown=missing or bool(call.get('transport_error')))
    return (authoritative or []) + fallback.view()


def assess(controller, decision, expected_goal):
    from supervision_store import digest
    accepted_revisions = {}
    current_goal = digest(json.dumps(controller.framing, sort_keys=True, ensure_ascii=False))
    if controller.cancelled() or current_goal != expected_goal:
        return accepted_revisions
    decisions = decision.get('incident_assessments')
    if not isinstance(decisions, list):
        return accepted_revisions
    for item in decisions[:64]:
        valid = set()
        subjects = []
        if isinstance(item, dict) and isinstance(item.get('basis_refs'), list):
            for ref in item['basis_refs'][:32]:
                if not isinstance(ref, str):
                    continue
                try:
                    page = controller.store.read_evidence(ref, limit=None)
                    if page['integrity'] == 'verified':
                        valid.add(ref)
                        try:
                            snapshot = json.loads(page['text'])
                        except (TypeError, ValueError):
                            snapshot = None
                        if isinstance(snapshot, dict) and isinstance(snapshot.get('observations'), list):
                            for record in snapshot['observations']:
                                row = record.get('latest', {}) if isinstance(record, dict) else {}
                                if row.get('basis') == 'observed' and row.get('subject_revision') is not None:
                                    subjects.append({'subject': row['subject'], 'revision': row['subject_revision']})
                except (OSError, ValueError, KeyError, TypeError):
                    pass
        if controller.cancelled() or digest(json.dumps(controller.framing, sort_keys=True, ensure_ascii=False)) != expected_goal:
            return accepted_revisions
        accepted = controller.recovery.assess(item, actor=controller.supervisor_id,
                                             valid_refs=valid, subjects=subjects)
        if accepted and subjects:
            from execution_situation import current as current_situation
            situation = current_situation(controller.owner, controller.task)
            if situation:
                for record in situation.snapshot()['observations']:
                    row = record['latest']
                    if row['basis'] == 'observed' and row.get('subject_revision') is not None:
                        controller.recovery.invalidate_subject(row['subject'], row['subject_revision'])
        controller.log('recovery.assessment', accepted=accepted,
                       incident_ref=item.get('incident_ref') if isinstance(item, dict) else None)
        if accepted and item['disposition'] in {'continue', 'unknown'}:
            accepted_revisions[item['incident_ref']] = item['incident_revision'] + 1
    return accepted_revisions


def pending(rows):
    return [row for row in rows if requires_attention(row)]
