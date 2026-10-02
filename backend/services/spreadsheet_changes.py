"""Conditional inverse edits and repeatable imports through the active engine.

No workbook is rewritten here. A proposal still passes the session fence and
plugin comparison immediately before mutation. Structural ambiguity is rejected.
"""
import json
import time
from copy import deepcopy
from xml.etree.ElementTree import tostring

from defusedxml.ElementTree import fromstring
from office_sessions import DocumentConflict, DocumentUnsupported
from office_store import digest
import spreadsheet_files as files


def structure(data):
    """Fingerprint non-value structure, including filters, row layout and styles.

Cached results and cell contents can change without invalidating an inverse.
Creating/removing a cell is deliberately conservative: request a new comparison.
"""
    parts = []
    with files.archive(data) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith('xl/worksheets/') and name.endswith('.xml'):
                root = fromstring(archive.read(name))
                for node in root.iter(files.NS + 'c'):
                    node.attrib.pop('t', None)
                    node.attrib.pop('s', None)  # Outside-range formatting is preserved, not reverted.
                    for child in list(node):
                        node.remove(child)
                parts.append((name, tostring(root).decode()))
            elif (name == 'xl/workbook.xml' or name.startswith(('xl/tables/', 'xl/_rels/'))):
                root = fromstring(archive.read(name))
                for tag in ('calcPr', 'bookViews'):
                    for node in root.findall(files.NS + tag):
                        root.remove(node)
                parts.append((name, tostring(root).decode()))
    return digest(json.dumps(parts, ensure_ascii=False).encode())


def cells(projection):
    return [{'value': c['entered_value'], 'formula': c['formula'],
             'type': c['value_type'], 'style': c['style_id']} for c in projection['items']]


def same_cells(left, right):
    # vj-ok: optimistic concurrency compares serialized evidence fingerprints,
    # not numeric/relational equality; even an equivalent spelling is a human edit.
    def fingerprint(value):
        return digest(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
    return fingerprint(left) == fingerprint(right)


def preflight(app, document_id, operation_id, session_id, client_id, epoch, expected):
    """Check a newly captured engine file before consuming a queued edit.

    XML-only changes (filters, validation, protection) may not alter cell values.
    They must still invalidate a proposal based on an earlier session revision.
    """
    with app.store.lock():
        _, session = app._session(document_id, session_id, client_id, epoch, expected)
        op = app.store.get('operation', operation_id)
        if (op['document_id'] != document_id or op.get('session_id') != session_id
                or op.get('epoch') != epoch or op.get('status') != 'queued'):
            raise DocumentConflict('다른 세션이거나 대기 중이 아닌 변경입니다')
        p = app.store.get('sheet_proposal', op['proposal_id'])
        snap = app.store.get('sheet_snapshot', p['snapshot_id'])
        if snap['blob'] != session['blob'] or snap['session_revision'] != expected:
            raise DocumentConflict('제안 이후 셀·행·시트·필터 상태가 바뀌었습니다. 다시 읽고 제안하세요')
        return {'ready': True}


def history(app, document_id):
    app._doc(document_id)
    return [{'operation_id': op['id'], 'proposal_id': op.get('proposal_id'),
             'status': op.get('status'), 'result': op.get('result')}
            for op in app.store.list('operation')
            if op.get('document_id') == document_id and op.get('proposal_id')]


def inverse(app, document_id, operation_id, snapshot_id):
    app._doc(document_id)
    operation = app.store.get('operation', operation_id)
    if operation['document_id'] != document_id:
        raise PermissionError('다른 자료의 변경입니다')
    if operation.get('status') != 'completed' or not operation.get('result', {}).get('applied'):
        raise DocumentConflict('완료된 변경만 취소할 수 있습니다')
    proposal = app.store.get('sheet_proposal', operation['proposal_id'])
    after_id = operation.get('result', {}).get('snapshot_id')
    if not after_id:
        raise DocumentUnsupported('적용 직후 스냅샷이 없는 과거 변경입니다. 범위를 직접 비교하세요')
    after = app.store.get('sheet_snapshot', after_id)
    now = app.store.get('sheet_snapshot', snapshot_id)
    original = app.store.get('sheet_snapshot', proposal['snapshot_id'])
    if any(s['document_id'] != document_id for s in (after, now, original)):
        raise PermissionError('다른 자료의 스냅샷입니다')
    if after['session_id'] != now['session_id'] or after['engine_epoch'] != now['engine_epoch']:
        raise DocumentConflict('편집 세대가 바뀌어 취소 대상을 확정할 수 없습니다')
    if structure(app.store.bytes(after['blob'])) != structure(app.store.bytes(now['blob'])):
        raise DocumentConflict('행·시트·필터·서식 구조가 바뀌었습니다. 자동 취소 대신 범위를 비교하세요')
    params = (document_id, proposal['sheet_id'], proposal['range'])
    def read(sid):
        return app.read(params[0], sid, params[1], params[2])
    current, applied, before = read(snapshot_id), read(after_id), read(original['id'])
    if not same_cells(cells(current), cells(applied)):
        raise DocumentConflict('변경 범위에 후속 편집이 있습니다. 사람의 변경을 보존했습니다')
    # The inverse restores only the affected range, never an entire prior file.
    x1, y1, x2, y2 = files.bounds(proposal['range'])
    width = x2 - x1 + 1
    restores = [{'value': c['entered_value'], 'formula': c['formula']} for c in before['items']]
    values = [restores[i:i + width] for i in range(0, len(restores), width)]
    if any(c['value_type'] == 'error' and not c['formula'] for c in before['items']):
        raise DocumentUnsupported('오류 리터럴 복원은 편집기에서 확인하세요')
    p = app.propose(document_id, snapshot_id, proposal['sheet_id'], proposal['range'],
                    [[None] * width for _ in range(y2 - y1 + 1)])
    p.update(kind='restore_cells', values=values, inverse_of=operation_id)
    app.store.put('sheet_proposal', p)
    return p


def imports(app, document_id):
    app._doc(document_id)
    return [r for r in app.store.list('sheet_import') if r['target_resource_id'] == document_id]


def refresh(app, document_id, recipe_id, source_resource_id, expected_revision, snapshot_id):
    """Re-run the recorded CSV types, compare the old area, queue an engine proposal."""
    import spreadsheet_imports as csv_imports
    from datetime import date
    from openpyxl.utils.datetime import to_excel, CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900
    app._doc(document_id)
    recipe = app.store.get('sheet_import', recipe_id)
    if recipe['target_resource_id'] != document_id:
        raise PermissionError('다른 통합문서의 가져오기 작업입니다')
    source, data = csv_imports.source(app, source_resource_id, expected_revision)
    rows, converted, types, errors = csv_imports.prepare(data, recipe['encoding'], recipe['delimiter'],
        recipe['quotechar'], recipe['header'], recipe['types'])
    if errors:
        raise ValueError(f'전체 {len(rows)}행 검사에서 {len(errors)}개 오류가 있습니다. 기존 영역을 유지했습니다')
    width = len(types)
    height = max(recipe['rows_imported'], len(converted))
    address = 'A1:' + files.cell_name(width, height)
    files.bounds(address)
    now = app.read(document_id, snapshot_id, recipe.get('sheet_id', '1'), address)
    baseline = recipe.get('baseline_blob')
    if not baseline:
        raise DocumentUnsupported('갱신 기준이 없는 과거 가져오기입니다. 새로 가져온 뒤 갱신하세요')
    previous = files.projection(app.store.bytes(baseline), recipe.get('sheet_id', '1'), address)
    if not same_cells(cells(previous), cells(now)):
        raise DocumentConflict('이전 가져오기 영역 또는 확장 영역에 사람의 편집이 있습니다. 비교 후 다시 시도하세요')
    epoch = CALENDAR_MAC_1904 if now['date_system'] == '1904' else CALENDAR_WINDOWS_1900
    values = [[to_excel(v, epoch) if isinstance(v, date) else v for v in row] for row in converted]
    values += [[None] * width for _ in range(height - len(values))]
    proposal = app.propose(document_id, snapshot_id, recipe.get('sheet_id', '1'), address, values)
    proposal['import_refresh'] = {'recipe_id': recipe_id, 'source_resource_id': source_resource_id,
        'source_revision_id': expected_revision, 'source_sha256': source['source_sha256'],
        'rows_imported': len(rows), 'cells_imported': sum(len(r) for r in rows), 'failure_count': 0}
    app.store.put('sheet_proposal', proposal)
    return proposal


def finish(app, operation, result):
    """Advance an import baseline only after the engine's confirmed capture."""
    if not operation.get('proposal_id') or not result.get('applied') or not result.get('snapshot_id'):
        return
    p = app.store.get('sheet_proposal', operation['proposal_id'])
    snapshot = app.store.get('sheet_snapshot', result['snapshot_id'])
    if snapshot['document_id'] != operation['document_id'] or snapshot['session_id'] != operation['session_id']:
        raise DocumentConflict('변경 영수증의 스냅샷이 다른 자료 또는 세션입니다')
    current = app.read(operation['document_id'], snapshot['id'], p['sheet_id'], p['range'])
    expected = []
    for row in p['values']:
        for value in row:
            if p['kind'] == 'restore_cells':
                expected.append(value)
            elif p['kind'] == 'set_formulas':
                expected.append({'value': None, 'formula': value})
            else:
                expected.append({'value': value, 'formula': None})
    actual = [{'value': c['entered_value'], 'formula': c['formula']} for c in current['items']]
    if not same_cells(expected, actual):
        # A human may edit between plugin return and capture. Do not label that
        # capture as our post-image or silently advance the import baseline.
        result.pop('snapshot_id', None)
        result['capture_warning'] = '적용 직후 후속 편집이 감지됐습니다. 자동 취소·가져오기 기준을 갱신하지 않았습니다'
        return
    info = p.get('import_refresh')
    if info:
        recipe = app.store.get('sheet_import', info['recipe_id'])
        if recipe.get('last_operation_id') == operation['id']:
            return
        recipe.setdefault('runs', []).append({**deepcopy(info), 'operation_id': operation['id']})
        recipe['last_operation_id'] = operation['id']
        recipe.update({k: v for k, v in info.items() if k != 'recipe_id'})
        recipe.update(baseline_blob=snapshot['blob'], refreshed_at=time.time())
        app.store.put('sheet_import', recipe)
