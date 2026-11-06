"""Resident process task adapters."""
from remote_process_sessions import status, control, cancel


def status_control(ref, params):
    return control(ref, params)


def status_cancel(ref):
    return cancel(ref)
