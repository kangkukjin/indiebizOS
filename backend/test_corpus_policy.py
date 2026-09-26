"""Old answers stay available as history, never as current authoring code."""
import sqlite3
import xml.etree.ElementTree as ET

import boot_paths  # noqa: F401
import pytest

from corpus_policy import current_examples, exclusion_reason


NEW = '#!ibl edition=2\nreturn [self:time]{}'


@pytest.mark.parametrize('change,reason', [
    ({'ibl_code': '[self:time]'}, 'legacy_source'),
    ({'edition': 1}, 'edition_conflict'),
    ({'ibl_code': ''}, 'missing_source'),
    ({'provenance': '[]'}, 'invalid_provenance'),
    ({'provenance': '{'}, 'invalid_provenance'),
    ({'provenance': {'corpus_review': {'decision': 'hold'}}}, 'review_hold'),
    ({'provenance': {'corpus_review': {'static_status': 'invalid'}}}, 'review_invalid'),
])
def test_exclusions_are_not_converted_to_passes(change, reason):
    row = {'intent': '현재 시각', 'ibl_code': NEW, **change}
    assert exclusion_reason(row) == reason
    assert current_examples([row]) == ([], {reason: 1})


def test_unknown_adapter_is_distinct_from_invalid_and_keeps_provenance():
    row = {'ibl_code': NEW, 'provenance': {'corpus_review': {
        'static_status': 'incomplete', 'fixture_verified': True, 'runtime_success_claimed': False}}}
    assert current_examples([row]) == ([row], {})


def test_legacy_reference_is_retrievable_but_neither_executable_nor_quoted():
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG, _top_for_execution
    old = UsageExample(987, '시각', '[self:time]', 'self', 'single', 1, .98, 'fixture', -1)
    new = UsageExample(988, '시각', NEW, 'self', 'single', 1, .98, 'fixture', -1)
    root = ET.fromstring(IBLUsageRAG._format_references(None, [old, new]))
    before, after = root.findall('ref')
    assert '[self:time]' not in before.text
    assert '#987' in before.text and before.attrib['authoring_excluded'] == 'legacy_source'
    # Current edition: a single statement is quoted inline and is the reflex candidate.
    # Only the explicit-expansion policy (length / several statements) can still hide it — not the edition itself
    # (2026-09-26: edition-based hiding + legacy exclusion together left zero reflex candidates).
    assert 'authoring_excluded' not in after.attrib and 'body_omitted' not in after.attrib
    assert 'return [self:time]{}' in after.text
    assert _top_for_execution([old]) == (.80, '')
    assert _top_for_execution([new]) == (.98, NEW)


def test_weekly_audit_routes_editions_and_distinguishes_unknown(tmp_path, monkeypatch):
    import corpus_vocab_audit as audit
    import ibl_v2_adapters
    import ibl_v2_store
    db = tmp_path / 'usage.db'
    nodes = tmp_path / 'nodes.yaml'
    nodes.write_text('nodes: {self: {actions: {time: {}}}}')
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE ibl_examples(id,intent,ibl_code,alias,provenance)')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?)', [
            (1, 'old', '[self:time]', '', '{}'),
            (2, 'valid', '#!ibl edition=2\nreturn [1,"007"]', '', '{}'),
            (3, 'invalid', '#!ibl edition=2\nreturn $missing', '', '{}'),
            (4, 'boundary', NEW, '', '{}'),
            (5, 'local definition', '[def:local]{[self:time]} ; [fn:local]{}', '', '{}'),
        ])
    contract = {'version': 1, 'params': {}, 'required': [], 'result': 'Record',
                'effects': ['unknown'], 'compatibility': 'legacy-envelope/1',
                'adapter': {'protocol': 'legacy-envelope', 'value_path': ''}}
    def forbidden(*a, **k):
        raise AssertionError('Weekly audit must not execute')
    monkeypatch.setattr(audit, '_DB_PATH', db)
    monkeypatch.setattr(audit, '_NODES_PATH', nodes)
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda: {
        'self:time': ibl_v2_adapters.Adapter(contract, forbidden)})
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    result = audit.audit_corpus_vocab()
    assert result['total'] == 5 and result['dead'] == result['unparsable'] == 0
    assert result['current'] == {'valid': 1, 'incomplete': 1, 'invalid': 1, 'failed': 0}
    assert result['authoring_excluded'] == 2
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda: (_ for _ in ()).throw(OSError('broken')))
    assert audit.audit_corpus_vocab()['current']['failed'] == 3


def test_name_recall_resolves_native_version_and_drops_deleted_names():
    from types import SimpleNamespace
    from ibl_usage_rag import _current_phrase_rows
    old = SimpleNamespace(alias='same', ibl_code='old', score=.9,
                          success_rate=1, avg_ms=12, avg_tokens=50)
    gone = SimpleNamespace(alias='deleted', score=.99)
    current = {'id': 2, 'alias': 'same', 'ibl_code': NEW, 'returns': 'Record',
               'success_count': 0, 'fail_count': 0}
    class DB:
        def find_phrase_by_alias(self, name, edition=1):
            return current if (name, edition) == ('same', 2) else None
    hits = _current_phrase_rows(DB(), [old, old, gone])
    assert len(hits) == 1 and hits[0].ibl_code == NEW and hits[0].id == 2
    assert hits[0].success_rate == hits[0].avg_ms == hits[0].avg_tokens == -1
    assert old.ibl_code == 'old' and old.success_rate == 1


def test_tree_current_name_prefers_native_but_keeps_legacy_call_envelope(tmp_path):
    import hippo_tree
    db = tmp_path / 'names.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE ibl_examples(id,alias,ibl_code,updated_at)')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?)', [
            (1, 'same', '[self:time]', '2026-09-24'),
            (2, 'same', NEW, '2026-09-23')])
    old = {'id': 1, 'alias': 'same', 'ibl_code': '[self:time]'}
    groups = hippo_tree._current_names([[old], [old]], str(db))
    assert groups[0][0]['id'] == 2 and groups[1] == []
    assert hippo_tree.phrase_call_line('old', '[self:time]', 'prose').endswith('→ Record')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
