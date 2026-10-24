"""Memory references, never a second owner of executable definitions."""
import json
import sqlite3

import function_store as store
from ibl_edition import source_edition


def attach(name, source, intent, provenance=None, *, expected_revision=None, reason=''):
    provenance = dict(provenance or {})
    if not name:
        return provenance
    prior = provenance.get('function_ref')
    review = provenance.get('corpus_review') or {}
    state = review.get('decision') if review.get('decision') in ('hold', 'quarantine') else None
    if review.get('static_status') in ('invalid', 'failed'):
        state = state or 'invalid'
    ref = store.register_memory(name, source, intent, provenance, state=state,
                                expected_revision=expected_revision,
                                function_id=(prior or {}).get('function_id'), reason=reason)
    provenance['function_ref'] = ref
    return provenance


def lookup(db, name, edition=1):
    current = store.memory_reference(name, edition)
    if current is None:
        return None
    try:
        with db._get_connection() as conn:
            rows = conn.execute('SELECT * FROM ibl_examples WHERE alias=? ORDER BY updated_at DESC,id DESC', (name,)).fetchall()
        for item in rows:
            row = dict(item)
            from corpus_policy import callable_exclusion_reason
            if callable_exclusion_reason(row):
                continue
            if source_edition(row['ibl_code']) != edition:
                continue
            provenance = json.loads(row.get('provenance') or '{}')
            ref = provenance.get('function_ref')
            if not ref or ref.get('function_id') != current['function_ref']['function_id']:
                continue
            projection = store.project_memory(row)
            if projection.get('function_problem'):
                return None
            current = {**row, **projection}
            break
    except (OSError, ValueError, sqlite3.OperationalError):
        pass
    from ibl_signature_slot import signature_of
    current['signature'] = signature_of(current['ibl_code'])
    from capability_history import function_statistics
    current.update(function_statistics(current['function_ref']))
    return current


def project_rows(rows):
    result = []
    view = store.snapshot()
    for row in rows:
        row = store.project_memory(row, view=view)
        if not row.get('function_problem'):
            result.append(row)
    return result
