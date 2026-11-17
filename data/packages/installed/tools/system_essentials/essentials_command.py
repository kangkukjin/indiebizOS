"""몸의 셸 — 명령은 몸이 쥐고(process session), 끝나거나 제한 시간이 지나면 돌아온다."""
import json


def execute_command(h, tool_input, project_path):
    if tool_input.get('mode') not in (None, 'sync', 'session'):
        return 'Error: mode는 sync/session입니다'
    command = tool_input.get("command", "").strip()
    timeout = min(tool_input.get("timeout", 60), 300)  # 최대 300초
    approved = tool_input.get("approved", False)

    if not command:
        return "Error: 명령어가 비어있습니다."

    runtime = tool_input.get("runtime", "shell")
    from phone_remote_execution import capabilities, run_local
    native_execution = capabilities().get("execution_contract") == 1
    if native_execution and tool_input.get('shell') not in (None, 'sh'):
        return json.dumps({'success': False, 'error': '폰 shell은 sh만 지원합니다'})
    if tool_input.get('mode') == 'session' and (runtime != 'shell' or native_execution):
        return json.dumps({'success': False, 'error': '이 몸의 process session은 미지원입니다', 'capabilities': {'process_session': False}})
    if runtime != "shell" or native_execution:
        if not native_execution:
            return json.dumps({"success": False, "error": "embedded_runtime_requires_phone"})
        if runtime == "shell" and not approved and h.is_dangerous_command(command):
            return f"__REQUIRES_APPROVAL__:{command}"
        return json.dumps(run_local(tool_input), ensure_ascii=False)

    # 리로드 강제 금지 — touch/kill 로 자기 몸을 재기동하면 그 리로드가 **이 턴을
    # 실행 중인 워커를 죽인다**(에피소드 미종료·화면 작업표시 영구 정지, 08-18 실측).
    # 반영은 [self:patch]{op:"apply"}, 판정은 워치독이 다음 턴에. 로직=repair_staging.
    try:
        _rf = h._staging_mod().reload_forcing_violation(
            command, str(h._REPO_ROOT) if h._REPO_ROOT is not None else "")
    except Exception:
        _rf = None
    if _rf:
        return json.dumps({"success": False, "error": _rf}, ensure_ascii=False)

    # 위험한 명령어 감지 - 승인되지 않았으면 승인 요청
    if not approved and h.is_dangerous_command(command):
        return f"__REQUIRES_APPROVAL__:{command}"

    # 명령어 실행
    try:
        from code_analysis_scope import working_directory
        project_path = str(working_directory(tool_input.get('cwd') if not h._red_grant_active() else None, project_path))
        if h._red_grant_active() and tool_input.get('mode') != 'session':
            return json.dumps(h._load_sibling("repair_tool_scope").run_shell(
                h, command, timeout, **({'shell': tool_input['shell']} if tool_input.get('shell') else {})), ensure_ascii=False)
        if tool_input.get("mode") == "session" or tool_input.get("io") == "pty":
            # 입력을 주고받을 세션 — 입력 통로를 열어 둔 채 접수증을 바로 돌려준다. 고르는 기준은 걸리는 시간이
            # 아니라 입력을 보낼 것인가다.
            from process_sessions import start
            return json.dumps(start(command, project_path, io=tool_input.get("io", "pipe"),
                                    request_id=tool_input.get("request_id"),
                                    yield_ms=tool_input.get("yield_ms", 1000),
                                    lifetime=tool_input.get("lifetime", "task"), shell=tool_input.get('shell')), ensure_ascii=False)
        # 몸이 쥔다(2026-11-17, docs/BODY_HELD_COMMANDS_DESIGN_2026_11_17.md). 길지 짧을지를 미리 고르지 않는다:
        # 끝나면 지금까지와 같은 꼴의 결과가, timeout이 지나면 명령을 계속 돌린 채 접수증과 살아 있다는 신호가 온다.
        from process_sessions import hold
        cli = tool_input.get('_door') == 'cli'
        held = hold(command, project_path, timeout=timeout, shell=tool_input.get('shell'),
                    lifetime=tool_input.get('lifetime', 'task'), request_id=tool_input.get('request_id'), user=cli)
        return render_held(held, timeout, structured=cli)

    except Exception as e:
        return f"Error: 명령어 실행 실패: {e}"


def render_held(held, timeout, structured=False):
    """hold의 결과를 도구 결과로. 끝난 명령은 예전 동기 실행과 같은 글자, 도는 명령은 접수증 봉투.

    structured는 CLI 실행자의 문(MCP 다리)이다. 그 길은 감독 작업대가 결과를 봉투로 읽으므로 끝난 명령도
    봉투로 준다(shape='command'). 다리가 실행자에게 보일 때 다시 글자로 편다.
    """
    if not held.get('accepted'):
        return json.dumps(held, ensure_ascii=False)        # 구문 검사에서 막힘 — 실행하지 않았다
    shape = {'shape': 'command'} if structured else {}
    output = held.get('stdout') or ''
    if held.get('stderr'):
        output += f"\n[stderr]\n{held['stderr']}" if output else held['stderr']
    if held.get('truncated'):
        output += "\n[출력이 보존 한도(1MB)를 넘어 앞부분만 실었습니다]"
    state, code = held['state'], held.get('exit_code')
    if state in ('queued', 'running'):
        return json.dumps({
            **shape, 'success': True, 'timed_out': True, 'state': state, 'task_ref': held.get('task_ref'),
            'generation': held.get('generation'), 'cursor': held.get('cursor'),
            'output': output.strip(), 'signs': held.get('signs'),
            'note': (f"{int(timeout)}초가 지나 돌아왔습니다. 명령은 계속 실행 중입니다(실패 아님, 죽이지 않았습니다). "
                     '[self:task]{op:"wait", ref:task_ref, timeout:초}로 이어서 기다리고, op:"status"로 지금 상태를, '
                     'op:"cancel"로 끝내기를 합니다. signs는 잰 값입니다: running_s=시작 뒤 초, quiet_s=마지막 출력 뒤 초, '
                     'cpu_s=프로세스 무리가 쓴 CPU 초, cpu_quiet_s=CPU 사용이 마지막으로 늘어난 뒤 초, '
                     'processes=살아 있는 프로세스(끝 쪽부터), stdin=입력 통로 상태.')}, ensure_ascii=False)
    if state not in ('succeeded', 'failed'):
        return json.dumps({**shape, 'success': False, 'executed': True, 'state': state, 'exit_code': code,
                           'output': output.strip(), 'error': f"명령이 끝까지 실행되지 못했습니다: {state}",
                           **({'cleanup': held['cleanup']} if held.get('cleanup') else {})}, ensure_ascii=False)
    preflight = held.get('preflight') or {}
    # 명령이 끝날 때 살아 있던 하위 프로세스를 몸이 함께 끝냈으면 그 사실을 결과에 싣는다. 말하지 않으면 낸 쪽은
    # 백그라운드로 띄운 일이 계속 도는 줄 안다(에피소드 6192: 죽은 평가를 280초 기다렸다).
    left = held.get('left_behind') or {}
    if structured:
        return json.dumps({**shape, 'success': code == 0, 'executed': True, 'state': state, 'exit_code': code,
                           'output': output.strip(), **({'left_behind': left} if left else {}),
                           **({'preflight': preflight, 'diagnostics': held.get('diagnostics')}
                              if preflight.get('status') == 'unsupported' else {})}, ensure_ascii=False)
    if code:
        output += f"\n[exit code: {code}]"
    if left.get('note'):
        output = output.rstrip() + f"\n[{left['note']}]"
    # Preserve the successful text contract; unsupported coverage is explicit.
    if preflight.get('status') == 'unsupported':
        return json.dumps({'success': code == 0, 'executed': True, 'exit_code': code, 'output': output.strip(),
                           'preflight': preflight, 'diagnostics': held.get('diagnostics')}, ensure_ascii=False)
    return output.strip() if output else "(명령어가 출력 없이 완료됨)"
