"""Small contract cards for existing registered scripts and stored functions.

No new memory store: definitions stay in their owners. Search is deterministic,
bounded and optional; matching describes candidates, never proves suitability.
"""
import json
import math
from pathlib import Path

from recall_relevance import lexical_evidence, terms


def discovery_payload(rows, max_chars=5000):
    """소개 예산은 상세를 접는다. 긴 계약이 검색된 이름까지 지우지 않게 한다.

    원 계약·가이드 절은 통째로 넣거나 생략한다. 부분 계약을 만들어 조건을 잃지 않으며,
    contract_known(정의 존재)과 details_omitted(이번 소개 생략)는 별개다.
    """
    from guide_registry import callable_control_briefs

    payload = {'candidates': [], 'control_briefs': []}

    def fits():
        return len(json.dumps(payload, ensure_ascii=False)) <= max_chars

    sources = []
    for row in rows:
        kind, _, name = row['id'].partition(':')
        inspect = ({'describe': [row['id']]} if kind == 'fn' else
                   {'code': '[self:script]' + json.dumps({'op': 'list', 'id': name}, ensure_ascii=False)})
        card = {'id': row['id'], 'inspect': inspect,
                'contract_known': row.get('contract_known', False),
                'details_omitted': [key for key in ('description', 'contract', 'call') if row.get(key)]}
        if row.get('function_ref'):
            card['function_ref'] = row['function_ref']
        if row.get('error'):
            # 조회 거절은 소개 예산 때문에 실행 가능한 후보로 바뀌지 않는다.
            card['error'] = row['error']
        payload['candidates'].append(card)
        if not fits():
            payload['candidates'].pop()
            break
        sources.append(row)

    # 내부 Record의 실제 사용법·검증·복구 조건을 담은 짧은 절을 긴 계약보다 먼저 확보한다.
    for brief in callable_control_briefs(row['id'] for row in sources if not row.get('error')):
        payload['control_briefs'].append(brief)
        if not fits():
            payload['control_briefs'].pop()

    for key in ('description', 'contract', 'call'):
        for card, row in zip(payload['candidates'], sources):
            if key not in card['details_omitted']:
                continue
            card[key] = row[key]
            card['details_omitted'].remove(key)
            if not fits():
                del card[key]
                card['details_omitted'].append(key)
    return payload


def ranked(query, entries, limit=3):
    query = (query or '').strip().casefold()
    if not query:
        return []
    scored = []
    for row in entries:
        sid = str(row.get('id', '')).casefold()
        name = sid.partition(':')[2] or sid
        exact = query in {sid, name}
        named = len(name) >= 2 and name in terms(query)
        text = sid + ' ' + str(row.get('description', '')).casefold()
        score = lexical_evidence(query, text)
        if exact or named or score:
            # 긴 인자·결과 설명이 우연한 겹침을 많이 모아 짧고 적합한 부품을 밀어내지 않게 한다.
            score /= 1 + math.log1p(len(terms(text)))
            scored.append((exact or named, score, row))
    ordered = sorted(scored, key=lambda item: (-item[0], -item[1], str(item[2]['id'])))
    return [row for _, _, row in ordered[:limit]]



def candidates(query, limit=3):
    import principal
    if not principal.is_owner():
        return []
    import yaml
    from runtime_utils import get_base_path
    from thread_context import get_allowed_nodes, get_repair_workspace
    allowed = get_allowed_nodes()
    if allowed is not None and 'self' not in allowed:
        return []
    root = Path(get_repair_workspace() or get_base_path()) / 'data/scripts'
    file = root / 'registry.yaml'
    registry = yaml.safe_load(file.read_text()) if file.is_file() else {}
    rows = []
    for sid, entry in (registry or {}).items():
        if not (root / entry.get('file', '')).is_file():
            continue
        contract = entry.get('callable_contract')
        rows.append({'id': 'script:' + sid, 'description': entry.get('description', ''),
                     'call': '[self:script]' + json.dumps({'op': 'run', 'id': sid, 'args': {}}, ensure_ascii=False),
                     'contract': contract, 'contract_known': bool(contract)})
    import function_store
    from ibl_v2_store import describe
    for entry in function_store.snapshot()['records'].values():
        if entry.get('state') != 'active' or entry.get('problem'):
            continue
        rows.append({'id': 'fn:' + entry['name'], 'description': entry.get('description', ''),
                     'call': '[fn:' + entry['name'] + ']{}', 'contract': None,
                     'contract_known': False, 'function_ref': function_store.reference(entry)})
    from ibl_access import exposed_idiom_names
    exposed = exposed_idiom_names(allowed)
    # 실제 상시 블록에 실린 함수만 제외한다. 예산 밖의 함수·같은 이름의 스크립트는 남긴다.
    rows = [row for row in rows if not (
        row['id'].startswith('fn:') and row['id'][3:] in exposed)]
    found = ranked(query, rows, limit)
    # 저장 원문의 지문만 같아도 하위 부품은 바뀔 수 있다. 선택된 함수는 출처와
    # 무관하게 실행기가 해소하는 현재 정의·권한·의존성으로 계약을 다시 얻는다.
    for row in found:
        if row['id'].startswith('fn:'):
            definition = describe(row['id'][3:], allowed)
            row['contract'] = definition.get('callable_contract')
            row['contract_known'] = bool(row['contract'])
            if definition.get('error'):
                row['error'] = definition['error']
    return found
