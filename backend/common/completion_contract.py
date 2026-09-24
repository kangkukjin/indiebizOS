"""Process identity and numeric transport compatibility, without host services."""
import os

# CLI clients require a numeric timeout. Stay below JS's signed 32-bit ms timer
# ceiling. This is a transport compatibility bound, never the IBL job budget.
MCP_CLIENT_TIMEOUT_S = (2**31 - 1) // 1000


def process_identity():
    import psutil
    return {'pid': os.getpid(), 'born': psutil.Process().create_time()}


def owner_alive(owner):
    if not isinstance(owner, dict) or not owner.get('pid') or not owner.get('born'):
        return None  # old records have no trustworthy owner
    import psutil
    try:
        p = psutil.Process(owner['pid'])
        return p.create_time() == owner['born'] and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError, ValueError, TypeError, OverflowError):
        return None

