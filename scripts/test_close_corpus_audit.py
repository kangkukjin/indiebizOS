import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import close_corpus_audit as audit


def setup_case(tmp_path, monkeypatch, code='[old:action]{}', edition=1):
    row = {'origin': 'data/ibl_usage.db:ibl_examples', 'row_id': 1, 'role': 'learning',
           'intent': 'fixture', 'ibl_code': code}
    static = {**{k: row[k] for k in ('origin', 'row_id', 'role')}, 'edition': edition,
              'code_sha256': audit.sha(code), 'current_check': {'status': 'invalid',
              'issues': [{'code': 'UNSUPPORTED_ADAPTER'}]}, 'risk_tags': [], 'missing_functions': []}
    (tmp_path / 'audit').mkdir()
    (tmp_path / 'audit/rows.jsonl').write_text(json.dumps(static)+'\n')
    (tmp_path / 'data/idioms').mkdir(parents=True)
    (tmp_path / 'data/idioms/current_call_lessons.json').write_text('{"idioms":[]}')
    priority = tmp_path / 'priority.jsonl'; priority.write_text('')
    probes = tmp_path / 'probes.json'; probes.write_text('{"cases":[]}')
    monkeypatch.setattr(audit, 'rows_from_snapshot', lambda _: [row])
    return row, priority, probes


def test_rejection_has_a_disposition_without_claiming_semantics(tmp_path, monkeypatch):
    _, priority, probes = setup_case(tmp_path, monkeypatch)
    report = audit.reconcile(tmp_path, [], priority, probes)
    assert report['unclassified'] == 0 and report['eligible'] == 0
    assert report['semantic_review'] == {'not_evaluated_after_static_rejection': 1}
    assert report['all_rows_semantically_verified'] is False


def test_current_header_without_review_cannot_close_as_qualified(tmp_path, monkeypatch):
    _, priority, probes = setup_case(tmp_path, monkeypatch, '#!ibl edition=2\nreturn 1', 2)
    with pytest.raises(ValueError, match='Unreviewed current source'):
        audit.reconcile(tmp_path, [], priority, probes)


def test_changed_intent_refuses_prior_review(tmp_path, monkeypatch):
    row, priority, probes = setup_case(tmp_path, monkeypatch)
    review = tmp_path / 'review.json'
    review.write_text(json.dumps({'rows': [{**row, 'decision': 'hold',
        'before_code': row['ibl_code'], 'intent_sha256': audit.sha('another intent')}]}))
    with pytest.raises(ValueError, match='Review/live conflict'):
        audit.reconcile(tmp_path, [review], priority, probes)
