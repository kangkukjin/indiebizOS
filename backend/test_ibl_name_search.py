"""벡터 색인 여부가 서로 다른 관용구의 이름 검색과 자동 회상."""
import sqlite3
import struct

import boot_paths  # noqa: F401
import pytest

from test_ibl_v2_assets import memory  # noqa: F401


@pytest.fixture
def mixed_index(memory, tmp_path, monkeypatch):
    import ibl_access
    import korean_utils

    path = tmp_path / 'vectors.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE ibl_examples_vec (rowid INTEGER PRIMARY KEY, embedding BLOB)')
    monkeypatch.setattr(memory, 'is_semantic_available', lambda: True)
    monkeypatch.setattr(memory, '_generate_embedding', lambda _: struct.pack('ff', 1, 0))
    monkeypatch.setattr(memory, '_get_vec_connection', lambda: sqlite3.connect(path))
    monkeypatch.setattr(memory, '_ensure_vec_table', lambda _: None)
    monkeypatch.setattr(memory, 'hippo_disabled', lambda: False)
    monkeypatch.setattr(memory, '_rented_mode', lambda: False)
    monkeypatch.setattr(korean_utils, 'tokenize_korean', lambda query: query.split())
    monkeypatch.setattr(ibl_access, 'exposed_idiom_names', lambda _: frozenset())

    def add_indexed(name, vector):
        assert memory.add_examples_batch([{
            'intent': name, 'alias': name, 'category': 'phrase', 'nodes': '',
            'ibl_code': f'#!ibl edition=2\n[def:{name}](){{return 1}}',
        }]) == 1
        with memory._get_connection() as conn:
            row_id = conn.execute('SELECT id FROM ibl_current_examples WHERE alias = ?', (name,)).fetchone()[0]
        with sqlite3.connect(path) as conn:
            conn.execute('INSERT INTO ibl_examples_vec VALUES (?, ?)', (row_id, struct.pack('ff', *vector)))

    return memory, add_indexed


def test_catalog_only_phrase_is_recalled_alongside_indexed_phrase(mixed_index):
    from function_library import register
    from ibl_name_search import search_aliased
    from ibl_usage_rag import IBLUsageRAG

    db, add_indexed = mixed_index
    add_indexed('기존관용구', (1, 0))
    register('신규조사', '#!ibl edition=2\n[def:신규조사](){return 42}', '신규조사')

    results = {row.alias: row for row in search_aliased(db, '신규조사')}
    assert results['신규조사'].source == 'function_catalog'
    assert results['신규조사'].score == pytest.approx(0.8)
    assert results['기존관용구'].score == pytest.approx(0.7)
    fresh, seen = IBLUsageRAG().search_phrases_split('신규조사')
    assert [row.alias for row in fresh] == ['신규조사', '기존관용구']
    assert seen == []


def test_observed_zero_similarity_keeps_hybrid_score(mixed_index):
    from ibl_name_search import search_aliased
    from ibl_usage_rag import IBLUsageRAG

    db, add_indexed = mixed_index
    add_indexed('색인된조사', (0, 1))
    results = search_aliased(db, '색인된조사')
    assert len(results) == 1
    assert results[0].score == pytest.approx(0.3)
    assert IBLUsageRAG().search_phrases_split('색인된조사') == ([], [])


def test_unindexed_partial_match_stays_below_recall_threshold(mixed_index):
    from function_library import register
    from ibl_name_search import search_aliased
    from ibl_usage_rag import IBLUsageRAG

    db, add_indexed = mixed_index
    add_indexed('기존관용구', (1, 0))
    register('신규조사', '#!ibl edition=2\n[def:신규조사](){return 42}', '신규조사')
    query = '신규조사 무관한단어'
    results = {row.alias: row for row in search_aliased(db, query)}
    assert results['신규조사'].score == pytest.approx(0.4)
    fresh, _ = IBLUsageRAG().search_phrases_split(query)
    assert [row.alias for row in fresh] == ['기존관용구']
