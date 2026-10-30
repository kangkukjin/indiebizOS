"""일반 사용자 업무의 등록 순수 부품 수정. RED 전역 그랜트를 발급하지 않는다."""
import json
from pathlib import Path

import component_runtime as runtime


def binding():
    from execution_turn import current
    from principal import is_owner
    from thread_context import get_task_origin
    turn = current()
    if (turn and turn.component_repair_allowed and is_owner() and get_task_origin() == 'user'):
        if turn.cancel_check and turn.cancel_check():
            raise PermissionError('현재 작업이 취소됐습니다')
        from providers.base import turn_limit_reason
        if turn_limit_reason():
            raise PermissionError('현재 작업의 실행 예산이 끝났습니다')
        from script_process import check_invocation
        check_invocation()
        return turn
    return None


def permits_candidate(path):
    turn = binding()
    if not turn:
        return False
    path = Path(path)
    return (str(path.absolute()) in turn.component_paths and not path.is_symlink()
            and str(path.resolve()) in turn.component_paths
            and (not path.exists() or path.stat().st_nlink == 1))


def protected(path, root):
    rel = Path(path).relative_to(root).as_posix()
    from runtime_utils import get_code_root
    if rel in {s['source'] for s in runtime.registry(get_code_root()).values()}:
        return 'Error: 등록 부품은 활성 소유자 업무의 한정 사본 수정→self:patch apply로 반영합니다.'
    if (rel.startswith(('data/common_prompts/', 'data/restart_control/', 'data/system_ai_state/',
                        'data/packages/installed/tools/system_essentials/'))
            or rel in {'AGENTS.md', 'CLAUDE.md'} or rel.endswith('/runtime_components.json')):
        return 'Error: 지침·권한·검사 계약·적용 원장은 업무 중 부품 수리의 수정 대상이 아닙니다.'
    return None


def require_binding():
    if not binding():
        raise PermissionError('현재 작업 권한이 사라졌습니다')


def handle(handler, payload, context):
    if handler._red_grant_active():
        return None
    turn = binding()
    if not turn:
        return None
    repo = Path(handler._REPO_ROOT).resolve()
    st = handler._staging_mod()
    name = context.tool_name
    if name == 'patch_op' and turn.component_session and payload.get('op') in {'apply', 'status', 'discard'}:
        with st._candidate.locked(str(repo), 'application'):
            if payload['op'] == 'apply':
                result = apply(handler, repo, turn)
            elif payload['op'] == 'status':
                session = st.read_session(str(repo), turn.component_session) or {}
                result = {'success': True, 'component_repair': True,
                          'status': session.get('status'), 'worktree': session.get('worktree'),
                          'activation': session.get('component_activation'), 'commit': session.get('commit')}
            else:
                result = st.op_discard({'_repo_root': str(repo), '_grant_key': turn.component_session})
                turn.component_session = ''
                turn.component_paths.clear()
        return json.dumps(result, ensure_ascii=False)
    if name not in {'read_file', 'read_op', 'write_file', 'edit_file'}:
        return None
    from runtime_utils import get_code_root, expand_body_path
    raw = handler._get_path(payload)
    if not raw:
        return None
    target = Path(context.project_path) / expand_body_path(raw)
    if target.is_symlink():
        return None
    specs = runtime.registry(get_code_root())
    spec = next((s for s in specs.values() if target.resolve() == repo / s['source']), None)
    session = st.read_session(str(repo), turn.component_session) if turn.component_session else None
    if not spec and session:
        spec = next((s for s in specs.values() if target.resolve() ==
                     (repo / session['worktree'] / s['source']).resolve()), None)
    if not spec:
        return None
    writing = name in {'write_file', 'edit_file'}
    if session and session.get('status') in {'applied', 'discarded'}:
        if not writing:
            return handler._execute({**payload, 'path': str(repo / spec['source']),
                                     'file_path': str(repo / spec['source'])}, context)
        turn.component_session = ''
        turn.component_paths.clear()
    if not writing and not session:
        return None  # 기존 읽기 계약 그대로, 읽기만으로 수리 사본을 만들지 않는다.
    from coding_process import available
    if not available():
        raise PermissionError('이 몸의 부품 수리 제한 실행은 미지원입니다')
    if not turn.component_session:
        turn.component_attempt += 1
        turn.component_session = st.task_key(f'component-{turn.task}-{turn.component_attempt}')
    with st._candidate.locked(str(repo), 'application'):
        candidate = st.stage_file(str(repo), turn.component_session, str(repo / spec['source']))
        if not candidate:
            raise PermissionError('부품 수리 사본을 만들지 못했습니다')
        candidate = st._candidate.target(repo / st.read_session(str(repo), turn.component_session)['worktree'], spec['source'])
        turn.component_paths.add(str(candidate.resolve()))
        # 기존 파일 편집·읽기·줄 범위·불일치 진단을 재사용한다.
        mapped = {**payload, 'path': str(candidate), 'file_path': str(candidate)}
        result = handler._execute(mapped, context)
        if writing:
            session = st.read_session(str(repo), turn.component_session)
            st._candidate.collect(str(repo), session)
            st._candidate.invalidate(session)
            st._save_session(str(repo), session)
            if not str(result).startswith('Error:'):
                try:
                    obj = json.loads(result)
                except (ValueError, TypeError):
                    obj = {'success': True}
                if obj.get('success', True) and not obj.get('error'):
                    obj.update(staged=True, path=str(candidate), live_path=str(repo / spec['source']),
                               component=spec['id'], message='부품 사본 수정. self:patch apply가 고정 검사·반영·무재기동 활성화를 수행합니다. 이후 원래 업무를 계속하세요.')
                    return json.dumps(obj, ensure_ascii=False)
        return result


def apply(handler, repo, turn):
    """사본/검사/봉인/정본 충돌/커밋 원장을 재사용하고 부품 판본만 활성화한다."""
    from runtime_utils import get_code_root
    st, key = handler._staging_mod(), turn.component_session
    session = st.read_session(str(repo), key)
    if not session:
        raise ValueError('부품 수리 세션이 없습니다')
    specs = runtime.registry(get_code_root())
    by_source = {s['source']: s for s in specs.values()}
    if session.get('status') == 'applied':
        return finish(handler, repo, session)
    if session.get('status') in {'applying', 'component_prepared'}:
        recover(handler, repo, session)
        if session['status'] == 'applied':
            return finish(handler, repo, session)
    if session.get('status') != 'staging':
        raise ValueError('부품 적용 상태 확인이 필요합니다: ' + session.get('status', 'unknown'))
    st._candidate.collect(str(repo), session)
    files = session.get('files', {})
    if not files or any(r['rel'] not in by_source or r['op'] == 'delete' for r in files.values()):
        raise PermissionError('등록된 부품 소스만 수정할 수 있습니다. 계약·검사·지침·다른 파일 변경은 적용하지 않습니다')
    checks, selected = [], []
    for rec in files.values():
        spec = by_source[rec['rel']]
        source = Path(rec['staged']).read_bytes()
        check = runtime.verify(spec, source, check=require_binding)
        checks.append(check)
        version = runtime.store_object(repo, source)
        selected.append({'spec': spec, 'version': version})
    if not binding():
        raise PermissionError('현재 작업 권한이 사라졌습니다')
    st._candidate.seal(str(repo), session, checks, {'status': 'APPROVED'},
                       {'criteria': [{'id': 'component', 'text': '등록 부품의 고정 순수 변환 계약'}]})
    session['component_activation'] = selected
    # 게시된 검증 바이트가 감시자의 전체 교체로 확대되지 않게 소스 적용 전 연결한다.
    active_file = runtime.home(repo) / 'active.json'
    before = active_file.read_bytes() if active_file.exists() else b'{}'
    session['component_previous'] = json.loads(before)
    session['status'] = 'component_prepared'
    st._save_session(str(repo), session)
    try:
        st._candidate.validate(str(repo), session)
        for row in selected:
            runtime.publish(repo, row['spec'], row['version'], receipt={'session': key, 'phase': 'applying'})
        result = st._perform_apply_locked(str(repo), session, checks, None, None)
        if not result.get('success'):
            recover(handler, repo, session)
            return result
    except BaseException:
        recover(handler, repo, session)
        raise
    return finish(handler, repo, session)


def recover(handler, repo, session):
    """죽음/예외 뒤에는 원장에 고정된 바이트만 확인·복구한다. 타인 변경은 덮지 않는다."""
    import base64
    st = handler._staging_mod()
    states = []
    for rel, item in session['sealed'].items():
        path = st._candidate.target(repo, rel)
        current = st._candidate.fingerprint(path)
        if current not in (item['before'], item['after']):
            raise ValueError('부품 적용 중 정본 충돌. 사본과 기존 판본을 보존했습니다: ' + rel)
        states.append((path, item, current == item['after']))
    if all(after for _, _, after in states):
        session.update(status='applied', verified=True)
    else:
        for path, item, after in states:
            if after:
                handler._file_io.atomic_write_text(str(path), base64.b64decode(item['before_data']).decode())
                path.chmod(item['before']['mode'])
        active_file = runtime.home(repo) / 'active.json'
        rows = json.loads(active_file.read_bytes()) if active_file.exists() else {}
        for entry in session['component_activation']:
            cid = entry['spec']['id']
            if (rows.get(cid) or {}).get('version') == entry['version']:
                old = session.get('component_previous', {}).get(cid)
                if old:
                    rows[cid] = old
                else:
                    rows.pop(cid, None)
        active_file.parent.mkdir(parents=True, exist_ok=True)
        runtime.atomic_json(active_file, rows)
        session['status'] = 'staging'
    st._save_session(str(repo), session)


def finish(handler, repo, session):
    st = handler._staging_mod()
    committed = st._candidate.commit(str(repo), session, handler._load_sibling('body_ops'))
    session['commit'] = committed
    st._save_session(str(repo), session)
    versions = []
    for row in session['component_activation']:
        spec, version = row['spec'], row['version']
        if runtime.sha((repo / spec['source']).read_bytes()) != version:
            raise ValueError('적용 이후 정본 부품이 변경됐습니다')
        runtime.publish(repo, spec, version, receipt={'session': session['key'], 'commit': committed,
                                                     'phase': 'complete' if committed.get('success') else 'commit_pending'})
        versions.append({'component': spec['id'], 'version': version})
    return {'success': bool(committed.get('success')), 'applied': True,
            'activated': True, 'restart_required': False, 'versions': versions, 'commit': committed,
            'message': '부품 판본을 활성화했습니다. 원래 업무를 이어가 결과를 확인하세요.'}
