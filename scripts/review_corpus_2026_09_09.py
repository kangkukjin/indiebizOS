#!/usr/bin/env python3
"""기존 코퍼스의 검토된 행만 교체. 기본은 읽기 전용 검증, --apply로 적용.

행 추가·삭제/중복제거 없음. 행 ID·의도·출처·성공 통계는 보존한다.
운영 JSON/DB는 git 제외이므로 docs의 exact manifest가 재적용 정본이다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from collections import Counter
from datetime import datetime

from ibl_param_vocab import check_code_params
from ibl_typecheck import return_type_of, typecheck_code
from ibl_parser import parse_function_body
from workflow_contract import _free_vars

REVIEW = ROOT / 'docs/corpus_review_2026_09_09'
DB = ROOT / 'data/ibl_usage.db'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def key(row):
    return row['origin'], row['row_id']


def load_manifest():
    changes = {r['index']: r for r in lines(REVIEW / 'replacements.jsonl')}
    ledger = [r for p in sorted(REVIEW.glob('rows_*.jsonl')) for r in lines(p)]
    assert len({key(r) for r in ledger}) == len(ledger)
    for entry in ledger:
        if entry['decision'] == 'replace':
            c = changes[entry['replacement']]
            assert digest(c['before']) == entry['before_sha256']
            assert digest(c['after']) == entry['after_sha256']
            assert dict(origin=entry['origin'], row_id=entry['row_id']) in c['targets']
        else:
            assert entry['before_sha256'] == entry['after_sha256']
    return changes, ledger


def read_sources(ledger, conn):
    files = {}
    rows = {}
    for origin in sorted({r['origin'] for r in ledger} - {'db'}):
        files[origin] = json.loads((ROOT / origin).read_text())
        rows.update({(origin, i): r for i, r in enumerate(files[origin])})
    rows.update({('db', r['id']): dict(r) for r in conn.execute('SELECT * FROM ibl_examples')})
    assert set(rows) == {key(r) for r in ledger}, '행 목록 변경 — 재검토 필요'
    return files, rows


def prepare(changes, ledger, rows):
    pending = []
    warnings = []
    for entry in ledger:
        row = rows[key(entry)]
        assert digest(row['intent']) == entry['intent_sha256'], ('의도 변경', key(entry))
        old = row['ibl_code']
        assert digest(old) in (entry['before_sha256'], entry['after_sha256']), ('코드 변경', key(entry))
        new = changes[entry['replacement']]['after'] if entry['decision'] == 'replace' else old
        # alias는 함수 몸이다. standalone 머리 입력/미할당 인자를 오탐하지 않는다.
        code = '[def:검토]{' + new + '}' if row.get('alias') else new
        tc = typecheck_code(code)
        assert tc['ok'] and not tc.get('abstained'), (key(entry), tc)
        params = check_code_params(new)
        assert not params, (key(entry), params)
        if tc['issues']:
            warnings.append(dict(origin=entry['origin'], row_id=entry['row_id'], issues=tc['issues']))
        if old != new:
            pending.append((entry, old, new))
    return pending, warnings


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.corpus-review-tmp')
    try:
        with temporary.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(changes, ledger, pending, files, rows, connection):
    from ibl_usage_db import IBLUsageDB
    # 모델/확장 준비 실패 시 원본에는 손대지 않는다. local model만 사용한다.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    indexer = object.__new__(IBLUsageDB)
    db_changes = [p for p in pending if p[0]['origin'] == 'db']
    embeddings = []
    if db_changes:
        assert indexer._load_model_sync(), '로컬 임베딩 모델 로드 실패'
        embeddings = indexer._generate_embeddings_batch([
            indexer._prepare_search_text(rows[key(e)]['intent'], new)
            for e, _, new in db_changes
        ])
        assert len(embeddings) == len(db_changes)
    backup = ROOT / 'data/_backups' / (datetime.now().strftime('%Y-%m-%d_%H%M%S') + '_corpus_review')
    backup.mkdir(parents=True, exist_ok=False)
    # SQLite 온라인 백업. WAL 파일 복사는 일관된 백업이 아니다.
    with sqlite3.connect(backup / 'ibl_usage.db') as destination:
        connection.backup(destination)
    originals = {o: (ROOT / o).read_bytes() for o in files}
    for origin, data in originals.items():
        path = backup / origin
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    shutil.copytree(REVIEW, backup / 'review')
    vconn = indexer._get_vec_connection()
    assert vconn is not None, '벡터 연결 실패; 변경 없음'
    written = []
    try:
        vconn.execute('BEGIN IMMEDIATE')
        # 인코딩·백업 중 들어온 코드/행 변경을 덮어쓰지 않는다.
        fresh_files, fresh_rows = read_sources(ledger, vconn)
        again, _ = prepare(changes, ledger, fresh_rows)
        assert again == pending, '준비 중 코퍼스가 변경됨'
        assert all((ROOT / o).read_bytes() == raw for o, raw in originals.items())
        before_ids = set(fresh_rows)
        for entry, old, new in pending:
            if entry['origin'] != 'db':
                fresh_files[entry['origin']][entry['row_id']]['ibl_code'] = new
        for (entry, old, new), embedding in zip(db_changes, embeddings):
            row = fresh_rows[key(entry)]
            signature = ' '.join(_free_vars(parse_function_body(new)))
            returns = return_type_of(new) if row.get('alias') else row.get('returns', '')
            # nodes는 코드에서 파생되는 검색 메타데이터. 통계·topic·alias 등은 보존.
            from system_tools_ibl import _collect_step_nodes
            found = set()
            _collect_step_nodes(parse_function_body(new), found)
            nodes = ",".join(sorted(found & {"sense", "self", "limbs", "others", "engines", "table"}))
            cursor = vconn.execute(
                'UPDATE ibl_examples SET ibl_code=?, nodes=?, signature=?, returns=?, updated_at=? '
                'WHERE id=? AND ibl_code=?',
                (new, nodes, signature, returns, datetime.now().isoformat(), entry['row_id'], old))
            assert cursor.rowcount == 1
            vconn.execute('DELETE FROM ibl_examples_vec WHERE rowid=?', (entry['row_id'],))
            vconn.execute('INSERT INTO ibl_examples_vec(rowid, embedding) VALUES (?,?)',
                          (entry['row_id'], embedding))
        for origin, data in fresh_files.items():
            if data != files[origin]:
                atomic_write(ROOT / origin, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
                written.append(origin)
        _, final_rows = read_sources(ledger, vconn)
        assert set(final_rows) == before_ids
        assert all(digest(final_rows[key(e)]['ibl_code']) == e['after_sha256'] for e in ledger)
        # 외부 콘텐츠 FTS 실제 인덱스를 행 원문과 대조한다(트리거 검증).
        vconn.execute("INSERT INTO ibl_examples_fts(ibl_examples_fts, rank) VALUES ('integrity-check', 1)")
        vconn.commit()
    except BaseException:
        vconn.rollback()
        for origin in written:
            atomic_write(ROOT / origin, originals[origin])
        raise
    finally:
        vconn.close()
    return str(backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes, ledger = load_manifest()
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        files, rows = read_sources(ledger, conn)
        pending, warnings = prepare(changes, ledger, rows)
        result = dict(total=len(ledger), decisions=dict(Counter(r['decision'] for r in ledger)),
                      pending=len(pending), warning_rows=len(warnings),
                      pending_by_origin=dict(Counter(e['origin'] for e, _, _ in pending)))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.apply and pending:
            result['backup'] = apply(changes, ledger, pending, files, rows, conn)
            result['applied'] = len(pending)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            (Path(result['backup']) / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
