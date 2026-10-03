"""현재 승인 수리의 신원과 지원 도구 경계. 도구 이름 목록은 해당 구현자가 소유한다."""
def active():
    from thread_context import get_current_task_id, get_current_agent_id
    from red_grant import active_grant
    return active_grant(task_id=get_current_task_id(), agent_id=get_current_agent_id())


def guard_tool(handler, name, payload):
    if active():
        check = getattr(handler, "repair_safe_call", None)
        if not check or not check(name, payload):
            raise PermissionError("이 도구의 자기수리 격리는 미지원입니다. 사본 파일 도구 또는 격리 셸을 사용하세요")


def activation_only():
    from repair_continuation import current
    row = current() or {}
    return (row.get("result") or {}).get("outcome") == "healthy"


def guard_route():
    """사본 실행에 연결되지 않은 직접 실행 경로는 지원을 주장하지 않는다."""
    if active():
        raise PermissionError("이 실행 경로는 자기수리 격리를 지원하지 않습니다. 사본 파일 도구 또는 격리 셸을 사용하세요")
