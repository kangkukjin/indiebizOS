"""History remains addressable without participating in executable retrieval."""
import sqlite3

from ibl_example_index import ensure_current_examples, ensure_search_index


def database():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias TEXT, intent TEXT, ibl_code TEXT)')
    ensure_current_examples(db)
    ensure_search_index(db)
    return db


def matches(db, word):
    return [r[0] for r in db.execute('SELECT rowid FROM ibl_current_fts WHERE ibl_current_fts MATCH ?', (word,))]


def test_index_admission_edit_withdrawal_and_deletion():
    with database() as db:
        db.execute("INSERT INTO ibl_examples VALUES(1,'old','history secret','unparseable',0)")
        db.execute("INSERT INTO ibl_examples VALUES(2,'current','searchable','return 1',1)")
        assert matches(db, 'secret') == []
        assert matches(db, 'searchable') == [2]
        db.execute("UPDATE ibl_examples SET intent='edited' WHERE id=2")
        assert matches(db, 'searchable') == []
        assert matches(db, 'edited') == [2]
        db.execute('UPDATE ibl_examples SET executable=0 WHERE id=2')
        assert matches(db, 'edited') == []
        db.execute('UPDATE ibl_examples SET executable=1 WHERE id=2')
        assert matches(db, 'edited') == [2]
        db.execute('DELETE FROM ibl_examples WHERE id=2')
        assert matches(db, 'edited') == []
        assert db.execute('SELECT ibl_code FROM ibl_examples WHERE id=1').fetchone()[0] == 'unparseable'


def test_default_read_uses_partial_index_without_source_revalidation():
    with database() as db:
        db.executemany('INSERT INTO ibl_examples VALUES(?,?,?,?,0)',
                       [(i, 'old', 'historical', 'not a program') for i in range(1, 1001)])
        db.execute("INSERT INTO ibl_examples VALUES(1001,'current','eligible','return 2',1)")
        plan = str(db.execute('EXPLAIN QUERY PLAN SELECT id FROM ibl_current_examples WHERE alias=?', ('current',)).fetchall())
        assert 'ibl_examples_current' in plan
        assert db.execute('SELECT COUNT(*) FROM ibl_current_examples').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM ibl_examples').fetchone()[0] == 1001


def test_history_id_read_does_not_parse_or_synchronize(tmp_path, monkeypatch):
    import hippo_tree
    import ibl_v2_parser
    import pytest
    path=tmp_path/'memory.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias, intent, ibl_code, topic)')
        ensure_current_examples(db)
        db.execute("INSERT INTO ibl_examples VALUES(7,'old','original','not parseable', 'archive',0)")
    monkeypatch.setattr(hippo_tree,'sync_topic',lambda *a: pytest.fail('historical read synchronized'))
    monkeypatch.setattr(ibl_v2_parser,'parse',lambda *a: pytest.fail('historical read parsed'))
    result=hippo_tree.recall('archive',str(path),expand='#7')
    assert result['historical'] and not result['executable']
    assert result['items'][0]['ibl_code']=='not parseable'


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
