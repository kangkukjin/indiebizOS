"""Small contract cards for existing registered scripts and stored functions.

No new memory store: definitions stay in their owners. Search is deterministic,
bounded and optional; matching describes candidates, never proves suitability.
"""
import json
import re
from pathlib import Path


def ranked(query, entries, limit=3):
    query = (query or '').strip().casefold()
    words = {w.casefold() for w in re.findall(r'[\w]+', query or '') if len(w) >= 2}
    if not query:
        return []
    scored = []
    for row in entries:
        sid = str(row.get('id', '')).casefold()
        exact = query in {sid, sid.partition(':')[2]}
        text = sid + ' ' + str(row.get('description', '')).casefold()
        score = sum(len(w) for w in words if w in text)
        # 허용한 두 글자 검색어를 점수 하한에서 다시 버리지 않는다.
        # 정확명은 길이와 무관하게 우선하며, 한 글자의 광범위 부분 검색은 피한다.
        if exact or score >= 2:
            scored.append((exact, score, row))
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
    return ranked(query, rows, limit)
