#!/usr/bin/env python3
"""웹앱 관용구·호출 용례를 현재 IBL 입구로 멱등 등록한다. 상시 소개는 끈다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import json
import sqlite3
from datetime import datetime


def register(apply=False, local_encoder=False):
    from ibl_usage_db import IBLUsageDB
    from ibl_v2_store import definitions, definition_name
    from ibl_v2_learning import check_source
    db = IBLUsageDB()
    seeds = json.loads((ROOT / 'data/idioms/webapp_seeds.json').read_text())
    functions = [row for row in seeds if row.get('alias')]
    calls = [row for row in seeds if not row.get('alias')]
    library = definitions()
    for row in functions:
        name = row['alias']
        if definition_name(row['ibl_code']) != name:
            raise ValueError('등록 이름과 정의가 다릅니다')
        old = db.find_phrase_by_alias(name, edition=2)
        if old and old['ibl_code'].strip() != row['ibl_code'].strip():
            raise ValueError(f'{name}: 이미 다른 정의가 있습니다. 명시적 개정이 필요합니다')
        library[name] = row['ibl_code']
    for row in seeds:
        why = check_source(row['ibl_code'], bool(row.get('alias')), library=library)
        if why:
            raise ValueError(why)
    if not apply:
        return {'validated': len(seeds), 'changed': False}
    backup = ROOT / 'data/_backups' / (datetime.now().strftime('%Y-%m-%d_%H%M%S') + '_웹앱관용구')
    backup.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(ROOT / 'data/ibl_usage.db') as src, sqlite3.connect(backup / 'ibl_usage.db') as dst:
        src.backup(dst)
    if local_encoder:
        import urllib.request
        import numpy as np
        class RunningEncoder:
            def encode(self, texts, **kwargs):
                request = urllib.request.Request('http://127.0.0.1:8765/ibl/embed',
                    data=json.dumps({'texts': texts}).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    return np.asarray(json.load(response)['vectors'], dtype='float32')
        encoder = RunningEncoder()
        encoder.encode(['웹앱 관용구 등록'])
        IBLUsageDB._model = encoder
    elif not db._load_model_sync():
        raise RuntimeError('임베딩 모델을 준비하지 못했습니다')
    if not db._check_sqlite_vec():
        raise RuntimeError('sqlite_vec가 없습니다. .venv 파이썬으로 실행하세요')
    added = 0
    # 호출 용례는 앞 배치에서 등록된 함수로 검증된다. 모든 행은 단일 배치 입구를 쓴다.
    for batch in (functions, calls):
        with db._get_connection() as conn:
            pending = [row for row in batch if not conn.execute(
                'SELECT 1 FROM ibl_examples WHERE intent=? AND ibl_code=?',
                (row['intent'], row['ibl_code'])).fetchone()]
        inserted = db.add_examples_batch(pending)
        if inserted != len(pending):
            raise RuntimeError(f'원장 입구 거절: {inserted}/{len(pending)}. 백업: {backup}')
        added += inserted
    rows = []
    with db._get_connection() as conn:
        for seed in seeds:
            row = conn.execute('SELECT id,intent,ibl_code,alias FROM ibl_examples WHERE intent=? AND ibl_code=?',
                               (seed['intent'], seed['ibl_code'])).fetchone()
            rows.append(dict(row))
        conn.executemany('UPDATE ibl_examples SET always_on=0 WHERE id=?', [(r['id'],) for r in rows])
        conn.commit()
    vec = db._get_vec_connection()
    try:
        missing = [r for r in rows if not vec.execute(
            'SELECT rowid FROM ibl_examples_vec WHERE rowid=?', (r['id'],)).fetchone()]
    finally:
        vec.close()
    if missing:
        db._index_batch([r['id'] for r in missing], missing)
    vec = db._get_vec_connection()
    try:
        if not all(vec.execute('SELECT rowid FROM ibl_examples_vec WHERE rowid=?', (r['id'],)).fetchone() for r in rows):
            raise RuntimeError('의미 검색 색인이 미완료입니다')
    finally:
        vec.close()
    return {'inserted': added, 'ids': {r['alias']: r['id'] for r in rows if r['alias']},
            'always_on': False, 'semantic_indexed': len(rows), 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--local-encoder', action='store_true')
    args = parser.parse_args()
    print(json.dumps(register(args.apply, args.local_encoder), ensure_ascii=False, indent=2))
