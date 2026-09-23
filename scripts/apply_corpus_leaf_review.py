"""Validate and migrate individually reviewed literal leaf calls to edition 2.

No model training or external tool execution. IDs and intents stay fixed;
old code/statistics remain in provenance and an online backup. DB+JSON commits
are journaled separately: rerun the same review after interruption to roll
forward, without resetting statistics of rows already on the new version.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import json
import os
import sqlite3
from collections import Counter

from ibl_corpus_snapshot import connect, dump, now, sha, snapshot
from ibl_parser import parse
from ibl_edition import source_edition
from ibl_v2_adapters import Adapter, Adapted, decode_envelope
from ibl_v2_compile import compile_program
from ibl_v2_compat import plain_arguments
from ibl_v2_runtime import Runtime

DB_ORIGIN = 'data/ibl_usage.db:ibl_examples'
RESET = {'success_count': 0, 'fail_count': 0, 'bypass_count': 0,
         'avg_ms': -1.0, 'avg_tokens': -1.0}


def literal_call(source):
    if source_edition(source) != 1:
        raise ValueError('원본은 검토한 판본 1 leaf여야 합니다.')
    steps = parse(source)
    if len(steps) != 1 or not isinstance(steps[0], dict):
        raise ValueError('단일 호출이 아닙니다.')
    call = steps[0]
    if (set(call) - {'_node', 'action', 'target', 'params'}
            or call.get('_node') in {'fn', 'def'} or call.get('target')):
        raise ValueError('대상 없는 명시 액션 호출이 아닙니다.')
    def literal(value):
        if isinstance(value, str):
            return '$' not in value
        if isinstance(value, list):
            return all(literal(v) for v in value)
        if isinstance(value, dict):
            return all(isinstance(k, str) and not k.startswith('_') and literal(v)
                       for k, v in value.items())
        return value is None or type(value) in (int, float, bool)
    if not literal(call.get('params', {})):
        raise ValueError('입력/보간/내부 표현이 있는 호출은 개별 프로그램 검토가 필요합니다.')
    return call['_node'] + ':' + call['action'], call.get('params', {})


def candidate_call(source):
    prefix = '#!ibl edition=2\nreturn '
    if not source.startswith(prefix):
        raise ValueError('후보에는 명시 판본과 return이 필요합니다.')
    return literal_call(source[len(prefix):])


def prove(before, after, contract, decision):
    action, old_args = literal_call(before)
    new_action, args = candidate_call(after)
    if action != new_action or (decision == 'convert' and args != old_args):
        raise ValueError('동등 이관의 호출/인자가 달라졌습니다. 수리로 별도 검토하세요.')
    if contract.get('compatibility') != 'legacy-envelope/1':
        raise ValueError('이 적용기의 반환 증명은 legacy-envelope/1에 한정합니다.')
    outcomes = []
    cases = [
        ('empty', {'success': True, 'items': [], 'source': 'fixture'}, None),
        ('one', {'success': True, 'items': [{'id': '007', 'n': None}], 'source': 'fixture'}, None),
        ('many', {'success': True, 'items': [{'id': '007'}, {'id': 'b'}, {'id': 'c'}],
                  'source': 'fixture', 'nested': [[], [1, 2]]}, None),
        ('error', {'success': False, 'error': 'fixture failed'}, 'runtime'),
        ('denied', {'success': False, 'error': 'fixture denied', 'denied': True}, 'permission'),
        ('partial', {'success': True, 'items': [{'id': '007'}], 'error_count': 1}, 'partial'),
        ('partial_flag_only', {'success': True, 'items': [], 'partial': True}, None),
    ]
    for name, payload, failure in cases:
        seen = []
        def run(runtime, params):
            plain_arguments(params)  # same typed-value gate as the live legacy adapter
            seen.append(copy.deepcopy(params))
            value, evidence = decode_envelope(copy.deepcopy(payload), contract['adapter'])
            return Adapted(value, evidence)
        plan = compile_program(after, {action: Adapter(contract, run)})
        if plan.issues:
            raise ValueError(plan.issues)
        result = Runtime(plan).run()
        if seen != [args]:
            diagnostic = result.get('diagnostic', {})
            raise ValueError(f'호출 횟수/인자 불일치: {name}; {diagnostic.get("code", "arguments")}')
        if failure:
            if result['success'] or result.get('diagnostic', {}).get('kind') != failure:
                raise ValueError(f'실패를 성공으로 바꾸거나 종류를 잃음: {name}')
        elif not result['success'] or result['value'] != payload:
            raise ValueError(f'전체 Record·순서·문자열·중첩 불일치: {name}')
        outcomes.append({'case': name, 'passed': True})
    return {'status': plan.report()['status'], 'cases': outcomes,
            'before_args': old_args, 'after_args': args, 'external_calls': 0}


def file_path(root, origin):
    relative = Path(origin)
    if relative.parent != Path('data/training') or relative.suffix != '.json':
        raise ValueError('검토 가능한 파일은 data/training/*.json뿐입니다.')
    path = root / relative
    if path.is_symlink():
        raise ValueError('symlink 학습 파일은 별도 검토가 필요합니다.')
    return path


def load_sources(root, entries, conn):
    files = {o: json.loads(file_path(root, o).read_text())
             for o in {e['origin'] for e in entries} if o != DB_ORIGIN}
    rows = {(o, i): r for o, data in files.items() for i, r in enumerate(data)}
    rows.update({(DB_ORIGIN, r['id']): dict(r) for r in conn.execute('SELECT * FROM ibl_examples')})
    return files, rows


def pending_rows(entries, rows):
    pending, seen = [], set()
    for entry in entries:
        key = entry['origin'], entry['row_id']
        if key in seen:
            raise ValueError('중복 검토 행')
        seen.add(key)
        row = rows.get(key)
        if not row or sha(row['intent']) != entry['intent_sha256']:
            raise ValueError(f'원본 의도/행 변경: {key}')
        if row.get('alias') or row.get('always_on'):
            raise ValueError('함수 정의/상시 별칭은 이 적용기의 대상이 아닙니다.')
        if entry['decision'] not in ('hold', 'convert', 'repair') or not entry['reason']:
            raise ValueError('검토 판정/사유 누락')
        if sha(entry['before_code']) != entry['before_sha256']:
            raise ValueError('검토 원문 지문 불일치')
        if row['ibl_code'] == entry['before_code']:
            if entry['decision'] != 'hold':
                if source_edition(row['ibl_code'], row.get('edition')) != 1:
                    raise ValueError('원본 저장 판본 충돌')
                pending.append(entry)
        elif entry['decision'] == 'hold' or row['ibl_code'] != entry['after_code']:
            raise ValueError(f'코드가 검토 이후 변경됨: {key}')
        else:
            if source_edition(row['ibl_code'], row.get('edition')) != 2:
                raise ValueError('적용 후 저장 판본 충돌')
            provenance = row.get('provenance') or {}
            if isinstance(provenance, str):
                provenance = json.loads(provenance)
            if not any(v.get('sha256') == entry['before_sha256'] and v.get('code') == entry['before_code']
                       for v in provenance.get('corpus_versions', [])):
                raise ValueError('같은 후보 코드지만 구형 판본 보존 증거가 없습니다.')
    return pending


def upgraded(row, entry, review_hash):
    new = copy.deepcopy(row)
    raw = row.get('provenance') or {}
    provenance = json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    if not isinstance(provenance, dict):
        raise ValueError('기존 provenance를 덮어쓸 수 없습니다.')
    history = provenance.setdefault('corpus_versions', [])
    if not isinstance(history, list):
        raise ValueError('기존 corpus_versions를 덮어쓸 수 없습니다.')
    history.append({'edition': 1, 'code': row['ibl_code'], 'sha256': entry['before_sha256'],
                    'observations': {k: row[k] for k in RESET if k in row},
                    'metadata': {k: row[k] for k in ('nodes', 'signature', 'returns', 'updated_at') if k in row}})
    provenance['corpus_review'] = {'edition': 2, 'review_sha256': review_hash,
                                  'decision': entry['decision'], 'reason': entry['reason'],
                                  'static_status': 'incomplete', 'fixture_verified': True,
                                  'runtime_success_claimed': False, 'external_execution': 'not_run'}
    action, _ = candidate_call(entry['after_code'])
    new.update(ibl_code=entry['after_code'], nodes=action.split(':')[0], signature='', returns='Record')
    for key, value in RESET.items():
        if key in row:
            new[key] = value
    if 'updated_at' in row:
        new['updated_at'] = now()
    new['provenance'] = (json.dumps(provenance, ensure_ascii=False)
                         if entry['origin'] == DB_ORIGIN else provenance)
    if entry['origin'] != DB_ORIGIN or 'edition' in row:
        new['edition'] = 2
    return new


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.corpus-review-tmp')
    try:
        with temporary.open('w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_rows(root, entries, review_hash, indexer, journal, guard=lambda: None):
    conn = indexer._get_vec_connection()
    if conn is None:
        raise ValueError('벡터 연결 실패 — 원본 변경 없음')
    try:
        files, rows = load_sources(root, entries, conn)
        pending = pending_rows(entries, rows)
        db_entries = [e for e in pending if e['origin'] == DB_ORIGIN]
        vectors = indexer._generate_embeddings_batch([
            indexer._prepare_search_text(rows[(DB_ORIGIN, e['row_id'])]['intent'], e['after_code'])
            for e in db_entries]) if db_entries else []
        if len(vectors) != len(db_entries):
            raise ValueError('벡터 준비 실패 — 원본 변경 없음')
        guard()
        journal.update(state='prepared', pending=len(pending))
        atomic_json(journal['path'], {k: v for k, v in journal.items() if k != 'path'})
        conn.execute('BEGIN IMMEDIATE')
        files, rows = load_sources(root, entries, conn)
        if pending_rows(entries, rows) != pending:
            raise ValueError('준비 중 코드 변경 — 재검토 필요')
        for e, vector in zip(db_entries, vectors):
            current = rows[(DB_ORIGIN, e['row_id'])]
            revised = upgraded(current, e, review_hash)  # latest live statistics, under write lock
            columns = ['ibl_code', 'nodes', 'signature', 'returns', 'provenance', 'updated_at', *RESET]
            conn.execute('UPDATE ibl_examples SET ' + ','.join(k + '=?' for k in columns) + ' WHERE id=?',
                         [revised[k] for k in columns] + [e['row_id']])
            conn.execute('DELETE FROM ibl_examples_vec WHERE rowid=?', (e['row_id'],))
            conn.execute('INSERT INTO ibl_examples_vec(rowid,embedding) VALUES (?,?)', (e['row_id'], vector))
            actual = conn.execute('SELECT embedding FROM ibl_examples_vec WHERE rowid=?', (e['row_id'],)).fetchone()[0]
            if bytes(actual) != bytes(vector):
                raise ValueError('행별 벡터 내용 불일치')
        conn.execute("INSERT INTO ibl_examples_fts(ibl_examples_fts, rank) VALUES ('integrity-check', 1)")
        conn.commit()
        journal.update(state='db_committed', db_applied=len(db_entries))
        atomic_json(journal['path'], {k: v for k, v in journal.items() if k != 'path'})
        applied_files = 0
        for origin in files:
            path = file_path(root, origin)
            raw = path.read_bytes()
            data = json.loads(raw)
            targets = [e for e in entries if e['origin'] == origin]
            by_key = {(origin, i): r for i, r in enumerate(data)}
            changes = pending_rows(targets, by_key)
            for e in changes:
                data[e['row_id']] = upgraded(data[e['row_id']], e, review_hash)
            if changes:
                if path.read_bytes() != raw:
                    raise ValueError('학습 파일 동시 변경 — 재실행하여 병합 필요')
                atomic_json(path, data)
                applied_files += len(changes)
        _, current = load_sources(root, entries, conn)
        if pending_rows(entries, current):
            raise ValueError('미적용 행이 남았습니다. 같은 검토 원장으로 재실행하세요.')
        journal.update(state='applied', json_applied=applied_files, pending=0,
                       vector_content_verified=len(db_entries), fts_integrity='ok')
        atomic_json(journal['path'], {k: v for k, v in journal.items() if k != 'path'})
        return {k: v for k, v in journal.items() if k != 'path'}
    except BaseException:
        conn.rollback()  # only uncommitted DB changes; committed stages roll forward on retry
        raise
    finally:
        conn.close()


def check_inputs(root, hashes):
    if not hashes:
        raise ValueError('검토한 사전·컴파일러·핸들러 지문이 필요합니다.')
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != expected:
            raise ValueError(f'검토한 구현/계약 변경: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = args.review.read_bytes()
    review = json.loads(raw)
    entries = review['rows']
    check_inputs(ROOT, review.get('inputs_sha256'))
    base = ROOT / review['snapshot']
    from audit_ibl_corpus_v2 import frozen_registry, rows_from_snapshot
    contracts, definitions, availability, problems = frozen_registry(base, rows_from_snapshot(base))
    proofs = {}
    for entry in entries:
        if entry['decision'] == 'hold':
            continue
        before, after, decision = entry['before_code'], entry['after_code'], entry['decision']
        identity = sha(before + '\n' + after + '\n' + decision)
        if identity not in proofs:
            action, _ = literal_call(before)
            proofs[identity] = prove(before, after, contracts[action], decision)
    with connect(ROOT / 'data/ibl_usage.db') as conn:
        conn.row_factory = sqlite3.Row
        _, rows = load_sources(ROOT, entries, conn)
        pending = pending_rows(entries, rows)
    report = {'rows': len(entries), 'groups': review['groups'], 'review_sha256': sha(raw),
              'decisions': dict(Counter(e['decision'] for e in entries)), 'pending': len(pending),
              'programs_verified': len(proofs), 'fixture_cases': sum(len(p['cases']) for p in proofs.values()),
              'external_calls': 0, 'static_status': 'incomplete', 'applied': False}
    dump(args.review.parent / 'proofs.json', proofs)
    dump(args.review.parent / 'preview.json', report)
    if args.apply and pending:
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from ibl_usage_db import IBLUsageDB
        indexer = object.__new__(IBLUsageDB)
        if not indexer._load_model_sync():
            raise ValueError('로컬 모델 준비 실패')
        dest = snapshot()
        dump(dest / 'leaf_review/review.json', review)
        journal = {'path': dest / 'leaf_review/journal.json', 'review_sha256': sha(raw),
                   'backup': str(dest.relative_to(ROOT)), 'state': 'starting'}
        result = apply_rows(ROOT, entries, sha(raw), indexer, journal,
                            guard=lambda: check_inputs(ROOT, review['inputs_sha256']))
        report.update(applied=True, pending=0, application=result)
        dump(args.review.parent / 'application.json', report)
    if args.apply:
        from ibl_usage_db import _tree_refresh
        topics = {rows[(e['origin'], e['row_id'])].get('topic', '') for e in entries
                  if e['origin'] == DB_ORIGIN and e['decision'] != 'hold'}
        _tree_refresh(*topics, strict=True)  # also retry after a committed DB/JSON stage
        report['tree_topics_refreshed'] = len(topics)
        dump(args.review.parent / 'latest_check.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
