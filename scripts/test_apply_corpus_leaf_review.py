"""Migration preserves identities/evidence and recovers across DB/JSON stages."""
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import apply_corpus_leaf_review as migration
from ibl_corpus_snapshot import sha


CONTRACT = {'version': 1, 'params': {'query': 'Unknown', 'city': 'Unknown', 'op': 'Unknown'},
            'required': [], 'result': 'Record', 'effects': ['unknown'],
            'compatibility': 'legacy-envelope/1',
            'adapter': {'protocol': 'legacy-envelope', 'value_path': ''}}
OLD = '[sense:search]{query:"007"}'
NEW = '#!ibl edition=2\nreturn ' + OLD


def entry(origin=migration.DB_ORIGIN, row_id=1, decision='convert'):
    return {'origin': origin, 'row_id': row_id, 'before_code': OLD, 'before_sha256': sha(OLD),
            'intent_sha256': sha('007을 검색'), 'after_code': NEW, 'decision': decision,
            'reason': '검토한 문자열 검색 입력과 전체 반환 보존'}


def test_real_compiler_and_decoder_keep_values_failures_and_arguments():
    result = migration.prove(OLD, NEW, CONTRACT, 'convert')
    assert result['status'] == 'incomplete'
    assert len(result['cases']) == 7 and result['external_calls'] == 0
    assert result['after_args'] == {'query': '007'}


@pytest.mark.parametrize('source', [
    '[sense:search]{query:$q}', '[sense:search]{query:"$q"}',
    '[sense:search]{} >> [table:take]{n:1}', '[self:write]{path:"x",content:"x"}',
])
def test_nonliteral_or_composed_sources_require_separate_review(source):
    with pytest.raises(ValueError):
        migration.literal_call(source)


def test_changed_argument_cannot_be_claimed_as_equivalent_conversion():
    with pytest.raises(ValueError, match='달라졌습니다'):
        migration.prove(OLD, NEW.replace('007', '008'), CONTRACT, 'convert')


def test_storage_format_uses_origin_and_keeps_training_id():
    row = {'id': 42, 'ibl_code': OLD, 'provenance': ''}
    db = migration.upgraded(row, entry(), 'review')
    assert isinstance(db['provenance'], str) and 'edition' not in db
    training = migration.upgraded(row, entry('data/training/test.json'), 'review')
    assert training['id'] == 42 and training['edition'] == 2
    assert isinstance(training['provenance'], dict)
    with pytest.raises(ValueError, match='corpus_versions'):
        migration.upgraded({**row, 'provenance': {'corpus_versions': {}}}, entry(), 'review')


def test_decimal_literal_is_not_proven_safe_at_legacy_json_boundary():
    old = '[sense:search]{query:37.5}'
    with pytest.raises(ValueError):
        migration.prove(old, '#!ibl edition=2\nreturn ' + old, CONTRACT, 'convert')


class Indexer:
    def __init__(self, path):
        self.path = path

    def _get_vec_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _prepare_search_text(self, intent, code):
        return intent + code

    def _generate_embeddings_batch(self, texts):
        return [sha(t).encode() for t in texts]


@pytest.fixture
def setup(tmp_path):
    data = tmp_path / 'data'
    (data / 'training').mkdir(parents=True)
    indexer = Indexer(data / 'ibl_usage.db')
    with indexer._get_vec_connection() as conn:
        conn.executescript('''
            CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY,intent,ibl_code,nodes,signature,returns,
                provenance,updated_at,success_count,fail_count,bypass_count,avg_ms,avg_tokens,
                alias,always_on,topic);
            CREATE TABLE ibl_examples_vec(rowid INTEGER PRIMARY KEY,embedding BLOB);
            CREATE VIRTUAL TABLE ibl_examples_fts USING fts5(intent,ibl_code,content='ibl_examples',content_rowid='id');
            CREATE TRIGGER ins AFTER INSERT ON ibl_examples BEGIN
                INSERT INTO ibl_examples_fts(rowid,intent,ibl_code) VALUES(new.id,new.intent,new.ibl_code); END;
            CREATE TRIGGER upd AFTER UPDATE ON ibl_examples BEGIN
                INSERT INTO ibl_examples_fts(ibl_examples_fts,rowid,intent,ibl_code)
                VALUES('delete',old.id,old.intent,old.ibl_code);
                INSERT INTO ibl_examples_fts(rowid,intent,ibl_code) VALUES(new.id,new.intent,new.ibl_code); END;
        ''')
        conn.execute('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (1,'007을 검색',OLD,'sense',None,'','{"owner":"keep"}','old',9,2,3,100,200,'',0,'topic'))
        conn.execute('INSERT INTO ibl_examples_vec VALUES (?,?)', (1,b'old'))
        conn.commit()
    source = data / 'training/test.json'
    source.write_text(json.dumps([{'intent':'007을 검색','ibl_code':OLD,'source':'keep'},
                                 {'intent':'보류','ibl_code':'untouched'}]))
    entries = [entry(), entry('data/training/test.json', 0)]
    journal = {'path':tmp_path / 'journal.json'}
    return tmp_path, indexer, source, entries, journal


def test_apply_keeps_ids_old_statistics_and_refreshes_fts_vectors(setup):
    root, indexer, source, entries, journal = setup
    result = migration.apply_rows(root, entries, 'review', indexer, journal)
    assert result['db_applied'] == result['json_applied'] == result['vector_content_verified'] == 1
    with indexer._get_vec_connection() as conn:
        row = dict(conn.execute('SELECT * FROM ibl_examples').fetchone())
        assert row['id'] == 1 and row['intent'] == '007을 검색' and row['topic'] == 'topic'
        assert row['ibl_code'] == NEW and row['success_count'] == row['fail_count'] == 0
        p = json.loads(row['provenance'])
        assert p['owner'] == 'keep'
        assert p['corpus_versions'][0]['code'] == OLD
        assert p['corpus_versions'][0]['observations']['success_count'] == 9
        assert conn.execute("SELECT rowid FROM ibl_examples_fts WHERE ibl_examples_fts MATCH 'return'").fetchall()
    rows = json.loads(source.read_text())
    assert rows[0]['edition'] == 2 and rows[0]['source'] == 'keep'
    assert rows[1] == {'intent':'보류','ibl_code':'untouched'}


def test_resume_after_db_commit_does_not_reset_new_observations(setup, monkeypatch):
    root, indexer, source, entries, journal = setup
    original = migration.atomic_json
    def fail_file(path, data):
        if path == source:
            raise OSError('simulated crash between stores')
        return original(path, data)
    monkeypatch.setattr(migration, 'atomic_json', fail_file)
    with pytest.raises(OSError):
        migration.apply_rows(root, entries, 'review', indexer, journal)
    with indexer._get_vec_connection() as conn:
        assert conn.execute('SELECT ibl_code FROM ibl_examples').fetchone()[0] == NEW
        conn.execute('UPDATE ibl_examples SET success_count=3')
        conn.commit()
    monkeypatch.setattr(migration, 'atomic_json', original)
    result = migration.apply_rows(root, entries, 'review', indexer, journal)
    assert result['db_applied'] == 0 and result['json_applied'] == 1
    with indexer._get_vec_connection() as conn:
        row = dict(conn.execute('SELECT * FROM ibl_examples').fetchone())
        assert row['success_count'] == 3
        assert len(json.loads(row['provenance'])['corpus_versions']) == 1
    result = migration.apply_rows(root, entries, 'review', indexer, journal)
    assert result['db_applied'] == result['json_applied'] == 0


def test_stale_intent_refuses_every_write(setup):
    root, indexer, source, entries, journal = setup
    entries[0]['intent_sha256'] = sha('changed')
    with pytest.raises(ValueError, match='의도'):
        migration.apply_rows(root, entries, 'review', indexer, journal)
    with indexer._get_vec_connection() as conn:
        assert conn.execute('SELECT ibl_code FROM ibl_examples').fetchone()[0] == OLD


def load_handler(folder):
    path = migration.ROOT / 'data/packages/installed/tools' / folder / 'handler.py'
    spec = importlib.util.spec_from_file_location('corpus_fixture_' + folder, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_region_handler_reads_city_not_query(monkeypatch):
    handler = load_handler('real-estate')
    calls = []
    def get_codes(city, **kwargs):
        calls.append(city)
        return {'items': [{'region': city}]}
    monkeypatch.setattr(handler, 'load_module', lambda name: SimpleNamespace(get_region_codes=get_codes))
    handler._op_codes({'op':'codes','query':'서울'}, None)
    result = handler._op_codes({'op':'codes','city':'서울'}, None)
    assert calls == ['', '서울'] and result['items'][0]['region'] == '서울'


def test_actual_sec_handler_reads_filing_type_not_type(monkeypatch):
    handler = load_handler('investment')
    calls = []
    def filings(**kwargs):
        calls.append(kwargs)
        return {'items': []}
    monkeypatch.setattr(handler, 'load_module', lambda name: SimpleNamespace(get_filings=filings))
    base = {'op':'disclosures','market':'us','company':'AAPL'}
    handler._company_disclosures({**base,'type':'10-K'})
    handler._company_disclosures({**base,'filing_type':'10-K'})
    assert [c['filing_type'] for c in calls] == [None,'10-K']
    assert all(c['symbol'] == 'AAPL' for c in calls)
