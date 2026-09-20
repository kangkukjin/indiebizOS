"""통합 증류의 심층·공간 자료 준비와 무모델 저장 관문."""
import json
import os
import re
from pathlib import Path

from distill_receipts import fingerprint


def memory_modules():
    import sys
    path = str(Path(__file__).resolve().parents[2] / 'data/packages/installed/tools/memory')
    if path not in sys.path:
        sys.path.insert(0, path)
    import memory_db
    import memory_tree
    return memory_db, memory_tree


def _version(row):
    return fingerprint({k: row.get(k) for k in ('content', 'source_ref', 'node')})


def prepare_deep(job):
    from memory_evidence import durable_source_units
    units = durable_source_units(job['user_message'])
    if not any(u['eligible'] for u in units):
        return {'eligible': False, 'reason': 'no_user_fact_candidate'}
    db, tree = memory_modules()
    project, agent = job['project_path'], job['agent_id']
    known, allowed, omitted, queries = {}, [], [], []
    # 문맥 단위 검색. 불명확한 후보를 살리려고 별도 요약/판정 모델을 부르지 않는다.
    for i, unit in enumerate(units):
        if not unit['eligible']:
            continue
        context = '\n'.join(u['text'] for u in units[max(0, i-1):i+1])
        if len(queries) >= 8 or len(context) > 2000:
            omitted.append(unit['id'])
            continue
        hits = db.search(project, agent, query=context, limit=3)
        full = [db.read(project, agent, h['id'], touch=False) for h in hits]
        if any(not r for r in full):
            omitted.append(unit['id'])
            continue
        additions = {r['id']: {**r, 'version': _version(r)} for r in full}
        prospective = {**known, **additions}
        if len(json.dumps(prospective, ensure_ascii=False)) > 10000:
            omitted.append(unit['id'])
            continue
        known = prospective
        queries.append({'unit_id': unit['id'], 'existing_ids': list(additions)})
        allowed.append(unit['id'])
    mapping = tree.map_text(db._get_db_path(project, agent))
    if len(mapping) > 4000:
        mapping = '\n'.join(mapping.splitlines()[:30])
    return {'eligible': bool(allowed), 'units': units, 'allowed_ids': allowed,
            'omitted_ids': omitted, 'queries': queries, 'known': list(known.values()),
            'tree': mapping, 'reason': 'ready' if allowed else 'no_complete_comparison'}


def apply_deep(job, prepared, candidate, key):
    from memory_evidence import grounded_fact, select_units, unresolved_reference
    ids = candidate.get('user_source_ids')
    if (not isinstance(ids, list) or not ids
            or any(type(i) is not int or i not in prepared['allowed_ids'] for i in ids)):
        return {'status': 'rejected', 'reason': 'ineligible_user_source'}
    source = {'recorded_at': job['recorded_at'], 'timezone': job['timezone'],
              'episode_id': job.get('episode_id'), 'task': job.get('task_id'),
              'turn_id': job['turn_id'], 'candidate_key': key}
    fact = grounded_fact({**candidate, 'source_ids': ids}, prepared['units'],
                         json.dumps(source, ensure_ascii=False), durable_only=True)
    if not fact or unresolved_reference(select_units(ids, prepared['units'])):
        return {'status': 'rejected', 'reason': 'unresolved_user_fact'}
    db, tree = memory_modules()
    if db.body_noun_leak(fact['content']):
        return {'status': 'rejected', 'reason': 'body_internal_information'}
    if candidate.get('category') not in {'사용자선호', '사용자정보', '의사결정', '중요날짜'}:
        return {'status': 'rejected', 'reason': 'invalid_user_memory_category'}
    node = tree.norm_node(candidate.get('node', ''))
    if not node or len(node.split('/')) > 3:
        return {'status': 'rejected', 'reason': 'invalid_memory_branch'}
    relation = candidate.get('relation')
    known = {r['id']: r for r in prepared['known']}
    target = known.get(candidate.get('existing_id'))
    if relation in {'SAME', 'UPDATE', 'REPLACE'}:
        if not target or candidate.get('existing_version') != target['version']:
            return {'status': 'rejected', 'reason': 'unknown_relation_target'}
    elif relation != 'NEW' or candidate.get('existing_id') is not None:
        return {'status': 'rejected', 'reason': 'invalid_relation'}
    if relation == 'SAME':
        return {'status': 'same', 'id': target['id']}
    # 같은 배치/다른 턴과의 의미 중복은 모델 판단. 명백한 원문 중복은 코드가 차단.
    if relation == 'NEW' and any(fact['content'] == r['content'] for r in prepared['known']):
        return {'status': 'same', 'reason': 'identical_existing_fact'}
    project, agent = job['project_path'], job['agent_id']
    kwargs = dict(content=fact['content'], keywords=candidate.get('keywords', ''),
                  category=candidate.get('category', ''), node=node,
                  source_ref=fact['source_ref'], candidate_key=key)
    if relation == 'REPLACE':
        correction = candidate.get('correction_source_ids')
        if (not correction or any(type(i) is not int or i not in ids for i in correction)
                or candidate.get('explicit_correction') is not True):
            return {'status': 'rejected', 'reason': 'no_explicit_user_correction'}
        # 의미상 정정 여부는 통합 판단이 소유. 원문·버전·옛 출처는 기계가 고정.
        source = json.loads(fact['source_ref'])
        source['superseded'] = {k: target[k] for k in ('id', 'content', 'source_ref', 'version')}
        kwargs['source_ref'] = json.dumps(source, ensure_ascii=False)
        applied = db.update(project, agent, target['id'], expected_content=target['content'],
                            expected_version=target['version'], **kwargs)
        return {'status': 'saved' if applied else 'deferred', 'id': target['id'],
                'reason': 'replaced' if applied else 'version_conflict_terminal'}
    if relation == 'UPDATE':
        kwargs['related_id'] = target['id']
        kwargs['expected_version'] = target['version']
        source = json.loads(fact['source_ref'])
        source['related_memory_id'] = target['id']
        kwargs['source_ref'] = json.dumps(source, ensure_ascii=False)
    ident = db.save(project, agent, **kwargs)
    return {'status': 'saved', 'id': ident}


_ADDRESS = re.compile(r'https?://[^\s<>"\'`{}\[\],]+|(?<![\w:/])/(?:[^\s<>"\'`{}\[\],]+)')


def _addresses(text):
    found = []
    for match in _ADDRESS.finditer(text):
        loc = match.group().rstrip(').;:')
        if loc.startswith('/') and not os.path.exists(loc):
            continue
        if loc not in found:
            found.append(loc)
    return found


def prepare_forage(job):
    import forage_memory as fm
    from ibl_honesty import truncation_evidence, completion_evidence
    from runtime_utils import detect_body
    from memory_evidence import durable_source_units
    if (detect_body().get('profile') or 'pc') == 'phone':
        return {'eligible': False, 'reason': 'phone_surface'}
    observations, addresses, omitted = [], {}, []
    for index, tc in enumerate(job.get('tool_calls') or [], 1):
        if not isinstance(tc, dict) or tc.get('success') is not True or tc.get('result') is None:
            continue
        if (tc.get('input') or {}).get('check') or '_t0' in tc:
            continue
        raw = json.dumps(tc['result'], ensure_ascii=False, default=str)
        cuts = (tc.get('evidence') or truncation_evidence(tc['result']) or {}).get('truncations') or []
        if len(raw) > 8000 or completion_evidence(tc['result']) or any(
                c.get('scope') in {'source', 'unknown'} for c in cuts):
            omitted.append(index)
            continue
        locs = _addresses(raw + '\n' + json.dumps(tc.get('input'), ensure_ascii=False))
        if not locs or len(observations) >= 6:
            continue
        observations.append({'id': index, 'source_kind': 'tool_observation', 'input': tc.get('input'),
                             'result': tc['result'], 'addresses': locs, 'sha256': fingerprint(tc['result'])})
        for loc in locs:
            addresses[loc] = {'body': fm.canonical_body('web' if loc.startswith('http') else 'mac', loc),
                              'mtime_ns': os.stat(loc).st_mtime_ns if loc.startswith('/') else None}
    # 명시적인 공간 선언도 원문에 주소가 있어야 한다. AI 답변은 주소 근거가 아니다.
    declarations = []
    if job.get('write_deep'):
        for u in durable_source_units(job['user_message']):
            locs = _addresses(u['text']) if u['eligible'] else []
            if locs and len(declarations) < 3:
                declarations.append({**u, 'addresses': locs})
                for loc in locs:
                    addresses[loc] = {'body': fm.canonical_body('web' if loc.startswith('http') else 'mac', loc),
                                      'mtime_ns': os.stat(loc).st_mtime_ns if loc.startswith('/') else None}
    if not addresses:
        return {'eligible': False, 'reason': 'no_actual_spatial_observation'}
    known = {}
    conn = fm._connect()
    try:
        for loc, info in addresses.items():
            parent = str(Path(loc).parent) if loc.startswith('/') else loc.rsplit('/', 1)[0]
            rows = conn.execute('SELECT * FROM forage_map WHERE body=? AND locus IN (?,?) ORDER BY id DESC LIMIT 9',
                                (info['body'], loc, parent)).fetchall()
            if len(rows) > 8:
                return {'eligible': False, 'reason': 'spatial_comparison_truncated'}
            for row in rows:
                item = dict(row)
                item['version'] = fingerprint({k: item[k] for k in ('claim', 'provenance', 'surface_flag')})
                known[item['id']] = item
    finally:
        conn.close()
    if len(json.dumps(known, ensure_ascii=False)) > 12000:
        return {'eligible': False, 'reason': 'spatial_comparison_budget'}
    return {'eligible': True, 'observations': observations, 'declarations': declarations,
            'addresses': addresses, 'known': list(known.values()), 'omitted_ids': omitted}


def apply_forage(job, prepared, candidate, key):
    import forage_memory as fm
    from cognitive_distill import CognitiveDistillMixin
    loc, body = candidate.get('locus'), candidate.get('body')
    info = prepared['addresses'].get(loc)
    if not info or fm.canonical_body(body or '', loc) != info['body']:
        return {'status': 'rejected', 'reason': 'ungrounded_address'}
    obs = candidate.get('observation_ids') or []
    users = candidate.get('user_source_ids') or []
    sources = [r for r in prepared['observations'] if r['id'] in obs]
    declarations = [r for r in prepared['declarations'] if r['id'] in users]
    if (any(type(i) is not int for i in obs + users) or len(sources) != len(set(obs))
            or len(declarations) != len(set(users)) or not sources + declarations
            or not any(loc in r['addresses'] for r in sources + declarations)):
        return {'status': 'rejected', 'reason': 'missing_actual_observation'}
    claim = candidate.get('claim', '')
    kind = candidate.get('kind')
    if (not claim or len(claim) > 400 or kind not in fm._MAP_KINDS
            or candidate.get('prior_class') not in fm._PRIOR_CLASSES
            or candidate.get('generalizes') is not True
            or CognitiveDistillMixin._is_self_narration(CognitiveDistillMixin, claim, loc)):
        return {'status': 'rejected', 'reason': 'invalid_spatial_claim'}
    if kind == 'dead_branch':
        # 검색 실패/미발견으로 부재를 일반화하지 않는다. v1 자동 부재 기억은 저장하지 않는다.
        return {'status': 'rejected', 'reason': 'absence_not_proven'}
    from distill_receipts import lookup
    conn = fm._connect()
    try:
        already_written = lookup(conn, key)
    finally:
        conn.close()
    if not already_written and loc.startswith('/') and (
            not os.path.exists(loc) or os.stat(loc).st_mtime_ns != info['mtime_ns']):
        return {'status': 'deferred', 'reason': 'location_changed_terminal'}
    relation = candidate.get('relation')
    target = next((r for r in prepared['known'] if r['id'] == candidate.get('existing_id')), None)
    if relation in {'SAME', 'UPDATE'} and (not target or candidate.get('existing_version') != target['version']):
        return {'status': 'rejected', 'reason': 'unknown_spatial_version'}
    if target and (target['locus'] != loc or target['body'] != info['body']):
        return {'status': 'rejected', 'reason': 'unrelated_spatial_target'}
    if relation == 'SAME' and target:
        return {'status': 'same', 'id': target['id']}
    if (relation not in {'NEW', 'UPDATE'} or (relation == 'UPDATE' and not target)
            or (relation == 'NEW' and candidate.get('existing_id') is not None)):
        return {'status': 'rejected', 'reason': 'invalid_spatial_relation'}
    if any(r['locus'] == loc and r['claim'] == claim for r in prepared['known']):
        return {'status': 'same', 'reason': 'identical_spatial_claim'}
    provenance = {'job_key': job['job_key'], 'candidate_key': key,
                  'observed': [{'id': r['id'], 'sha256': r['sha256']} for r in sources],
                  'user_declarations': declarations, 'formed_at': job['recorded_at']}
    result = fm.note_map(body=info['body'], locus=loc, kind=kind, claim=claim,
                         prior_class=candidate['prior_class'], provenance=provenance,
                         generalizes=True, candidate_key=key, expected_target=target,
                         mark_related_surface=candidate.get('surface') is True)
    return {'status': 'saved' if result.get('success') else 'rejected',
            'id': result.get('id'), 'reason': result.get('error', '')}
