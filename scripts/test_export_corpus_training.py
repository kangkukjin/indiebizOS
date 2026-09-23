import json
import sqlite3

import pytest

from export_corpus_training import export


def test_both_stores_share_qualification_and_exports_cannot_mix(tmp_path):
    root = tmp_path / 'repo'
    (root / 'data/training').mkdir(parents=True)
    new = '#!ibl edition=2\nreturn 1'
    rows = [{'id': 1, 'intent': 'old', 'ibl_code': 'return 1', 'nodes': '', 'category': '', 'alias': '', 'provenance': '{}'},
            {'id': 2, 'intent': 'new', 'ibl_code': new, 'nodes': '', 'category': '', 'alias': '', 'provenance': '{}'}]
    with sqlite3.connect(root / 'data/ibl_usage.db') as conn:
        conn.execute('CREATE TABLE ibl_examples(id,intent,ibl_code,nodes,category,alias,provenance)')
        conn.executemany('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?)', [tuple(r.values()) for r in rows])
    (root / 'data/training/examples.json').write_text(json.dumps(rows))
    report = export(root, tmp_path / 'export')
    assert [r['accepted'] for r in report['sources']] == [1, 1]
    assert [r['excluded'] for r in report['sources']] == [{'legacy_source': 1}] * 2
    for path in (tmp_path / 'export/ibl_examples_export.json', tmp_path / 'export/training/examples.json'):
        assert json.loads(path.read_text()) == [rows[1]]
    with pytest.raises(ValueError, match='fresh'):
        export(root, tmp_path / 'export')
