"""Synchronous command compatibility and resumable process sessions."""
import json
import subprocess


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
        if h._red_grant_active() and tool_input.get("mode") == "session":
            return json.dumps({"success": False, "error": "수리 실행 범위의 세션은 현재 지원하지 않습니다"})
        if h._red_grant_active():
            return json.dumps(h._load_sibling("repair_tool_scope").run_shell(
                h, command, timeout), ensure_ascii=False)
        if tool_input.get("mode") == "session":
            from process_sessions import start
            return json.dumps(start(command, project_path, io=tool_input.get("io", "pipe"),
                                    request_id=tool_input.get("request_id"),
                                    yield_ms=tool_input.get("yield_ms", 1000),
                                    lifetime=tool_input.get("lifetime", "task")), ensure_ascii=False)
        from command_preflight import check, default_argv, blocked, rejection
        argv = default_argv(command)
        preflight = check(argv, cwd=project_path)
        if blocked(preflight):
            return json.dumps(rejection(preflight), ensure_ascii=False)
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}" if output else result.stderr

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        # Preserve the successful text contract; unsupported coverage is explicit.
        if preflight['status'] == 'unsupported':
            return json.dumps({'success': result.returncode == 0, 'executed': True,
                               'exit_code': result.returncode, 'output': output.strip(),
                               'preflight': preflight}, ensure_ascii=False)
        return output.strip() if output else "(명령어가 출력 없이 완료됨)"

    except subprocess.TimeoutExpired:
        return f"Error: 명령어 실행 시간 초과 ({timeout}초)"
    except Exception as e:
        return f"Error: 명령어 실행 실패: {e}"
