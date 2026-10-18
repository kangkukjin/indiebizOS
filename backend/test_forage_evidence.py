"""관측 → 증류/직접 note → 문서 → 재색인 → 범위 제한 대조의 계약."""
import copy
import hashlib
import json
import os
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import forage_memory as fm
import forage_doc as fd
import forage_evidence as fe
import source_observation as so
from distill_receipts import fingerprint


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, '_DB_PATH', str(tmp_path / 'forage.db'))
    monkeypatch.setattr(fd, 'DOC_DIR', str(tmp_path / 'memories'))
    monkeypatch.setattr(fm, '_place_order', lambda q: [])
    monkeypatch.setattr(fd, 'reconcile_lazy', lambda *a, **k: None)
    import pulse_db
    monkeypatch.setattr(pulse_db, 'CONSCIOUSNESS_DB_PATH', tmp_path / 'pulse.db')
    return tmp_path


def observe(path):
    before = so.file_state(path)
    raw = path.read_bytes()
    e = so.file_evidence(str(path), before, hashlib.sha256(raw).hexdigest(), {'complete': True})
    ref = so.publish(e, raw.decode())
    return {'receipt_id': ref}


def note(path, claim='금액 열은 천 원 단위이고 취소 항목을 포함한다.', **kw):
    return fm.note_map(body='mac', locus=str(path), kind='convention', claim=claim,
                       prior_class='semantic', provenance={'observation_refs': [observe(path)]}, **kw)


def row(ident):
    conn = fm._connect()
    try:
        return dict(conn.execute('SELECT * FROM forage_map WHERE id=?', (ident,)).fetchone())
    finally:
        conn.close()


def status(ident, mode='content', **kw):
    return fe.Checker(mode, **kw).status(row(ident))


def test_file_content_change_preserves_size_mtime_and_parent(env):
    p = env / 'orders.csv'; p.write_text('a,b\n1,2\n')
    ident = note(p)['id']
    old, parent = p.stat(), env.stat().st_mtime_ns
    assert status(ident)['state'] == 'unchanged'
    assert status(ident, 'metadata')['state'] == 'unknown'
    p.write_text('a,b\n1,3\n'); os.utime(p, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert env.stat().st_mtime_ns == parent
    assert status(ident)['state'] == 'changed'
    assert row(ident)['confidence'] == .7


def test_roundtrip_empty_index_edit_duplicate_delete_and_split(env):
    p = env / 'root' / 'child' / 'orders.csv'; p.parent.mkdir(parents=True); p.write_text('unit=1000')
    ident = note(p)['id']
    original = row(ident)
    doc = Path(fd.doc_path_for('mac', str(p)))
    text = doc.read_text()
    assert '## 근거' in text and fe.provenance(original['provenance'])['claim_ref'] in text
    conn = fm._connect(); conn.execute('DELETE FROM forage_map'); conn.commit(); conn.close()
    assert fd.sync_doc_to_db(str(doc))['success']
    restored = fd.parse_section(doc.read_text())[0]
    assert fe.provenance(restored['provenance']) == fe.provenance(original['provenance'])
    # Whitespace does not alter semantic binding.
    doc.write_text(text.replace('금액 열은', '금액   열은', 1)); assert fd.sync_doc_to_db(str(doc))['success']
    assert fd.parse_section(doc.read_text())[0]['provenance'] == restored['provenance']
    # Human semantic edit does not inherit an endorsement from old bytes.
    doc.write_text(text.replace('천 원 단위', '원 단위', 1)); assert fd.sync_doc_to_db(str(doc))['success']
    changed = fd.rows_for_doc('mac', fd.root_of_doc(str(doc)))[0]
    assert fe.Checker('content').status(changed)['state'] == 'unknown'
    # Duplicate IDs are rejected before mutating the index.
    line = next(l for l in text.splitlines() if l.startswith('- [convention]'))
    doc.write_text(text.replace(line, line + '\n' + line))
    before = fd.rows_for_doc('mac', fd.root_of_doc(str(doc)))
    assert not fd.sync_doc_to_db(str(doc))['success']
    assert fd.rows_for_doc('mac', fd.root_of_doc(str(doc))) == before
    doc.write_text(text); assert fd.sync_doc_to_db(str(doc))['success']
    fd.refresh_doc_for('mac', str(p.parent), own_node=True)
    moved = Path(fd.doc_path_for('mac', str(p)))
    assert moved != doc and fe.provenance(fd.parse_section(moved.read_text())[0]['provenance']) == fe.provenance(original['provenance'])
    fm.forget(entry_id=fd.rows_for_doc('mac', str(p.parent))[0]['id'])
    assert 'unit=1000' not in moved.read_text()
    assert fd.parse_section(moved.read_text()) == []


def test_forged_foreign_and_unrelated_refs_rejected(env, monkeypatch):
    p = env / 'a'; p.write_text('a')
    ref = observe(p)
    for refs in ([{'receipt_id': 'bogus'}], [ref]):
        target = p if refs[0]['receipt_id'] == 'bogus' else env / 'other'
        out = fm.note_map(body='mac', locus=str(target), kind='identity', claim='test', provenance={'observation_refs': refs})
        assert not out['success']
    monkeypatch.setattr(so, 'identity', lambda: ('member:other', 'pc'))
    with pytest.raises(ValueError, match='foreign'):
        so.resolve(ref['receipt_id'], locus=str(p))
    monkeypatch.setattr(so, 'identity', lambda: ('owner', 'other-body'))
    with pytest.raises(ValueError, match='foreign'):
        so.resolve(ref['receipt_id'], locus=str(p))


def test_untrusted_hash_is_plain_note_not_observation(env):
    p = env / 'never_read'
    out = fm.note_map(body='mac', locus=str(p), kind='identity', claim='사람 메모',
                      provenance={'evidence': {'items': [{'stable': True, 'complete': True}]}})
    assert out['success'] and status(out['id'])['state'] == 'unknown'
    assert fe.provenance(row(out['id'])['provenance'])['evidence']['items'] == []


def test_same_sentence_no_reinforce_new_observation_idempotent(env):
    p = env / 'unit'; p.write_text('천 원')
    ident = note(p)['id']; before = row(ident)
    plain = fm.note_map(body='mac', locus=str(p), kind='convention', claim=before['claim'])
    assert plain['action'] == 'same' and row(ident) == before
    ref = observe(p)
    kwargs = dict(body='mac', locus=str(p), kind='convention', claim=before['claim'],
                  prior_class='semantic', provenance={'observation_refs': [ref]}, candidate_key='candidate')
    assert fm.note_map(**kwargs)['action'] == 'reinforced'
    once = row(ident)
    fm.note_map(**kwargs)
    assert row(ident) == once
    assert len(fe.provenance(once['provenance'])['evidence']['items']) == 2


def test_single_file_meaning_does_not_inherit(env):
    p = env / 'file'; p.write_text('unit=1000')
    ident = note(p, generalizes=False)['id']
    assert ident in [r['id'] for r in fm.recall(locus=str(p), evidence_check='content')['map']]
    assert ident not in [r['id'] for r in fm.recall(locus=str(p / 'child'))['map'] if r['via'] == 'inherit']
    assert ident not in [r['id'] for r in fm.recall(locus=str(env / 'sibling'))['map']]


def test_listing_scope_filter_rename_add_delete_and_budget(env):
    root = env / 'files'; root.mkdir(); (root / 'a.csv').touch(); (root / 'ignore.txt').touch()
    before = so.file_state(root)
    e = so.listing_evidence(str(root), before, [{'path': str(root / 'a.csv')}], pattern='*.csv')
    ref = so.publish(e, 'a.csv')
    ident = fm.note_map(body='mac', locus=str(root), kind='identity', claim='CSV 자료 묶음',
                       provenance={'observation_refs': [{'receipt_id': ref}]})['id']
    assert status(ident)['state'] == 'unchanged'
    (root / 'ignore.txt').write_text('irrelevant')
    assert status(ident)['state'] == 'unchanged'
    (root / 'a.csv').rename(root / 'b.csv')
    assert status(ident)['state'] == 'changed'
    (root / 'b.csv').unlink(); assert status(ident)['state'] == 'changed'
    (root / 'a.csv').touch(); assert status(ident)['state'] == 'unchanged'
    (root / 'c.csv').touch(); assert status(ident)['state'] == 'changed'
    check = status(ident, limits={'entries': 0})
    assert check['state'] == 'unknown' and check['outcomes'][0]['reason'] == 'budget_exhausted'


def test_deep_listing_and_exclusions(env):
    root = env / 'tree'; root.mkdir(); (root / 'sub').mkdir(); (root / 'skip').mkdir()
    scope = {'depth': 2, 'complete': True, 'exclusions': ['skip*'], 'pattern': None}
    e = {'source': {'kind': 'directory', 'address': str(root), 'body': so.identity()[1], 'device_id': so.device_identity()},
         'scope': scope, 'stable': True, 'link_state': 'observed',
         'version': {'sha256': fe.Checker('content').listing(str(root), scope),
                     'method': 'listing_names_kinds', 'metadata': so.file_state(root)}}
    (root / 'skip' / 'x').touch()
    assert fe.Checker('content').check(e)['state'] == 'unchanged'
    (root / 'sub' / 'x').touch()
    assert fe.Checker('content').check(e)['state'] == 'changed'
    e['scope']['complete'] = False
    assert fe.Checker('content').check(e)['reason'] == 'incomplete_listing'


def test_unstable_permission_offline_missing_symlink(env, monkeypatch):
    p = env / 'file'; p.write_text('a'); ident = note(p)['id']
    e = fe.provenance(row(ident)['provenance'])['evidence']['items'][0]
    e['stable'] = False
    assert fe.Checker('content').check(e)['reason'] == 'unstable_observation'
    e['stable'] = True
    with monkeypatch.context() as m:
        m.setattr(fe, 'file_state', lambda p: (_ for _ in ()).throw(PermissionError()))
        assert fe.Checker('content').check(e)['reason'] == 'permission'
    with monkeypatch.context() as m:
        m.setattr(fm, '_mounted', lambda p: False)
        assert status(ident)['outcomes'][0]['reason'] == 'offline_volume'
    target = env / 'other'; target.write_text('a')
    link = env / 'link'; link.symlink_to(p)
    lid = note(link)['id']; link.unlink(); link.symlink_to(target)
    assert status(lid)['state'] == 'changed'
    p.unlink(); assert status(ident)['state'] == 'missing'


def test_only_returned_evidence_checked_and_shared_file_once(env, monkeypatch):
    p = env / 'file'; p.write_text('a'); a = note(p, '단위는 천 원')['id']
    b = note(p, '키는 고객 번호')['id']
    outside = env / 'outside'; outside.write_text('b'); note(outside, '다른 파일')
    calls, original = [], fe.Checker.file_hash
    def hashed(self, path, evidence):
        calls.append(path); return original(self, path, evidence)
    monkeypatch.setattr(fe.Checker, 'file_hash', hashed)
    result = fm.recall(locus=str(p), limit=1, evidence_check='content')
    assert {a, b} <= {r['id'] for r in result['map']}
    assert calls == [str(p)]
    monkeypatch.setitem(fe.CHECK_LIMITS, 'bytes', 0)
    result = fm.recall(locus=str(p), limit=1, evidence_check='content')
    assert len(result['map']) == 2 and all(r['evidence_status']['state'] == 'unknown' for r in result['map'])


def test_legacy_has_no_retroactive_fingerprint(env):
    p = env / 'legacy'; p.write_text('now')
    conn = fm._connect()
    conn.execute('INSERT INTO forage_map(body,locus,kind,claim,provenance,last_seen) VALUES (?,?,?,?,?,?)',
                 ('mac', str(p), 'identity', 'old', json.dumps({'observed': ['old observation']}), '2000-01-01'))
    conn.commit(); conn.close()
    fd.refresh_doc_for('mac', str(p))
    parsed = fd.parse_section(Path(fd.doc_path_for('mac', str(p))).read_text())[0]
    prov = fe.provenance(parsed['provenance'])
    assert prov['observed'] == ['old observation'] and prov['evidence']['link_state'] == 'legacy'
    assert not prov['evidence']['items']


def test_long_place_tail_is_searchable_without_evidence_json(env):
    p = env / 'data'; p.write_text('x')
    for i in range(8):
        note(p, ('처음 설명 ' * 30 if i < 7 else '고객번호 결합 기준 2025년 이후') + str(i))
    from forage_recall_store import ForageStore, place_ids
    store = ForageStore(); items = store.items()
    hits = store.lexical('고객번호 결합', items)
    assert str(p) in place_ids(hits)
    assert all(len(it.text) <= 700 and 'sha256' not in it.text for it in items)


@pytest.mark.parametrize('candidate_key', [None, 'pending'])
def test_doc_conflict_after_db_commit_is_recoverable_not_overwritten(env, monkeypatch, candidate_key):
    p = env / 'data'; p.write_text('a'); note(p)
    doc = Path(fd.doc_path_for('mac', str(p)))
    saved = doc.read_text()
    original = fm._doc_refresh
    def conflict(*a, **k):
        doc.write_text(saved + '\n사람의 동시 편집\n')
        return original(*a, **k)
    monkeypatch.setattr(fm, '_doc_refresh', conflict)
    kwargs = dict(body='mac', locus=str(p), kind='identity', claim='새 해석', candidate_key=candidate_key,
                  provenance={'observation_refs': [observe(p)]})
    with pytest.raises(ValueError, match='document_changed'):
        fm.note_map(**kwargs)
    assert '사람의 동시 편집' in doc.read_text()
    assert not fd.sync_doc_to_db(str(doc))['success']
    monkeypatch.setattr(fm, '_doc_refresh', original)
    doc.write_text(saved)
    assert fm.note_map(**kwargs)['success']
    assert '새 해석' in doc.read_text()


def test_paired_migration_and_backup_restore(env, monkeypatch):
    import importlib.util
    import shutil
    import sqlite3
    script = Path(__file__).resolve().parents[1] / 'scripts/migrate_forage_evidence.py'
    spec = importlib.util.spec_from_file_location('migration', script)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    p = env / 'old'; p.write_text('new bytes must not become old evidence')
    conn = fm._connect()
    conn.execute('INSERT INTO forage_map(body,locus,kind,claim,provenance,last_seen) VALUES (?,?,?,?,?,?)',
                 ('mac', str(p), 'identity', 'legacy', '{"observed":["old"]}', '2000-01-01'))
    conn.commit(); conn.close()
    backup = env / 'backups' / 'paired'
    result = migration.migrate(backup)
    assert result['claims'] == 1 and result['state'] == 'complete'
    assert status(1)['state'] == 'unknown'
    with pytest.raises(ValueError, match='already exists'):
        migration.migrate(backup)
    # Restore to a separate index: the paired old binary state is actually readable.
    restored = env / 'restored.db'
    src = sqlite3.connect(backup / 'forage_memory.db'); dst = sqlite3.connect(restored)
    src.backup(dst); dst.close(); src.close()
    conn = sqlite3.connect(restored)
    old = json.loads(conn.execute('SELECT provenance FROM forage_map').fetchone()[0]); conn.close()
    assert old == {'observed': ['old']}


def test_multiple_sources_priority_and_meaning_merge(env):
    a = env / 'a'; b = env / 'b'; a.write_text('a'); b.write_text('b')
    refs = [observe(a), observe(b)]
    ident = fm.note_map(body='mac', locus=str(env), kind='identity', claim='원본 묶음',
                        provenance={'observation_refs': refs})['id']
    b.unlink(); a.write_text('changed')
    st = status(ident)
    assert st['state'] == 'changed' and {o['state'] for o in st['outcomes']} == {'changed', 'missing'}
    other = fm.note_map(body='mac', locus=str(env), kind='identity', claim='옛 의미',
                       provenance={'observed': ['unversioned']})['id']
    out = fm.merge_entries(table='forage_map', keep_id=ident, drop_ids=[other], fields={'claim': '새 통합 의미'})
    assert out['success']
    assert len(fe.provenance(row(ident)['provenance'])['evidence']['items']) == 2
    assert 'reconfirmation_required' in [o['reason'] for o in status(ident)['outcomes']]


def test_large_source_budget_is_bounded(env):
    p = env / 'large'; p.write_bytes(b'x' * (fe.CHECK_LIMITS['bytes'] + 1))
    ident = note(p)['id']
    check = fe.Checker('content'); result = check.status(row(ident))
    assert result['state'] == 'unknown' and check.bytes <= fe.CHECK_LIMITS['bytes']
    assert result['outcomes'][0]['reason'] == 'budget_exhausted'


def test_default_listing_budget_stops_large_material(env):
    root = env / 'many'; root.mkdir()
    for i in range(fe.CHECK_LIMITS['entries'] + 1):
        (root / str(i)).touch()
    scope = {'depth': 1, 'complete': True, 'exclusions': []}
    checker = fe.Checker('content', limits={'seconds': 30})
    with pytest.raises(fe.BudgetExceeded):
        checker.listing(str(root), scope)
    assert checker.entries == fe.CHECK_LIMITS['entries']


def test_migration_keeps_gone_documents_archived(env):
    import importlib.util
    root = env / 'archived'; root.mkdir(); source = root / 'file'; source.write_text('x')
    note(source)
    fd.refresh_doc_for('mac', str(root), own_node=True)
    folded = fd.tombstone_node('mac', str(root))
    archived = Path(fd.DOC_DIR) / folded['archived'] / fd.DOC_NAME
    original = archived.read_bytes()
    other = env / 'live'; other.write_text('y'); note(other, '활성 메모')
    script = Path(__file__).resolve().parents[1] / 'scripts/migrate_forage_evidence.py'
    spec = importlib.util.spec_from_file_location('gone_migration', script)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    result = migration.migrate(env / 'paired-gone')
    assert result['state'] == 'complete' and result['claims'] == 2
    assert archived.read_bytes() == original
    assert not Path(fd.doc_path_at('mac', str(root))).exists()
    assert all(str(source) not in p.read_text() for p in Path(fd.DOC_DIR).rglob(fd.DOC_NAME)
               if fd.GONE_DIR not in p.relative_to(fd.DOC_DIR).parts)


def test_old_multiline_metadata_never_becomes_claim_content(env):
    p = env / 'legacy'; p.write_text('x')
    claim = '이 자료는 원본이다'
    legacy = '## 단언\n### ' + str(p) + '\n- [substrate] ' + claim + ' ‹0.70 · 2020-01-01 · first\nsecond · prune: legacy\nreason›\n'
    parsed = fd.parse_section(legacy)
    assert parsed[0]['claim'] == claim and parsed[0]['prune_reason'] == 'legacy reason'
    r = dict(body='mac', locus=str(p), kind='substrate', claim=claim, confidence=.7,
             provenance=json.dumps({'observed': ['first\nsecond ‹literal›']}), prune_reason='legacy\nreason')
    rendered = fd.render_section([r])
    assert len([l for l in rendered.splitlines() if l.startswith('- [substrate]')]) == 1
    restored = fd.parse_section(rendered)[0]
    assert restored['claim'] == claim
    assert fe.provenance(restored['provenance'])['observed'] == ['first\nsecond ‹literal›']
    with pytest.raises(ValueError, match='unclosed_claim_metadata'):
        fd.parse_section(legacy.replace('reason›', 'reason'))


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
