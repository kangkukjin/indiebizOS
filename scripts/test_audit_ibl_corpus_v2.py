"""Audit safety and classification: no tool effects, no silent missing rows."""
import json
import sqlite3

import pytest
from audit_ibl_corpus_v2 import (
    Adapter, audit, dependency_closure, forbidden, legacy_check,
    risks, rows_from_snapshot, static_check,
)
from ibl_corpus_snapshot import connect, dump, sha


def test_real_compiler_distinguishes_valid_invalid_incomplete():
    assert static_check('return 1', {}, {})['status'] == 'valid'
    assert static_check('return $missing', {}, {})['status'] == 'invalid'
    registry = {'test:read': Adapter({'version': 1, 'params': {}, 'result': 'Unknown',
                                    'effects': ['unknown'], 'compatibility': 'test'}, forbidden)}
    assert static_check('[test:read]{}', registry, {})['status'] == 'incomplete'


def test_audit_never_executes_write():
    registry = {'test:write': Adapter({'version': 1, 'params': {}, 'result': 'Record',
                                     'effects': ['write_external']}, forbidden)}
    report = static_check('[test:write]{}', registry, {})
    assert report['status'] == 'valid'
    assert report['effects'] == ['write_external']


def test_old_function_body_inputs_are_not_false_unbound():
    checked = static_check('$return = $목록', {}, {}, '옛함수')
    assert 'UNBOUND' not in {i['code'] for i in checked['issues']}
    assert checked['context'] == 'legacy_function_body_with_declared_free_inputs'
    assert 'legacy_return' in risks('$return = $목록')


def test_current_definition_uses_own_signature():
    code = '#!ibl edition=2\n[def:이름]($목록){return $목록}'
    assert static_check(code, {}, {}, '이름')['status'] == 'valid'


def test_alias_and_definition_must_match():
    code = '#!ibl edition=2\n[def:actual](){return 1}'
    result = static_check(code, {}, {}, 'wrong')
    assert result['status'] == 'invalid'
    assert result['issues'][0]['code'] == 'LIBRARY_NAME'


def test_explicit_edition_function_without_header_is_not_legacy_body():
    result = static_check('[def:f]($x){return $x}', {}, {}, 'f', edition=2)
    assert result['status'] == 'valid'
    assert result['context'] == 'stored_program'


def test_plain_strings_do_not_add_action_dependencies_or_parallel_risk():
    assert 'parallel' not in risks('return "[self:write]{} & [self:write]{}"')
    assert 'parallel' in risks('return 1 & 2')


def test_transitive_dependency_cycles_terminate():
    graph = {'fn:a': ['fn:b'], 'fn:b': ['fn:a', 'self:read']}
    assert dependency_closure(['fn:a'], graph) == ['fn:a', 'fn:b', 'self:read']


def test_legacy_parse_errors_are_not_discarded():
    assert legacy_check('[self:read]{path:') ['status'] == 'invalid'


def test_database_reader_is_read_only(tmp_path):
    p = tmp_path / 'test.db'
    with sqlite3.connect(p) as c:
        c.execute('CREATE TABLE t (id INTEGER)')
    with connect(p) as c, pytest.raises(sqlite3.OperationalError):
        c.execute('INSERT INTO t VALUES (1)')


def test_snapshot_tampering_is_rejected_before_parsing(tmp_path):
    (tmp_path / 'x').write_text('changed')
    dump(tmp_path / 'manifest.json', {'files': [{'path': 'x', 'sha256': sha('old')}], 'databases': []})
    with pytest.raises(ValueError, match='Snapshot changed'):
        audit(tmp_path)


def test_bad_training_rows_remain_in_population(tmp_path):
    data = tmp_path / 'data'
    (data / 'training').mkdir(parents=True)
    with sqlite3.connect(data / 'ibl_usage.db') as c:
        c.execute('CREATE TABLE ibl_examples(id INTEGER, ibl_code TEXT)')
    with sqlite3.connect(data / 'world_pulse.db') as c:
        c.execute('CREATE TABLE ibl_code_corpus(code_sha256 TEXT, code TEXT)')
    dump(data / 'training/test.json', [None, {'intent': 'missing'}, {'ibl_code': 'return 1'}])
    rows = rows_from_snapshot(tmp_path)
    assert len(rows) == 3
    assert rows[0]['invalid_row_type'] == 'NoneType'
    assert [r['row_id'] for r in rows] == [0, 1, 2]


def test_compiler_infrastructure_failure_is_not_a_syntax_verdict(monkeypatch):
    import audit_ibl_corpus_v2 as module
    def broken(*args, **kwargs):
        raise OSError('fixture missing')
    monkeypatch.setattr(module, 'compile_program', broken)
    result = static_check('return 1', {}, {})
    assert result['status'] == 'failed'
    assert result['issues'][0]['code'] == 'OSError'


def test_linked_surfaces_preserve_context_and_offsets(tmp_path):
    from ibl_corpus_surfaces import snippets
    p = tmp_path / 'doc.md'
    p.write_text('Example `[self:read]`\n```ibl\n[self:read]{path:"x"}\n```\n')
    found = list(snippets(p))
    assert len(found) == 2
    assert {r['kind'] for r in found} == {'markdown_inline', 'markdown_fence'}
    assert next(r for r in found if r['kind'] == 'markdown_inline')['review'] == 'fragment_not_standalone'


def test_structured_nested_source_keeps_edition(tmp_path):
    from ibl_corpus_surfaces import snippets
    p = tmp_path / 'schedule.json'
    dump(p, {'events': [{'edition': 2, 'code': '[self:read]{path:"x"}'}]})
    found = list(snippets(p))
    assert found[0]['edition_context'] == 2
    assert found[0]['location'] == '$/events/0/code'


def test_python_surface_is_parsed_not_imported(tmp_path):
    from ibl_corpus_surfaces import snippets
    p = tmp_path / 'danger.py'
    p.write_text('raise AssertionError("never import")\nx="[self:write]{path:1}"\n')
    found = list(snippets(p))
    assert len(found) == 1
    assert found[0]['kind'] == 'python_string'


def test_binary_metadata_is_not_a_failed_ibl_source(tmp_path):
    from ibl_corpus_surfaces import snippets
    p = tmp_path / '.DS_Store'
    p.write_bytes(b'\x80\xff')
    assert list(snippets(p)) == []


def test_frozen_catalog_includes_snapshot_api_actions(tmp_path):
    from audit_ibl_corpus_v2 import frozen_registry
    data = tmp_path / 'data'
    (data / 'vocabulary').mkdir(parents=True)
    (data / 'ibl_nodes.yaml').write_text('nodes:\n  sense:\n    actions: {}\n')
    (data / 'api_registry.yaml').write_text('tools:\n  sample_api:\n    node: sense\n    action_name: sample\n')
    dump(data / 'vocabulary/activation.json', {'active': {}})
    contracts, definitions, available, issues = frozen_registry(tmp_path, [])
    assert 'sense:sample' in contracts
    assert contracts['sense:sample']['compatibility'] == 'legacy-envelope/1'
    assert issues == []
