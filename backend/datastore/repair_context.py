"""자기수리는 코드의 작업 대상을 바꾼다. 일반 도구의 권한은 기존 정책이 소유한다."""


def active():
    from thread_context import get_current_task_id, get_current_agent_id
    from red_grant import active_grant
    return active_grant(task_id=get_current_task_id(), agent_id=get_current_agent_id())


def activation_only():
    from repair_continuation import current
    row = current() or {}
    return (row.get("result") or {}).get("outcome") == "healthy"
