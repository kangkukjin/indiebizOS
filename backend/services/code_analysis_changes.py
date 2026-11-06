"""One proposal journal for ordinary edits and LSP WorkspaceEdit, including recovery."""
import base64
import time
from pathlib import Path

from coding_git import CodingConflict, safe_path
from coding_store import fingerprint, identifier
from code_analysis_scope import check
from lsp_positions import decode, encode, edit_text, uri_path


def encoded(data):
    return base64.b64encode(data).decode('ascii') if data is not None else None


def decoded(data):
    return base64.b64decode(data, validate=True) if data is not None else None


def state(path):
    if path.exists() and not path.is_file():
        raise ValueError('편집 대상은 일반 파일이어야 합니다: ' + str(path))
    return {'bytes': encoded(path.read_bytes()) if path.is_file() else None,
            'mode': path.stat().st_mode & 0o777 if path.is_file() else 0o644}


def identity(root):
    stat = Path(root).stat()
    return [stat.st_dev, stat.st_ino]


def prepare(store, row, edits, *, selector=None, metadata=None):
    check(row['path'])
    if not edits:
        raise ValueError('적용할 변경이 없습니다')
    p = {'id': identifier('proposal'), 'project': row['id'], 'root_identity': identity(row['path']),
         'edits': edits, 'selector': selector or {}, 'analysis': metadata, 'created_at': time.time(), 'state': 'prepared'}
    store.save('workspace_proposal', p)
    return {'proposal': p['id'], 'state': 'prepared', 'paths': [e['path'] for e in edits],
            'items': [{'path': e['path'], 'before': fingerprint(decoded(e['before']['bytes'])) if e['before']['bytes'] is not None else None,
                       'after': fingerprint(decoded(e['after']['bytes'])) if e['after']['bytes'] is not None else None} for e in edits]}


def workspace_edit(store, row, session, change, selector):
    if not isinstance(change, dict):
        raise ValueError('서버가 WorkspaceEdit를 반환하지 않았습니다')
    root = session.root
    originals, virtual = {}, {}

    def relative(uri):
        path = uri_path(uri)
        if not path.is_relative_to(root):
            raise PermissionError('의존성·작업 공간 밖 파일은 편집할 수 없습니다')
        rel = path.relative_to(root).as_posix()
        safe_path(root, rel)
        return rel

    def load(rel):
        if rel not in virtual:
            originals[rel] = state(safe_path(root, rel))
            doc = session.documents.get((root / rel).as_uri())
            if doc and doc['hash'] != (fingerprint(decoded(originals[rel]['bytes'])) if originals[rel]['bytes'] is not None else None):
                raise CodingConflict('서버가 읽은 원본이 변경됐습니다: ' + rel)
            virtual[rel] = dict(originals[rel])
        return virtual[rel]

    def text_edit(uri, edits, version=None):
        rel = relative(uri)
        current = load(rel)
        if current['bytes'] is None:
            raise ValueError('없는 파일의 TextEdit: ' + rel)
        doc = session.documents.get(uri)
        if version is not None and (not doc or doc['version'] != version):
            raise CodingConflict('서버가 반환한 편집의 문서 판본이 다릅니다')
        text, encoding = decode(decoded(current['bytes']), rel)
        current['bytes'] = encoded(encode(edit_text(text, edits, session.encoding), encoding))

    if change.get('changes') and change.get('documentChanges'):
        raise ValueError('changes와 documentChanges를 동시에 적용하지 않습니다')
    for uri, edits in change.get('changes', {}).items():
        text_edit(uri, edits)
    for item in change.get('documentChanges', []):
        if 'textDocument' in item:
            document = item['textDocument']
            text_edit(document['uri'], item['edits'], document.get('version'))
            continue
        kind, options = item.get('kind'), item.get('options', {})
        if kind == 'create':
            rel = relative(item['uri']); current = load(rel)
            if current['bytes'] is not None and not options.get('overwrite'):
                if options.get('ignoreIfExists'):
                    continue
                raise CodingConflict('생성할 파일이 이미 있습니다: ' + rel)
            current['bytes'] = encoded(b'')
        elif kind == 'rename':
            old, new = relative(item['oldUri']), relative(item['newUri'])
            source, dest = load(old), load(new)
            if source['bytes'] is None:
                raise CodingConflict('개명 원본이 없습니다: ' + old)
            if dest['bytes'] is not None and not options.get('overwrite'):
                if options.get('ignoreIfExists'):
                    continue
                raise CodingConflict('개명 목적지가 이미 있습니다: ' + new)
            virtual[new] = dict(source)
            source['bytes'] = None
        elif kind == 'delete':
            rel = relative(item['uri']); current = load(rel)
            if current['bytes'] is None and not options.get('ignoreIfNotExists'):
                raise CodingConflict('삭제 대상이 없습니다: ' + rel)
            current['bytes'] = None
        else:
            raise ValueError('지원하지 않는 파일 작업: ' + str(kind))
    edits = [{'path': rel, 'before': originals[rel], 'after': value} for rel, value in virtual.items() if value != originals[rel]]
    return prepare(store, row, edits, selector=selector,
                   metadata={'generation': session.generation, 'encoding': session.encoding,
                             'annotations': change.get('changeAnnotations', {})})


def _replace(path, value):
    from code_analysis_fileops import replace
    replace(path, decoded(value['bytes']), value['mode'])


def apply(store, row, proposal, *, recover=False):
    check(row['path'], write=True)
    if row.get('mode') == 'inspect':
        raise PermissionError('inspect 뷰는 읽기 전용입니다. 변경은 코딩 작업 공간 또는 수리 후보에서 적용하세요')
    with store.lock('workspace:' + row['id']):
        p = store.get('workspace_proposal', proposal)
        if p.get('project') != row['id']:
            raise PermissionError('다른 작업 공간의 제안입니다')
        if p.get('state') == 'applied':
            return {**p['result'], 'cached': True}
        if p.get('root_identity') != identity(row['path']):
            raise CodingConflict('작업 공간 디렉터리 자체가 교체됐습니다')
        if row.get('mode') == 'repair':
            from repair_context import active
            from thread_context import get_repair_workspace
            from program_boundary import protected_reason
            candidate = get_repair_workspace(create=False)
            if not active() or not candidate or Path(candidate).resolve() != Path(row['path']).resolve():
                raise PermissionError('현재 수리 후보만 변경할 수 있습니다')
            for edit in p['edits']:
                reason = protected_reason(edit['path'])
                if reason:
                    raise PermissionError(str(reason))
        remaining = []
        for e in p['edits']:
            target = safe_path(row['path'], e['path'])
            actual = state(target)
            if actual == e['before']:
                remaining.append(e)
            elif recover and actual == e['after']:
                continue
            else:
                raise CodingConflict('파일이 그 사이 바뀌었습니다. 외부 편집을 덮어쓰지 않습니다: ' + e['path'])
        p['state'] = 'applying'
        store.save('workspace_proposal', p)
        try:
            for e in remaining:
                target = safe_path(row['path'], e['path'])
                if state(target) != e['before']:
                    raise CodingConflict('적용 중 외부 변경: ' + e['path'])
                _replace(target, e['after'])
            result = {'proposal': proposal, 'applied': True, 'paths': [e['path'] for e in p['edits']]}
            if len(p['edits']) == 1:
                e = p['edits'][0]
                result.update(path=e['path'], deleted=e['after']['bytes'] is None,
                              fingerprint=fingerprint(decoded(e['after']['bytes'])) if e['after']['bytes'] is not None else None)
            p.update(state='applied', result=result, applied_at=time.time())
            store.save('workspace_proposal', p)
            return result
        except BaseException:
            p['state'] = 'recovery_required'
            store.save('workspace_proposal', p)
            raise


def recover(store, row):
    results = []
    for p in store.list('workspace_proposal'):
        if p.get('project') == row['id'] and p.get('state') in ('applying', 'recovery_required'):
            try:
                results.append(apply(store, row, p['id'], recover=True))
            except (ValueError, OSError, CodingConflict) as exc:
                results.append({'proposal': p['id'], 'state': 'recovery_required', 'error': str(exc)})
    return {'items': results}
