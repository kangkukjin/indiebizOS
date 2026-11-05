"""사본의 실제 검사와 적용 기록을 연결한다. 원래 업무 완료와 분리한다."""


def execution_stream(stream):
    """같은 root의 실행자 하나만 사본을 소유한다. 상태 조회는 이 경로를 열지 않는다."""
    from repair_context import active, activation_only
    if not active() or activation_only():
        yield from stream
        return
    from repair_continuation import current, key, state_root
    from thread_context import get_current_task_id
    from restart_protocol import OwnerLock
    row = current() or {}
    root = key(row.get("root_task_id") or get_current_task_id())
    lock = OwnerLock(state_root() / "repair_sessions" / ("owner-" + root + ".lock"))
    if not lock.acquire():
        raise RuntimeError("같은 수리 사본을 다른 실행자가 수정 중입니다")
    try:
        yield from stream
    finally:
        lock.close()


def requires_code_receipts(controller):
    """RED 권한이 아니라 실제 코드 후보/적용 인계가 코드 완료 절차를 결정한다."""
    from repair_continuation import current, key, staging_session
    from runtime_utils import get_base_path
    previous = current() or {}
    base = get_base_path()
    task = previous.get("staging_task_id") or previous.get("task_id") or controller.task
    path = base / "data/system_ai_state/repair_sessions" / (key(task) + ".json")
    try:
        session = staging_session(task, base)
    except (OSError, ValueError):
        return True
    if not session:
        # 평가 재개 자체는 코드 인계가 아니다. 실제 후보/적용 대상만 근거다.
        return path.exists() or bool(previous.get("worktree") or previous.get("job_path"))
    if not isinstance(session, dict):
        return True
    if session.get('repair_policy') == 2 and session.get('status') != 'staging':
        # Publication changes the activation mechanism, not the completion
        # contract. The sealed candidate still needs its application receipts.
        return True
    if session.get('program_activation') and program_published(base, session):
        return False
    if session.get("component_activation") and component_published(base, session):
        # 부품 게시 영수증은 이미 완료됐다. 원래 업무/수리 목표는 일반 최종평가가
        # 새 호출 결과로 판단하며 전체 세대의 교체 영수증을 요구하지 않는다.
        return False
    if session.get("status") != "staging":
        return True
    try:
        from red_apply import _load_handler
        candidate = _load_handler({"repo": str(base)})._staging_mod()._candidate
        candidate.collect(str(base), session)  # 셸로 쓴 미수집 변경도 포함한다.
        return bool(session["files"])
    except (OSError, ValueError, RuntimeError, KeyError):
        return True  # 사본을 확인하지 못했으면 코드 반영 검사를 생략하지 않는다.


def component_published(base, session):
    import subprocess
    import component_registry as components
    from runtime_utils import get_code_root
    if session.get("status") != "applied" or not session.get("verified"):
        return False
    commit = (session.get("commit") or {}).get("commit")
    if not commit or not session["commit"].get("success"):
        return False
    try:
        specs = components.registry(get_code_root())
        for entry in session["component_activation"]:
            spec, version = specs[entry["spec"]["id"]], entry["version"]
            if components.sha(components.active_source(base, get_code_root(), spec)) != version:
                return False
            stored = subprocess.run(["git", "show", commit + ":" + spec["source"]], cwd=base,
                                    capture_output=True, timeout=30)
            if stored.returncode or components.sha(stored.stdout) != version:
                return False
        return bool(session["component_activation"])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False


def program_published(base, session):
    import hashlib
    import subprocess
    from program_versions import activation_matches
    from runtime_utils import get_code_root
    committed = session.get('commit') or {}
    if session.get('status') != 'applied' or not session.get('verified') or not committed.get('success'):
        return False
    try:
        if not activation_matches(base, get_code_root(), session):
            return False
        for rel, item in session['sealed'].items():
            result = subprocess.run(['git', 'show', committed['commit'] + ':' + rel],
                                    cwd=base, capture_output=True, timeout=30)
            if item['after'] is None:
                if result.returncode == 0:
                    return False
            elif result.returncode or hashlib.sha256(result.stdout).hexdigest() != item['after']['sha']:
                return False
        return True
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        return False


def completion_error(controller):
    if not controller.repair_granted or not requires_code_receipts(controller):
        return None
    from repair_continuation import current, key, staging_session
    from runtime_utils import get_base_path
    previous = current() or {}
    session_key = key(previous.get("staging_task_id") or previous.get("task_id") or controller.task)
    try:
        session = staging_session(session_key, get_base_path())
    except (OSError, ValueError):
        return "수리 기록을 읽지 못해 코드 적용을 확인할 수 없습니다"
    if not isinstance(session, dict) or not session:
        return "코드 적용 인계의 수리 기록을 찾지 못했습니다"
    if session.get("repair_policy") == 2:
        from repair_policy import completion
        passed, reason = completion(session, previous, get_base_path())
        return None if passed else reason
    if session.get("status") != "applied":
        return "수리 사본이 아직 정본에 반영되지 않았습니다. 사본 준비와 전체 완료는 다릅니다"
    if not (session.get("commit") or {}).get("success"):
        return "정본 반영은 확인했으나 수리 델타의 커밋이 완료되지 않았습니다"
    return None


def prepare(controller, repo, session, verify, candidate):
    from repair_policy import VERSION, failure, prepare as prepare_receipts
    if controller.cancelled() or not controller.repair_granted:
        return failure("ownership", "취소됐거나 수리 권한이 없습니다")
    # 아직 적용하지 않은 이전 사본도 같은 검사·적용 경로를 사용한다.
    session["repair_policy"] = VERSION
    controller._repair_completion_policy = VERSION
    controller.framing = {**(controller.framing or {}), "_repair_policy": VERSION}
    result = prepare_receipts(controller, repo, session, verify, candidate)
    controller._repair_failure = None if result.get("success") else result
    return result
