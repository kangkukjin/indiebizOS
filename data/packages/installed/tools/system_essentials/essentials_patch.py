"""Multi-file edit entry, retaining path guards and repair staging."""
from pathlib import Path
from file_workspace import FileWorkspace
from text_patch import parse


def edit(params, project, guard, stage):
    if ('patch' in params) == ('patch_ref' in params):
        raise ValueError('patch와 patch_ref 중 하나만 지정하세요')
    if any(k in params for k in ('old_string', 'new_string', 'start_line', 'end_line')):
        raise ValueError('문자열 편집과 patch를 함께 지정할 수 없습니다')
    service = FileWorkspace()
    if params.get('resource'):
        from workspace_sessions import Workspace
        _, adapter, row = Workspace().resolve(params['resource'])
        service = FileWorkspace(adapter.store)
    else:
        row = service.open(Path(project))
    patch = params.get('patch')
    if 'patch_ref' in params:
        from runtime_utils import expand_body_path
        source = Path(expand_body_path(params['patch_ref']))
        if not source.is_absolute(): source = Path(project) / source
        error = guard(str(source), project)
        if error: raise PermissionError(str(error))
        if source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('patch_ref는 8MiB 이하 파일이어야 합니다')
        patch = source.read_text(encoding='utf-8')
    entries = parse(patch, params.get('format', 'indiebiz-patch/1'))
    from coding_git import safe_path
    staged_root = None
    for entry in entries:
        for rel in [entry['path']] + ([entry['move']] if 'move' in entry else []):
            target = safe_path(row['path'], rel)
            error = guard(str(target), project)
            if error: raise PermissionError(str(error))
            staged = Path(stage(str(target), for_write=True))
            if staged != target:
                root = staged
                for _ in Path(rel).parts: root = root.parent
                if staged_root and staged_root != root:
                    raise ValueError('여러 수리 후보에 걸친 패치는 거절합니다')
                staged_root = root
    if staged_root:
        row = service.open(staged_root, mode='repair')
    result = service.patch(row, patch, expected=params.get('expected'),
                           request_id=params.get('request_id'), format=params.get('format', 'indiebiz-patch/1'))
    if not params.get('preview'):
        result = service.apply(row, result['proposal'])
    return {'success': True, **result, 'resource': row['id'],
            'effect_scope': 'candidate' if row.get('mode') == 'repair' else 'live'}
