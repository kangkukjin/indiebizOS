"""Review eligibility for current source projections; history is stored separately."""
import json
from collections import Counter



def applicability_note(raw):
    """Shared compact applicability projection; private provenance stays in storage."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data.get('evidence_stale'):
            return ''  # Old applicability is evidence about the old definition only.
        condition = data.get('applicability')
        if isinstance(condition, str):
            return condition[:240] + ('…(조건 발췌)' if len(condition) > 240 else '')
    except (ValueError, TypeError, AttributeError):
        pass
    return ''


def route_note(raw):
    """가장 최근의 길 한 건을 회상용 한 줄로 — 참고한 것과 안 된 길(원인), 그리고 날짜.

    금지문이 아니라 그날의 사실이다. 날짜를 함께 보여 낡았는지는 읽는 쪽이 판단한다."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data.get('evidence_stale'):
            return ''
        route = (data.get('routes') or [])[-1]
        parts = []
        seen = [r.get('guide') or '·'.join(r.get('actions') or []) for r in route.get('consulted') or []]
        if any(seen):
            parts.append('참고: ' + ', '.join(s for s in seen if s))
        for row in route.get('failed') or []:
            label = '사용자가 바로잡음: ' if row.get('by') == 'user' else '안 된 길: '
            parts.append(label + '·'.join(row.get('actions') or []) + ' — ' + str(row.get('cause') or ''))
        if parts:
            text = ' / '.join(parts)
            return f"{route.get('at', '')} " + text[:260] + ('…' if len(text) > 260 else '')
    except (ValueError, TypeError, AttributeError, IndexError):
        pass
    return ''


def function_reference(raw):
    """Identity from the owner's projection, not a name or a second definition."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        ref = data.get('function_ref')
        if isinstance(ref, dict) and all(isinstance(ref.get(k), str) and ref[k]
                                         for k in ('scope_id', 'function_id', 'revision')):
            return {k: ref[k] for k in ('scope_id', 'function_id', 'revision')}
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def field(row, key, default=None):
    if isinstance(row, dict) or hasattr(row, 'keys'):
        return row[key] if key in row.keys() else default
    return getattr(row, key, default)


def exclusion_reason(row):
    code = field(row, 'ibl_code', '')
    if not isinstance(code, str) or not code.strip():
        return 'missing_source'
    return review_exclusion_reason(row)


def callable_exclusion_reason(row):
    """Historical source never becomes an executable recall candidate."""
    return exclusion_reason(row)


def review_exclusion_reason(row):
    provenance = field(row, 'provenance', {}) or {}
    try:
        if isinstance(provenance, str):
            provenance = json.loads(provenance)
        if not isinstance(provenance, dict):
            return 'invalid_provenance'
        review = provenance.get('corpus_review', {})
        if not isinstance(review, dict):
            return 'invalid_review'
        if review.get('decision') in {'hold', 'quarantine', 'compatibility'}:
            return 'review_' + review['decision']
        if review.get('static_status') in {'invalid', 'failed'}:
            return 'review_' + review['static_status']
    except (ValueError, TypeError):
        return 'invalid_provenance'
    return None


def current_examples(rows):
    """Same filter for local/cloud training and portable corpus exports."""
    accepted, rejected = [], Counter()
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            rejected[reason] += 1
        else:
            accepted.append(row)
    return accepted, dict(rejected)
