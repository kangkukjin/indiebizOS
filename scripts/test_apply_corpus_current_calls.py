"""Refuse stale review inputs and never invent execution evidence when seeding."""
import json
import sqlite3

import pytest

import apply_corpus_current_calls as bundle
from ibl_corpus_snapshot import sha


def fixture(root, monkeypatch):
    path = root / bundle.SOURCE
    path.parent.mkdir(parents=True)
    rows = [{'intent': '문맥이 필요한 질문', 'ibl_code': '[self:read]{path:"x"}'}] * 40
    path.write_text(json.dumps(rows))
    monkeypatch.setattr(bundle, 'REVIEWED_SHA', sha(path.read_bytes()))
    with sqlite3.connect(root / 'data/ibl_usage.db') as conn:
        conn.execute('CREATE TABLE ibl_examples(intent,ibl_code)')
    return path, rows


def test_review_preview_preserves_source_and_archived_state_is_idempotent(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    pending, decisions = bundle.quarantine_rows(tmp_path)
    assert pending and path.exists() and len(decisions) == 40
    assert {r['row_id'] for r in decisions} == set(range(40))
    archive = tmp_path / bundle.ARCHIVE
    archive.parent.mkdir()
    path.rename(archive)
    assert bundle.quarantine_rows(tmp_path) == (False, decisions)
    assert not list((tmp_path / 'data/training').glob('*.json'))


def test_changed_source_requires_new_review(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='지문'):
        bundle.quarantine_rows(tmp_path)


def test_database_duplicate_cannot_silently_remain_active(tmp_path, monkeypatch):
    _, rows = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / 'data/ibl_usage.db') as conn:
        conn.execute('INSERT INTO ibl_examples VALUES (?,?)', tuple(rows[0].values()))
    with pytest.raises(ValueError, match='운영 DB'):
        bundle.quarantine_rows(tmp_path)


def test_seed_is_bound_to_exact_callee_and_never_inherits_statistics():
    source = '$return=$목록'
    lesson = {'name': 'f', 'source_sha256': sha(source), 'source_edition': 1,
              'seed_intent': '빈 목록을 반환해줘', 'example': '#!ibl edition=2\nreturn [fn:f]{목록:[]}',
              'topic': '목록', 'returns': 'Record'}
    ex, = bundle.seed_examples([lesson], {'f': source})
    assert ex['alias'] == '' and 'success_count' not in ex
    assert ex['provenance']['runtime_success_claimed'] is False
    with pytest.raises(ValueError, match='바뀌었습니다'):
        bundle.seed_examples([lesson], {'f': source + '\n'})
