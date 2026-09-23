"""Consumer boundary for stored IBL editions; never rewrites historical source.

Edition 1 remains executable through its explicit compatibility paths. It is
not a current-authoring answer or a current-model training target. This is a
qualification boundary, not a claim of semantic or runtime verification.
"""
import json
from collections import Counter

from ibl_edition import source_edition


def field(row, key, default=None):
    if isinstance(row, dict) or hasattr(row, 'keys'):
        return row[key] if key in row.keys() else default
    return getattr(row, key, default)


def exclusion_reason(row):
    code = field(row, 'ibl_code', '')
    if not isinstance(code, str) or not code.strip():
        return 'missing_source'
    try:
        edition = source_edition(code, field(row, 'edition'))
    except ValueError:
        return 'edition_conflict'
    if edition != 2:
        return 'legacy_source'
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
