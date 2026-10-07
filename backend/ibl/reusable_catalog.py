"""Small contract cards for existing registered scripts and stored functions.

No new memory store: definitions stay in their owners. Search is deterministic,
bounded and optional; matching describes candidates, never proves suitability.
"""
import json
import re
from pathlib import Path


def ranked(query, entries, limit=3):
    words = {w.casefold() for w in re.findall(r'[\w]+', query or '') if len(w) >= 2}
    if not words:
        return []
    scored = []
    for row in entries:
        text = (str(row.get('id', '')) + ' ' + str(row.get('description', ''))).casefold()
        score = sum(len(w) for w in words if w in text)
        if score >= 3:
            scored.append((score, row))
    return [row for _, row in sorted(scored, key=lambda pair: (-pair[0], str(pair[1]['id'])))[:limit]]


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
