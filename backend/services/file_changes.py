"""One proposal journal for ordinary edits and LSP WorkspaceEdit, including recovery."""
import base64
import time
from pathlib import Path

from coding_git import CodingConflict, safe_path
from coding_store import fingerprint, identifier
from code_analysis_scope import check


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
    validate_targets(row, edits)
    if not edits:
        raise ValueError('적용할 변경이 없습니다')
    edits = [{**e, **{key: {**e[key], 'mode': 0o644} if e[key]['bytes'] is None else e[key]
                      for key in ('before', 'after')}} for e in edits]
    p = {'id': identifier('proposal'), 'project': row['id'], 'root_identity': identity(row['path']), 'root': row['path'],
         'attribution': attribution(), 'edits': edits, 'selector': selector or {}, 'analysis': metadata, 'created_at': time.time(), 'state': 'prepared'}
    validate_attribution(p)
    store.save('workspace_proposal', p)
    return {'proposal': p['id'], 'state': 'prepared', 'paths': [e['path'] for e in edits],
            'items': [{'path': e['path'], 'before': fingerprint(decoded(e['before']['bytes'])) if e['before']['bytes'] is not None else None,
                       'after': fingerprint(decoded(e['after']['bytes'])) if e['after']['bytes'] is not None else None} for e in edits]}



def _replace(path, value):
    from code_analysis_fileops import replace
    replace(path, decoded(value['bytes']), value['mode'])


def apply(store, row, proposal, *, recover=False, writer=None):
    check(row['path'], write=True)
    if row.get('mode') == 'inspect':
        raise PermissionError('inspect 뷰는 읽기 전용입니다. 변경은 코딩 작업 공간 또는 수리 후보에서 적용하세요')
    with attribution_lock(store.get('workspace_proposal', proposal)), store.lock('workspace:' + row['id']), store.lock('file-change-application'):
        p = store.get('workspace_proposal', proposal)
        if p.get('project') != row['id']:
            raise PermissionError('다른 작업 공간의 제안입니다')
        validate_attribution(p)
        validate_targets(row, p['edits'])
        if p.get('state') == 'applied':
            return {**p['result'], 'cached': True}
        if p.get('root_identity') != identity(row['path']):
            raise CodingConflict('작업 공간 디렉터리 자체가 교체됐습니다')
        targets = {str(safe_path(row['path'], e['path'])) for e in p['edits']}
        for pending in store.list('workspace_proposal'):
            if pending['id'] == proposal or pending.get('state') not in ('applying', 'recovery_required'):
                continue
            root = pending.get('root')
            if root and targets.intersection(str(Path(root) / e['path']) for e in pending['edits']):
                raise CodingConflict('먼저 중단된 변경을 복구하세요: ' + pending['id'])
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
                (writer or _replace)(target, e['after'])
                if state(target) != e['after']:
                    raise CodingConflict('교체 직후 외부 변경: ' + e['path'])
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


def attribution():
    from conversation_sessions import effect_current
    from dataclasses import asdict
    binding = effect_current()
    if not binding:
        return {}
    return asdict(binding)


def validate_attribution(proposal):
    owner = proposal.get('attribution') or {}
    if not owner or (proposal.get('analysis') or {}).get('rewind'):
        return
    from conversation_sessions import connection
    from turn_checkpoints import revision, assert_unlocked, schema
    with connection(owner['db_path']) as conn:
        schema(conn)
        assert_unlocked(conn, owner['session_id'])
        if revision(conn, owner['session_id']) != owner.get('revision', 0):
            raise CodingConflict('대화 판본이 변경돼 이전 턴의 쓰기를 적용하지 않습니다')


def write_text(path, text):
    """Preimage is durable before any managed ordinary file write."""
    from file_workspace import FileWorkspace
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    service = FileWorkspace()
    row = service.open(target.parent)
    before = state(target)
    after = {**before, 'bytes': encoded(text.encode('utf-8'))}
    p = prepare(service.store, row, [{'path': target.name, 'before': before, 'after': after}])
    return apply(service.store, row, p['proposal'])


def transfer_file(source, destination, *, move=False, if_exists='rename', guard=None):
    """Bound ordinary copies/moves preserve both preimages in one proposal."""
    import os
    from file_workspace import FileWorkspace
    from output_publish import collision_policy
    policy = collision_policy(if_exists)
    source, requested = Path(source).absolute(), Path(destination).absolute()
    target, index = requested, 1
    if source.is_symlink() or requested.is_symlink():
        raise ValueError('추적 복사·이동은 일반 파일만 지원합니다')
    while target.exists() and policy == 'rename':
        index += 1
        target = requested.with_name(f'{requested.stem} ({index}){requested.suffix}')
    if target.exists() and policy == 'fail':
        raise FileExistsError(str(target))
    if guard:
        error = guard(str(target))
        if error:
            raise ValueError(str(error))
    target.parent.mkdir(parents=True, exist_ok=True)
    root = Path(os.path.commonpath([source.parent, target.parent])) if move else target.parent
    service = FileWorkspace()
    row = service.open(root)
    with attribution_lock({'attribution': attribution()}), service.store.lock('workspace:' + row['id']), service.store.lock('file-change-application'):
        before = state(target)
        original = state(source)
        edits = [{'path': target.relative_to(root).as_posix(), 'before': before, 'after': original}]
        if move:
            edits.append({'path': source.relative_to(root).as_posix(), 'before': original,
                          'after': {**original, 'bytes': None}})
        p = prepare(service.store, row, edits, metadata={'source': 'move' if move else 'copy'})
        apply(service.store, row, p['proposal'])
    return {'path': str(target), 'requested_path': str(requested), 'proposal': p['proposal'],
            'if_exists': policy, 'replaced_existing': before['bytes'] is not None, 'renamed': target != requested}


def delete_file(path):
    from file_workspace import FileWorkspace
    target = Path(path).absolute()
    service = FileWorkspace()
    row = service.open(target.parent)
    before = state(target)
    p = prepare(service.store, row, [{'path': target.name, 'before': before,
                                     'after': {**before, 'bytes': None}}], metadata={'source': 'delete'})
    return apply(service.store, row, p['proposal'])


def validate_targets(row, edits):
    if not str(row['id']).startswith('files_') or row.get('mode') == 'repair':
        return
    from runtime_utils import get_base_path
    from program_boundary import describe
    base = Path(get_base_path()).resolve()
    for edit in edits:
        target = safe_path(row['path'], edit['path'])
        if target.is_relative_to(base):
            spec = describe(target.relative_to(base).as_posix()) or {}
            if spec and spec.get('route') != 'file':
                raise PermissionError('몸의 코드·관리 자료는 기존 수리/관리 경로로 변경하세요: ' + edit['path'])


from contextlib import contextmanager


@contextmanager
def attribution_lock(proposal):
    owner = proposal.get('attribution') or {}
    if not owner:
        yield
        return
    from filelock import FileLock
    folder = Path(owner['db_path']).parent / 'conversation_state' / owner['session_id']
    folder.mkdir(parents=True, exist_ok=True)
    with FileLock(str(folder / 'rewind.lock'), is_singleton=True):
        yield
