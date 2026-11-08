"""승인된 자기수리 도구의 공통 경로와 실행 증거. 일반 작업에는 적용하지 않는다."""
import json
import os
from pathlib import Path

WRITE_TOOLS = {"write_file", "edit_file", "make_directory", "delete_path", "move_path", "copy_path"}
FILE_TOOLS = WRITE_TOOLS | {"read_op", "read_file", "list_directory", "run_command",
                            "patch_op", "grep_files", "glob_files"}
PATHS = {"path", "root_path", "file_path", "target", "dir_path", "src", "source", "dest", "destination", "args_file"}


def protected_write_reason(handler, path, body_root):
    """File tools and candidate publication share one protected boundary."""
    from script_workspace import owned_script_work_path
    if owned_script_work_path(path) is not None:
        return None  # Task-owned scratch is not a host-owned execution receipt.
    from program_boundary import protected_reason
    relative = Path(path).relative_to(body_root).as_posix()
    return protected_reason(relative)


def source_path(st, root, wt, path):
    """Read explicit sources without turning them into candidate destinations.

    Old owned workspaces are source material, never writable through this path.
    The candidate's path validator still rejects state stores and symlink escapes.
    """
    from program_boundary import readable_runtime_state
    root, wt = Path(root).resolve(), Path(wt).resolve()
    if path.is_absolute() and path.is_relative_to(wt):
        rel = path.relative_to(wt).as_posix()
        return (st._candidate.target(root, rel, read_only=True) if readable_runtime_state(rel)
                else st._candidate.target(wt, rel))
    relative = path.relative_to(root) if path.is_absolute() and path.is_relative_to(root) else path
    if relative.is_absolute():
        raise PermissionError('수리 자료 읽기는 정본 또는 소유한 수리 사본 안에서 수행합니다')
    if relative.parts and relative.parts[0] == '.worktrees':
        if len(relative.parts) < 3:
            raise PermissionError('읽을 수리 사본과 파일 경로를 지정하세요')
        work = root / '.worktrees' / relative.parts[1]
        sessions = root / st.SESSION_DIRNAME
        owned = False
        for record in sessions.glob('*.json'):
            try:
                session = json.loads(record.read_text())
            except (ValueError, OSError):
                continue
            if (isinstance(session, dict) and session.get('owner') == st._repair_owner()
                    and session.get('worktree') == work.relative_to(root).as_posix()):
                owned = True
                break
        if not owned or work.is_symlink() or not work.resolve().is_relative_to(root):
            raise PermissionError('이전 수리 사본의 읽기 소유권을 확인하지 못했습니다')
        return st._candidate.target(work, Path(*relative.parts[2:]).as_posix())
    rel = relative.as_posix()
    if readable_runtime_state(rel):
        return st._candidate.target(root, rel, read_only=True)
    candidate = st._candidate.target(wt, rel)
    from program_boundary import describe
    # Runtime reports are absent from git worktrees. Do not fall back for deleted
    # program source: that would disguise the candidate actually being tested.
    if not candidate.exists() and (describe(rel) or {}).get('route') in {None, 'file'}:
        live = st._candidate.target(root, rel)
        if live.exists():
            return live
    return candidate


def prepare(self_module, name, payload, project):
    if name == "body_op" and payload.get("op") == "commit":
        raise PermissionError("수리 델타의 각인은 self:patch apply 이후 적용 서비스가 수행합니다")
    if name not in FILE_TOOLS and name != "script_op":
        return dict(payload), project
    st, repo, key = self_module._staging_mod(), str(self_module._REPO_ROOT), self_module._staging_key()
    from red_grant import active_grant
    from thread_context import get_current_task_id
    grant = active_grant(task_id=get_current_task_id()) or {}
    if grant.get('task_scope'):
        from task_repair import parent_of
        parent_of(grant, repo)
        if name == 'patch_op' and payload.get('op', 'propose') != 'status' and (
                payload.get('op', 'propose') == 'propose' or payload.get('proposal_id')
                or payload.get('key', key) != key):
            raise PermissionError('한정 수리는 현재 사본만 수정·적용합니다. 다른 제안·수리 키로 바꾸지 마세요')
    from repair_context import activation_only
    if activation_only():
        if name not in {"read_file", "read_op", "list_directory", "patch_op"} or (
                name == "patch_op" and payload.get("op") not in {"status", "apply"}):
            raise PermissionError("적용 이후에는 활성 확인만 합니다. 추가 결함은 같은 root의 복구 단계에서 수리하세요")
        return dict(payload), repo
    if name == "patch_op":
        return dict(payload), repo
    read_only = name in {"read_file", "read_op", "list_directory", "grep_files", "glob_files"}
    sess = st.read_session(repo, key) if read_only else None
    if not sess:
        sess = st.ensure_session(repo, key)
    if not sess:
        raise PermissionError("수리 사본을 확보하지 못했습니다. 정본은 변경하지 않습니다")
    from repair_continuation import cancelled
    if cancelled({"root_task_id": sess.get("root_task_id", key)}, repo):
        raise PermissionError("취소된 수리입니다")
    wt, root = (Path(repo) / sess["worktree"]).resolve(), Path(repo).resolve()
    result = dict(payload)
    if name in {"glob_files", "grep_files"}:
        # 메타 색인은 정본을 가리키므로 사본의 실제 파일만 탐색한다.
        pattern = payload.get("pattern" if name == "glob_files" else "file_pattern") or ""
        if os.path.isabs(pattern) or ".." in Path(pattern).parts:
            raise ValueError("수리 검색 패턴은 사본의 검색 루트 안에서만 사용합니다")
        if not result.get("path") and not result.get("root_path"):
            result["path"] = "."
    if name == "patch_op":
        return result, str(root)  # 적용자는 정본을 소유. 일반 파일 도구와 구별한다.
    from runtime_utils import expand_body_path
    from script_workspace import owned_script_work_tree, prepare_path
    temporary = []
    for field in PATHS & result.keys():
        if not isinstance(result[field], str):
            raise ValueError("수리 파일 경로는 문자열이어야 합니다")
        path = Path(expand_body_path(result[field]))
        scratch = owned_script_work_tree(path if path.is_absolute() else wt / path)
        scratch_operand = name in FILE_TOOLS or (
            name == 'script_op' and payload.get('op') == 'run' and field == 'args_file')
        if scratch_operand and scratch is not None:
            result[field] = str(scratch)
            temporary.append(scratch)
            continue
        if read_only or (name == 'copy_path' and field in {'src', 'source'}):
            result[field] = str(source_path(st, root, wt, path))
            continue
        if path.is_absolute():
            if path.is_relative_to(wt):
                rel = path.relative_to(wt).as_posix()
            elif path.is_relative_to(root):
                rel = path.relative_to(root).as_posix()
            else:
                raise PermissionError("수리 파일 도구는 같은 사본만 읽고 씁니다. 외부 의존성은 격리 셸로 읽으세요")
        else:
            rel = path.as_posix()
        if not read_only:
            from task_repair import check_delta
            check_delta(sess, [rel])
            writes_path = name in WRITE_TOOLS and not (
                name == 'copy_path' and field in {'src', 'source'})
            if writes_path and sess.get('program_policy'):
                from program_boundary import change, artifact_path
                owner = change(rel, sess['baseline'].get(rel), {'pending': True})
                if (not owner or owner['route'] != 'workspace') and not artifact_path(rel):
                    raise PermissionError('일반 프로그램 수리 범위 밖 변경: ' + rel)
        result[field] = str(st._candidate.target(wt, rel))
    if name == 'copy_path' and temporary and not (result.get('src') or result.get('source')):
        # The legacy pipe carries source paths inside rows, not PATHS. Validate
        # the whole batch before copy_piped_items creates/writes its destination.
        rows = self_module._load_sibling('copy_ops').piped_items(result.get('_prev_result'))
        destination = result.get('dest') or result.get('destination')
        if rows is not None and destination:
            mapped = []
            for row in rows:
                row = dict(row) if isinstance(row, dict) else row
                src = (row.get('path') or row.get('file') or row.get('url')) if isinstance(row, dict) else None
                if isinstance(src, str) and src and not src.startswith(('http://', 'https://')):
                    owned_script_work_tree(Path(destination) / Path(src).name)
                    if row.get('source') != 'usb':
                        path = Path(expand_body_path(src))
                        scratch = owned_script_work_tree(path if path.is_absolute() else wt / path)
                        row['path'] = str(scratch or source_path(st, root, wt, path))
                mapped.append(row)
            result['_prev_result'] = {'items': mapped}
    # Validate every operand before making any directory (including mixed moves).
    if name in WRITE_TOOLS:
        for path in temporary:
            prepare_path(path)
    return result, str(wt)


def run_shell(handler, command, timeout, shell=None):
    from supervision_bus import current
    from repair_check_runner import execute
    st, repo, key = handler._staging_mod(), str(handler._REPO_ROOT), handler._staging_key()
    from code_analysis_scope import current_scope
    execution = (current_scope() or {}).get('execution')
    if execution and not execution['body']:
        from repair_process import run
        from command_preflight import repair_argv, check as precheck, blocked, rejection
        from thread_context import repair_workspace_scope
        import subprocess
        with repair_workspace_scope(None):
            try:
                argv = repair_argv(command, shell)
                preflight = precheck(argv, cwd=execution['cwd'], runner=lambda parser, **kw:
                    run(parser, execution['root'], body=False, readonly=True,
                        check=lambda: command_check(handler), **kw))
                if blocked(preflight):
                    return shell_result(rejection(preflight), current())
                result = run(argv, execution['root'], timeout=timeout,
                             body=False, check=lambda: command_check(handler))
                from preflight_feedback import execution_result
                value = {'success': result.returncode == 0, 'exit_code': result.returncode,
                         'output': result.stdout + result.stderr,
                         'preflight': preflight,
                         'diagnostics': execution_result(preflight, result.returncode, result.stdout + result.stderr),
                         'cleanup': getattr(result, 'process_result', {}).get('cleanup')}
            except (subprocess.TimeoutExpired, OSError) as exc:
                partial = getattr(exc, 'process_result', {})
                timeout_error = isinstance(exc, subprocess.TimeoutExpired)
                value = {'success': False, 'exit_code': 124 if timeout_error else 126,
                         'failure_kind': 'timeout' if timeout_error else 'environment',
                         'output': partial.get('stdout', '') + partial.get('stderr', '') + str(exc),
                         'cleanup': partial.get('cleanup')}
        return shell_result({**value, 'workspace': execution['root']}, current())
    sess = st.ensure_session(repo, key)
    if not sess:
        raise PermissionError("수리 사본이 없습니다")
    record = execute(repo, sess, st._candidate, command, current(), timeout,
                     **({'shell_kind': shell} if shell is not None else {}),
                     **({'cwd': execution['cwd']} if execution else {}))
    st._save_session(repo, sess)
    return shell_result({"success": record["exit_code"] == 0, "exit_code": record["exit_code"],
            "output": record["output"], "verification": {k: v for k, v in record.items() if k != "output"},
            "worktree": str(Path(repo) / sess["worktree"]),
            "repository_baseline": sess.get("repository_baseline")}, current())


def shell_result(result, controller):
    """MCP 압축 뒤에도 사본 밖 파일 대신 기존 작업 증거 조회로 원문을 회수한다."""
    if controller:
        ref = controller.store.evidence(result)
        result["result_ref"] = {"id": ref["id"], "chars": ref["chars"], "scope": "tool_result",
                                "read_args": {"id": ref["id"], "path": ["output"], "limit": 16000}}
    return result


def record_write(st, repo, key, result):
    session = st.load_session(repo, key)
    st._candidate.collect(repo, session)
    st._candidate.invalidate(session)
    st._save_session(repo, session)
    try:
        parsed = json.loads(result)
    except (ValueError, TypeError):
        parsed = {"success": not str(result).startswith("Error:"), "message": str(result)}
    if isinstance(parsed, dict) and parsed.get("success", True) and not parsed.get("error"):
        parsed.update(staged=True, worktree=session["worktree"],
                      message="격리 사본에 변경을 보존했습니다. 필요한 확인을 하고 apply 하세요")
        return json.dumps(parsed, ensure_ascii=False)
    return result


def file_call(handler, payload, context):
    """Resolve file ownership before creating a code workspace; never revoke grants.

    The boundary owns classification. This adapter only binds tool path fields
    and checks the existing task, candidate, cancellation and path constraints.
    Explicit candidate paths remain candidate operations (including artifacts).
    """
    name = context.tool_name
    if name not in FILE_TOOLS - {'run_command', 'patch_op'} and name != 'ledger_op':
        return None
    fields = {'path', 'items_file'} if name == 'ledger_op' else PATHS
    root = Path(handler._REPO_ROOT).resolve()
    st, key = handler._staging_mod(), handler._staging_key()
    session = st.read_session(str(root), key) or {}
    from thread_context import repair_workspace_scope
    from runtime_utils import expand_body_path
    from program_boundary import describe
    from script_workspace import owned_script_work_path
    # Resolve scratch in the caller's candidate, before the live-document view
    # temporarily clears repair_workspace. prepare() validates all operands.
    if name in FILE_TOOLS and any(isinstance(payload[f], str)
            and owned_script_work_path(expand_body_path(payload[f])) is not None for f in fields & payload.keys()):
        return None
    paths, routes = {}, set()
    with repair_workspace_scope(None):
        for field in fields & payload.keys():
            raw = payload[field]
            if not isinstance(raw, str):
                raise ValueError('파일 경로는 문자열이어야 합니다')
            path = Path(expand_body_path(raw))
            path = path if path.is_absolute() else root / path
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                return None  # existing repair path validator owns external paths
            # Do not silently turn an explicitly selected candidate into live data.
            if session.get('worktree') and path.is_relative_to(root / session['worktree']):
                routes.add('workspace')
                continue
            item = describe(relative) or {}
            routes.add(item.get('route'))
            paths[field] = (relative, path)
    if 'file' not in routes:
        if name == 'ledger_op' and payload.get('op', 'select') != 'select':
            raise PermissionError('원장 파일의 소유 경로로 변경해야 합니다. self:patch status로 경계를 확인하세요')
        return None
    if routes != {'file'}:
        raise PermissionError('서로 다른 소유 경로의 파일 연산은 분리하세요. 코드 사본과 정본 문서를 함께 이동하지 않습니다')
    from repair_continuation import current, cancelled
    from task_repair import check_delta
    from repair_context import activation_only
    from red_grant import active_grant
    from thread_context import get_current_task_id
    grant = active_grant(task_id=get_current_task_id()) or {}
    if grant.get('task_scope'):
        from task_repair import parent_of
        parent_of(grant, str(root))
        check_delta({**session, 'task_scope': grant['task_scope']}, [r for r, _ in paths.values()])
    check_delta(session, [r for r, _ in paths.values()])
    row = current() or session
    if row.get('root_task_id') and cancelled(row, str(root)):
        raise PermissionError('취소된 수리입니다')
    writing = name in WRITE_TOOLS or (name == 'ledger_op' and payload.get('op', 'select') != 'select')
    if writing and activation_only():
        raise PermissionError('적용 이후에는 활성 확인만 합니다. 문서 변경도 실행 단계에서 이어가세요')
    mapped = dict(payload)
    for field, (relative, path) in paths.items():
        # The existing candidate validator also rejects symlinked parents.
        path = st._candidate.target(root, relative)
        if writing and path.is_file() and path.stat().st_nlink != 1:
            raise PermissionError('하드 링크를 통한 문서 변경은 지원하지 않습니다')
        if writing and path.is_dir():
            for child in path.rglob('*'):
                rel = child.relative_to(root).as_posix()
                st._candidate.target(root, rel)
                if (describe(rel) or {}).get('route') != 'file' or (child.is_file() and child.stat().st_nlink != 1):
                    raise PermissionError('폴더 안에 다른 소유자의 대상이 있습니다: ' + rel)
        mapped[field] = str(path)
    from copy import copy
    routed_context = copy(context)
    routed_context.project_path = str(root)
    return mapped, routed_context


def execute(handler, payload, context, operation):
    """Run under the caller's application lock and record only owned effects."""
    st, repo, key = handler._staging_mod(), str(handler._REPO_ROOT), handler._staging_key()
    name = context.tool_name
    if name == 'run_command':
        from code_analysis_scope import bind
        from thread_context import repair_workspace_scope
        from copy import copy
        execution = command_context(handler, payload)
        routed = copy(context)
        routed.project_path = execution['cwd']
        with bind(execution['root'], writable=True, generation=execution.get('created_at', ''), execution=execution), \
                repair_workspace_scope(execution['root'] if execution['body'] else None):
            return operation(payload, routed, prepared=True)
    routed = file_call(handler, payload, context)
    if routed:
        from thread_context import repair_workspace_scope
        with repair_workspace_scope(None):
            return operation(*routed, prepared=True)
    if name == 'script_op' and payload.get('op') in {'register', 'remove'}:
        return managed_write(st, repo, key, lambda: operation(payload, context))
    from copy import copy
    from script_workspace import owned_script_work_path
    mapped, project = prepare(handler, name, payload, context.project_path)
    prepared_context = copy(context)
    prepared_context.project_path = project
    result = operation(mapped, prepared_context, prepared=True)
    paths = [mapped[f] for f in PATHS & mapped.keys()]
    scratch_only = bool(paths) and all(owned_script_work_path(p) is not None for p in paths)
    return record_write(st, repo, key, result) if name in WRITE_TOOLS and not scratch_only else result


def command_check(handler, session=None, relatives=()):
    """The file and command routes retain the same repair authority."""
    from repair_context import activation_only
    from repair_continuation import current, cancelled
    from red_grant import active_grant
    from thread_context import get_current_task_id
    from task_repair import parent_of, check_delta
    if activation_only():
        raise PermissionError('적용 이후에는 활성 확인만 합니다')
    repo = str(handler._REPO_ROOT)
    session = session or handler._staging_mod().read_session(repo, handler._staging_key()) or {}
    grant = active_grant(task_id=get_current_task_id()) or {}
    if grant.get('task_scope'):
        parent_of(grant, repo)
        check_delta({**session, 'task_scope': grant['task_scope']}, list(relatives))
    check_delta(session, list(relatives))
    row = current() or session
    if row.get('root_task_id') and cancelled(row, repo):
        raise PermissionError('취소된 수리입니다')


def command_context(handler, payload):
    from code_analysis_scope import working_directory, check, current_scope
    from program_boundary import describe
    from runtime_utils import expand_body_path
    from thread_context import repair_workspace_scope
    root = Path(handler._REPO_ROOT).resolve()
    st, key = handler._staging_mod(), handler._staging_key()
    session = st.read_session(str(root), key) or {}
    from repair_continuation import directory, key as continuation_key
    cancellation = str(directory(str(root)) / (continuation_key(session.get('root_task_id') or key) + '.cancel'))
    requested = payload.get('cwd')
    with repair_workspace_scope(None):
        raw = Path(expand_body_path(requested)) if requested is not None else root
    raw = raw if raw.is_absolute() else root / raw
    if not raw.is_relative_to(root):
        scope = current_scope()
        if not scope:
            raise PermissionError('외부 프로젝트에는 기존 작업 범위가 필요합니다')
        check(raw, write=True)
        path = st._candidate.target(scope['root'], raw.relative_to(scope['root']).as_posix())
        relative, explicit_candidate, body = str(path), False, False
    else:
        relative = raw.relative_to(root).as_posix()
        explicit_candidate = session.get('worktree') and raw.is_relative_to(root / session['worktree'])
        path = (st._candidate.target(root / session['worktree'], raw.relative_to(root / session['worktree']).as_posix())
                if explicit_candidate else st._candidate.target(root, relative))
        body = explicit_candidate or (describe(relative) or {}).get('route') != 'file'
    command_check(handler, session, [relative] if not body else ())
    if not body:
        target = working_directory(str(path), root)
        # Seatbelt rejects new links and writes through symlink targets. Reject
        # existing hard links before giving a live content tree write authority.
        for directory, _, files in os.walk(target, followlinks=False):
            for name in files:
                item = Path(directory) / name
                if not item.is_symlink() and item.stat().st_nlink > 1:
                    raise PermissionError('하드 링크를 통한 문서 변경은 지원하지 않습니다')
        return {'root': str(target), 'cwd': str(target), 'body': False,
                'repo': str(root), 'key': key, 'cancel_path': cancellation}
    session = st.ensure_session(str(root), key)
    if not session:
        raise PermissionError('수리 사본이 없습니다')
    wt = (root / session['worktree']).resolve()
    cwd = path if explicit_candidate else wt / relative
    cwd = working_directory(str(cwd), wt)
    check(wt, write=True)
    return {'root': str(wt), 'cwd': str(cwd), 'body': True, 'repo': str(root), 'key': key,
            'cancel_path': cancellation,
            'created_at': session.get('created_at'),
            'session_path': str(Path(st._session_path(str(root), key)))}


def managed_write(st, repo, key, operation):
    """The script owner writes; the existing host session records exact bytes.

    Failed publication rolls its resource back, never poisoning the candidate.
    The caller holds the repair application lock through this transaction.
    """
    from program_boundary import MANAGED_RESOURCES
    session = st.ensure_session(repo, key)
    relative = 'data/scripts/registry.yaml'
    path = st._candidate.target(Path(repo) / session['worktree'], relative)
    before = path.read_bytes() if path.is_file() else None
    mode = path.stat().st_mode if path.exists() else None
    draft = None
    owner_before = before
    try:
        baseline = session['baseline'].get(relative)
        if (relative not in session.get('managed_files', {})
                and st._candidate.fingerprint(path) != baseline):
            # Legacy candidates may contain a manually edited registry. Preserve
            # the draft, then run the real owner against the proven baseline.
            # Do not grant the whole old draft a fabricated owner receipt.
            live = st._candidate.target(repo, relative)
            if st._candidate.fingerprint(live) != baseline:
                raise ValueError('등록부의 정본도 변경됐습니다. 기존 초안을 보존하고 충돌을 먼저 해결하세요')
            import base64
            draft = {'path': relative, 'data': base64.b64encode(before or b'').decode(),
                     'fingerprint': st._candidate.fingerprint(path), 'reason': 'unreceipted registry draft'}
            owner_before = live.read_bytes() if live.is_file() else None
            if owner_before is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(owner_before)
        st._candidate.collect(repo, session)
        result = operation()
        parsed = json.loads(result) if isinstance(result, str) else result
        if not isinstance(parsed, dict) or parsed.get('success') is not True:
            if before is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(before)
                path.chmod(mode)
            return result
        from script_mutation import validate_task_scope
        validate_task_scope(session, owner_before, path.read_bytes() if path.exists() else None)
        after = st._candidate.fingerprint(path)
        old = session.get('managed_files', {}).get(relative)
        session.setdefault('managed_files', {})[relative] = {
            'owner': MANAGED_RESOURCES[relative], 'fingerprint': after}
        try:
            st._candidate.collect(repo, session)
            st._candidate.invalidate(session)
            if draft:
                session.setdefault('managed_drafts', []).append(draft)
            st._save_session(repo, session)
        except BaseException:
            if old is None:
                session['managed_files'].pop(relative, None)
            else:
                session['managed_files'][relative] = old
            raise
        if draft:
            parsed['recovered_draft'] = {'path': relative, 'preserved_in': 'managed_drafts',
                'message': '기존 수동 원장은 초안으로 보존했습니다. 이번 공식 연산만 반영했으며 나머지 초안 항목도 공식 등록이 필요합니다.'}
        parsed.update(staged=True, worktree=session['worktree'], applied=False,
                      message='관리 연산의 사본 판본을 수리 후보에 연결했습니다. 검사 뒤 같은 사본을 apply 하세요.')
        return json.dumps(parsed, ensure_ascii=False)
    except BaseException:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)
            path.chmod(mode)
        raise
