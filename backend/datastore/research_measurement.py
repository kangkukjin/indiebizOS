"""완료 연구의 판본·품질·비용 연결. 오프라인 읽기 전용이며 새 모델을 호출하지 않는다."""
import hashlib
import json
import sqlite3
from pathlib import Path

from common.value_semantics import numeric_value
from model_call_context import billable_identity, summarize_usage


def aggregate(database, episode_id):
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        found = conn.execute('SELECT id,task_id,run_id,started_at,ended_at,total_ms '
                             'FROM episode_log WHERE id=?', (episode_id,)).fetchone()
        if found is None:
            raise ValueError('측정할 에피소드가 없습니다')
        episode = dict(found)
        rows = [dict(r) for r in conn.execute("SELECT * FROM trajectory_event WHERE kind LIKE 'model.%'")]
    for row in rows:
        row['data'] = json.loads(row['data'])
    # Ancestry joins use persisted identities, never timing proximity or prose.
    selected = [r for r in rows if r['episode_id'] == episode_id]
    ids = {r['data'].get('call_id') for r in selected} - {None}
    runs = {episode['run_id']} - {None, ''}
    while True:
        joined = [r for r in rows if r['episode_id'] == episode_id or r['run_id'] in runs
                  or r['parent_run_id'] in runs or r['data'].get('parent_call_id') in ids
                  or r['data'].get('call_id') in ids]
        next_ids = ids | {r['data'].get('call_id') for r in joined} - {None}
        next_runs = runs | {r['run_id'] for r in joined} - {None, ''}
        if next_ids == ids and next_runs == runs:
            selected = joined
            break
        ids, runs = next_ids, next_runs
    started, finished, billed = {}, {}, set()
    seen, unique, duplicates, conflicts = {}, [], 0, []
    for row in selected:
        data, kind = row['data'], row['kind']
        cid = data.get('call_id')
        if kind == 'model.call_started':
            started[cid] = data
        elif kind == 'model.call_finished':
            finished[cid] = data
        if kind != 'model.usage' or data.get('accounting') != 'billable_usage':
            continue  # response snapshots and boundary timings are not new charges.
        key = billable_identity(data) or (row['run_id'], row['event_seq'])
        charges = {k: data.get(k) for k in ('input', 'output', 'cache_read', 'cache_create', 'reasoning')}
        if key in seen:
            if seen[key] == charges:
                duplicates += 1
            else:
                conflicts.append({'identity': key, 'first': seen[key], 'other': charges})
            continue
        seen[key] = charges
        unique.append(data)
        if cid:
            billed.add(cid)
    normalized, roles, invalid = [], {}, []
    for row in unique:
        clean = {k: row[k] for k in ('call_id', 'parent_call_id', 'usage_id', 'round_index', 'provider', 'model', 'role') if k in row}
        clean['measured'] = True
        for key in ('input', 'output', 'cache_read', 'cache_create', 'reasoning'):
            number = numeric_value(row.get(key))
            if number is None or number < 0 or number != int(number):
                clean[key] = None
                invalid.append({'call_id': row.get('call_id'), 'field': key})
                continue
            clean[key] = int(number)
        normalized.append(clean)
        roles.setdefault(row.get('role', 'unknown'), []).append(clean)
    summary = summarize_usage(normalized)
    measured = {k: summary[k] for k in ('input', 'output', 'cache_read', 'cache_create', 'reasoning')}
    roles = {key: {k: v for k, v in summarize_usage(value).items() if k != 'calls'} for key, value in roles.items()}
    unknown = [{'call_id': cid, 'role': data.get('role'), 'phase': data.get('phase'),
                'reason': 'finished_without_usage' if cid in finished else 'unfinished_call'}
               for cid, data in started.items() if cid not in billed]
    return {'episode': episode, 'joined_runs': sorted(runs), 'billable_records': len(unique),
            'duplicates_removed': duplicates, 'conflicts': conflicts, 'measured': dict(measured),
            'input_plus_output': measured['input'] + measured['output']
                if measured['input'] is not None and measured['output'] is not None else None,
            'roles': roles, 'calls': normalized,
            'calls_started': len(started), 'calls_finished': len(finished), 'unmeasured_calls': unknown,
            'unattributed_usage': sum(not r.get('call_id') for r in unique), 'invalid_fields': invalid,
            'usage_partial': [r['data'].get('call_id') for r in selected if r['data'].get('usage_partial')],
            'complete': False,
            'limitations': ['Unbound subprocess experiments cannot be assigned without call/run identities.',
                            'Input includes cache; output includes reasoning; neither subset is added again.',
                            'Only episode.total_ms is wall time; parallel call latencies are not summed.',
                            'Missing usage and conflicting records are not replaced with zero.'],
            'user_corrections': None}


def measure(database, episode_id, artifact, *, task, variant, review=None, conditions=None):
    """사람 검토는 같은 답변 지문일 때만 연결한다. 미측정은 None으로 보존한다."""
    path = Path(artifact).resolve()
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if not task or not variant:
        raise ValueError('비교 과제와 조건 이름이 필요합니다')
    if review is not None:
        if review.get('artifact_sha256') != checksum:
            raise ValueError('사람 검토가 다른 산출물 판본을 가리킵니다')
        for key in ('active_review_seconds', 'active_edit_seconds', 'critical_claim_changes'):
            value = review.get(key)
            if value is not None and (numeric_value(value) is None or numeric_value(value) < 0):
                raise ValueError(f'{key}는 0 이상의 관측값 또는 null이어야 합니다')
    cost = aggregate(database, episode_id)
    return {'schema': 1, 'task': task, 'variant': variant, 'conditions': conditions,
            'artifact': {'path': str(path), 'sha256': checksum, 'bytes': len(raw)},
            'cost': cost, 'human_review': review,
            'usable_result_elapsed_ms': (review or {}).get('usable_result_elapsed_ms'),
            'quality': (review or {}).get('quality'),
            'missing': [name for name, value in {
                'quality': (review or {}).get('quality'), 'human_review': review,
                'usable_result_elapsed_ms': (review or {}).get('usable_result_elapsed_ms'),
                'matched_conditions': conditions}.items() if value is None],
            'effect_established': False}
