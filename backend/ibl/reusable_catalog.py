"""Small contract cards for existing registered scripts and stored functions.

No new memory store: definitions stay in their owners. Search is deterministic,
bounded and optional; matching describes candidates, never proves suitability.
"""
import json
import math
from pathlib import Path

from recall_relevance import lexical_evidence, terms


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
    from workflow_store import _get_workflows_path
    from ibl_v2_ir import digest
    for path in _get_workflows_path().glob('*.yaml'):
        try:
            entry = yaml.safe_load(path.read_text()) or {}
            if entry.get('edition') != 2:
                continue
            contract = entry.get('capability_contract') if entry.get('source_hash') == digest(entry.get('code')) else None
            rows.append({'id': 'fn:' + entry['name'], 'description': entry.get('description', ''),
                         'call': '[fn:' + entry['name'] + ']{}', 'contract': contract,
                         'contract_known': bool(contract)})
        except (ValueError, KeyError, OSError, yaml.YAMLError):
            continue
    from ibl_v2_store import installed_definitions, describe
    installed = installed_definitions()
    for name in installed:
        if not any(row['id'] == 'fn:' + name for row in rows):
            rows.append({'id': 'fn:' + name, 'description': name,
                         'call': '[fn:' + name + ']{}', 'contract': None,
                         'contract_known': False, 'origin': 'installed'})
    from ibl_access import exposed_idiom_names
    exposed = exposed_idiom_names(allowed)
    # 실제 상시 블록에 실린 함수만 제외한다. 예산 밖의 함수·같은 이름의 스크립트는 남긴다.
    rows = [row for row in rows if not (
        row['id'].startswith('fn:') and row['id'][3:] in exposed)]
    found = ranked(query, rows, limit)
    # 선택된 배포 함수만 기존 컴파일러에서 계약을 얻는다. 별도 계약 사본은 없다.
    for row in found:
        if row.get('origin') == 'installed':
            definition = describe(row['id'][3:], allowed)
            row['contract'] = definition.get('callable_contract')
            row['contract_known'] = bool(row['contract'])
            if definition.get('error'):
                row['error'] = definition['error']
    return found
