#!/usr/bin/env python3
"""Explicit, backed-up storage transition. Never imported by the application.

Run with the backend stopped. Immutable function revisions and original example
columns are retained; only catalog membership and disposable search indexes move.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import function_store as store
from ibl_example_index import ensure_current_examples, ensure_search_index
from corpus_policy import review_exclusion_reason


def project_training(base, backup):
    marker = backup / 'training-report.json'
    if marker.exists():
        return json.loads(marker.read_text())
    report = []
    for path in sorted((base / 'data/training').glob('*.json')):
        saved = backup / 'training' / path.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            shutil.copy2(path, saved)
        rows = json.loads(saved.read_text())
        if not isinstance(rows, list):
            raise ValueError(f'Expected training row list: {path.name}')
        current, history = [], []
        for row in rows:
            code = row.get('ibl_code', '') if isinstance(row, dict) else ''
            (current if isinstance(code, str) and code.lstrip().startswith('#!ibl edition=2\n') else history).append(row)
        archive = base / 'data/ibl_history/training' / path.name
        store._atomic(archive, json.dumps(history, ensure_ascii=False, indent=2)+'\n')
        store._atomic(path, json.dumps(current, ensure_ascii=False, indent=2)+'\n')
        report.append({'path':str(path.relative_to(base)), 'current':len(current),
                       'historical':len(history), 'original_sha256':hashlib.sha256(saved.read_bytes()).hexdigest()})
    backup.mkdir(parents=True, exist_ok=True)
    store._atomic(marker, json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def transition(base, backup):
    base, backup = Path(base), Path(backup)
    root = base / 'data/workflows'
    with store.transaction(root):
        catalog_path = root / 'catalog.json'
        original = json.loads(catalog_path.read_text())
        if original.get('schema') == 2:
            project_training(base, backup)
            return {'already_current': True}
        if original.get('schema') != 1:
            raise ValueError('Unknown source catalog schema')
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / 'catalog.json').exists():
            shutil.copy2(catalog_path, backup / 'catalog.json')
        current, history = {}, {}
        for fid, entry in original['functions'].items():
            (current if entry['edition'] == 2 else history)[fid] = entry
        dbpath = base / 'data/ibl_usage.db'
        conn = sqlite3.connect(dbpath)
        conn.row_factory = sqlite3.Row
        try:
            if not (backup / 'ibl_usage.db').exists():
                saved = sqlite3.connect(backup / 'ibl_usage.db')
                conn.backup(saved)
                saved.close()
            columns = [r[1] for r in conn.execute('PRAGMA table_info(ibl_examples)') if r[1] != 'executable']
            select = 'SELECT ' + ','.join(columns) + ' FROM ibl_examples ORDER BY id'
            before = store.digest([tuple(r) for r in conn.execute(select)])
            conn.execute('BEGIN IMMEDIATE')
            ensure_current_examples(conn)
            for trigger in ('ibl_examples_ai', 'ibl_examples_ad', 'ibl_examples_au'):
                conn.execute(f'DROP TRIGGER IF EXISTS {trigger}')
            conn.execute('DROP TABLE IF EXISTS ibl_examples_fts')
            admitted = [r['id'] for r in conn.execute('SELECT * FROM ibl_examples')
                        if r['ibl_code'].lstrip().startswith('#!ibl edition=2\n')
                        and not review_exclusion_reason(r)]
            conn.execute('UPDATE ibl_examples SET executable=0')
            conn.executemany('UPDATE ibl_examples SET executable=1 WHERE id=?', [(i,) for i in admitted])
            ensure_search_index(conn)
            conn.execute("INSERT INTO ibl_current_fts(ibl_current_fts) VALUES ('rebuild')")
            after = store.digest([tuple(r) for r in conn.execute(select)])
            if before != after:
                raise ValueError('Original memory columns changed')
            conn.commit()
            # sqlite-vec is a derived candidate index; historical source stays above.
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='ibl_examples_vec'").fetchone():
                conn.execute('DELETE FROM ibl_examples_vec WHERE rowid NOT IN (SELECT id FROM ibl_current_examples)')
                conn.commit()
        finally:
            conn.close()
        portable = base / 'data/ibl_hippo_index.json'
        vecs = base / 'data/ibl_hippo_vecs.f32'
        if portable.exists() and vecs.exists():
            for path in (portable, vecs):
                if not (backup / path.name).exists():
                    shutil.copy2(path, backup / path.name)
            index = json.loads((backup / portable.name).read_text())
            raw, width = (backup / vecs.name).read_bytes(), index['dim'] * 4
            if len(raw) != len(index['examples']) * width:
                raise ValueError('Portable vector alignment mismatch')
            selected = [(n, e) for n, e in enumerate(index['examples']) if e['id'] in set(admitted)]
            index.update(examples=[e for _, e in selected], count=len(selected))
            vecs.write_bytes(b''.join(raw[n*width:(n+1)*width] for n, _ in selected))
            store._atomic(portable, json.dumps(index, ensure_ascii=False))
        archive = {**original, 'functions': history}
        store._atomic(root / 'history.json', json.dumps(archive, ensure_ascii=False, indent=2))
        active = {k: v for k, v in original.items() if k not in {'migration', 'functions'}}
        active.update(schema=2, functions=current, generation=original['generation']+1)
        report = {'functions': len(current), 'historical_functions': len(history),
                  'examples': len(admitted), 'original_rows_hash': before,
                  'catalog_before': hashlib.sha256((backup/'catalog.json').read_bytes()).hexdigest()}
        store._atomic(backup / 'report.json', json.dumps(report, ensure_ascii=False, indent=2))
        project_training(base, backup)
        # Last publication is the completion marker; interrupted work is replayable.
        store._atomic(catalog_path, json.dumps(active, ensure_ascii=False, indent=2))
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(transition(args.root, args.backup), ensure_ascii=False, indent=2))
