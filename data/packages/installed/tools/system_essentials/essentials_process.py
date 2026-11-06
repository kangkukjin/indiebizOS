"""Process receipt adapter; transport lives in services."""
from process_sessions import task_status, task_cancel, task_control


def status(ref):
    return task_status(ref)


def status_cancel(ref):
    return task_cancel(ref)


def status_control(ref, params):
    return task_control(ref, params)


def rewind_status(ref):
    from conversation_rewind import task_status
    return task_status(ref)


def rewind_status_cancel(ref):
    from conversation_rewind import task_cancel
    return task_cancel(ref)
