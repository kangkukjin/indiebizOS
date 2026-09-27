"""Corpus growth must not multiply registry loads or hide per-source errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iblbuild_v2 import check_v2_corpus


def test_session_reuses_registry_but_checks_every_source(monkeypatch):
    import ibl_v2_adapters
    import ibl_v2_store
    calls = []
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda: calls.append('registry') or {})
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: calls.append('library') or {})
    session, issues = {}, []
    for source in ('return 1', 'return $missing', 'return [2,3]'):
        assert check_v2_corpus('#!ibl edition=2\n'+source, {}, issues, 'fixture', session)
    assert calls == ['registry', 'library'] and len(issues) == 1
    check_v2_corpus('#!ibl edition=2\nreturn 4', {}, [], 'another pass', {})
    assert calls == ['registry', 'library', 'registry', 'library']


def test_broken_registry_is_reported_for_each_row_without_reloading(monkeypatch):
    import ibl_v2_adapters
    calls = []
    def broken():
        calls.append(1)
        raise OSError('fixture unavailable')
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', broken)
    session, issues = {}, []
    for i in range(3):
        check_v2_corpus('#!ibl edition=2\nreturn 1', {}, issues, f'row{i}', session)
    assert len(calls) == 1 and len(issues) == 3


def test_builder_preserves_unreviewed_errors_but_excludes_held_training(tmp_path):
    import json
    import sqlite3
    from iblbuild_validators import _corpus_entries
    from corpus_policy import current_examples
    invalid = {'intent': 'ambiguous', 'ibl_code': '#!ibl edition=2\nreturn $missing'}
    held = {**invalid, 'provenance': {'corpus_review': {
        'decision': 'hold', 'reason': 'channel must be established'}}}
    folder = tmp_path / 'data' / 'training'
    folder.mkdir(parents=True)
    (folder / 'cases.json').write_text(json.dumps([invalid, held]))
    with sqlite3.connect(tmp_path / 'data' / 'ibl_usage.db') as con:
        con.execute('CREATE TABLE ibl_examples(intent,ibl_code,alias,category,provenance)')
        con.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?)', [
            (r['intent'], r['ibl_code'], '', '', json.dumps(r.get('provenance', {})))
            for r in [invalid, held]])
    entries = list(_corpus_entries(tmp_path, include_db=True))
    assert len(entries) == 2  # One unreviewed invalid source per store must still fail.
    assert len(current_examples([invalid, held])[0]) == 1
    for origin, row in entries:
        issues = []
        assert check_v2_corpus(row['ibl_code'], row, issues, origin, {'registry': {}, 'library': {}})
        assert issues


def test_corpus_without_review_column_is_still_checked(tmp_path):
    import sqlite3
    from iblbuild_validators import _corpus_entries
    (tmp_path / 'data').mkdir()
    with sqlite3.connect(tmp_path / 'data' / 'ibl_usage.db') as con:
        con.execute('CREATE TABLE ibl_examples(intent,ibl_code,alias,category)')
        con.execute('INSERT INTO ibl_examples VALUES (?,?,?,?)', ('old', '[self:time]', '', ''))
    assert len(list(_corpus_entries(tmp_path, include_db=True))) == 1
