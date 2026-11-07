"""검토 촉발 조건과 독립적인 목표 지적의 수명을 구분한다."""
import json

from supervision_store import digest


def review_findings(decision):
    """알 수 없는 형식은 원문을 보존한 재확인 대상으로 만든다."""
    rows = decision.get('findings')
    legacy = not isinstance(rows, list) or not rows
    if legacy:
        rows = [{'id': 'legacy', 'scope': 'unscoped',
                 'reason': decision.get('reason', ''),
                 'instruction': decision.get('instruction', ''),
                 'resolved_when': '', 'evidence_ids': decision.get('evidence_ids', [])}]
    result = []
    for index, raw in enumerate(rows):
        row = raw if isinstance(raw, dict) else {'instruction': str(raw)}
        valid = (isinstance(row.get('scope'), str) and row['scope'] in {'trigger', 'goal'}
                 and all(isinstance(row.get(k), str) and row[k].strip()
                         for k in ('reason', 'instruction'))
                 and isinstance(row.get('evidence_ids', []), list)
                 and all(isinstance(ref, str) for ref in row.get('evidence_ids', [])))
        result.append({
            'id': row.get('id') if isinstance(row.get('id'), str) else f'finding-{index + 1}',
            'scope': row['scope'] if valid else 'unscoped',
            'reason': str(row.get('reason', decision.get('reason', ''))),
            'instruction': str(row.get('instruction', '')),
            'resolved_when': str(row.get('resolved_when', '')),
            'evidence_ids': row.get('evidence_ids', []) if valid else [],
            'needs_recheck': not valid,
        })
    # 잘못된 구조가 상위 instruction에만 있는 교정을 지워 버리지 않게 한다.
    if not legacy and any(r['scope'] == 'unscoped' for r in result) and decision.get('instruction'):
        result.append({'id': 'unparsed-review', 'scope': 'unscoped',
                       'reason': str(decision.get('reason', '')),
                       'instruction': str(decision['instruction']), 'resolved_when': '',
                       'evidence_ids': [], 'needs_recheck': True})
    return result


def _evidence_status(controller, refs):
    if not refs:
        return 'unverified'
    try:
        for ref in refs:
            if controller.store.read_evidence(ref, limit=0)['integrity'] != 'verified':
                return 'unverified'
    except (OSError, ValueError, KeyError, TypeError):
        return 'unverified'
    return 'verified'


def refresh_notice(controller, notice):
    """코드는 참조/수명만 검사한다. 근거의 의미상 해결 여부를 대신 판정하지 않는다."""
    conditions = notice.get('conditions') or {}
    goal = digest(json.dumps(controller.framing, sort_keys=True, ensure_ascii=False))
    if controller.cancelled() or conditions.get('goal') != goal:
        controller.log('decision.stale', role='harness', notice_id=notice.get('id'),
                       reason='cancelled_or_goal_changed')
        return None
    trigger_valid = controller.conditions_valid(conditions)
    changed = notice.get('revision') != controller.exec_revision or not trigger_valid
    kept = []
    for row in notice['findings']:
        row = dict(row)
        row['evidence_status'] = _evidence_status(controller, row['evidence_ids'])
        if row['scope'] == 'trigger' and not trigger_valid:
            controller.log('review.finding_retired', role='harness', notice_id=notice['id'],
                           finding_id=row['id'], reason='trigger_resolved')
            continue
        row['needs_recheck'] = (row['needs_recheck'] or changed
                                or row['evidence_status'] != 'verified')
        kept.append(row)
    if not kept:
        controller.log('decision.stale', role='harness', notice_id=notice['id'],
                       reason='all_findings_retired', reviewed_revision=notice.get('revision'),
                       current_revision=controller.exec_revision)
        return None
    notice = {**notice, 'findings': kept, 'observed_state_changed': changed}
    lines = ['[검토 교정 — 사용자 목표·권한을 유지하고 다음 행동 전에 확인]']
    for row in kept:
        lines += [f"지적 {row['id']}: {row['reason']}"]
        if row['needs_recheck']:
            lines += ['상태 또는 근거 재확인 필요. 아래는 이전 관측의 교정 제안이다. '
                      '그대로 실행하지 말고 현재도 필요한지 확인하라. 종료된 작업을 중복 실행하지 마라.']
        lines += [f"교정: {row['instruction']}", f"해결 증거: {row['resolved_when'] or '현재 근거로 재확인'}",
                  f"근거 참조: {', '.join(row['evidence_ids']) or '미확인'}"]
    notice['instruction'] = '\n'.join(lines)
    return notice
