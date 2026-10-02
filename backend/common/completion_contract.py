"""Process identity and numeric transport compatibility, without host services."""
import os
import sys

# CLI clients require a numeric timeout. Stay below JS's signed 32-bit ms timer
# ceiling. This is a transport compatibility bound, never the IBL job budget.
MCP_CLIENT_TIMEOUT_S = (2**31 - 1) // 1000


def process_birth_time(process):
    """macOS 신원은 시계 보정 전 커널 출생값으로 비교한다.

    psutil 7.2의 공개 create_time()은 모듈 import 이후 NTP 보정을 더하므로
    같은 PID도 장수 제어자와 새 워커에서 값이 달라진다. macOS의 내부
    monotonic=True는 같은 epoch 형식의 보정 전 값이라 기존 영수증도 유지한다.
    이 옵션 이전 psutil은 공개 메서드가 커널 값을 그대로 반환했다.
    """
    if sys.platform == "darwin":
        try:
            return process._proc.create_time(monotonic=True)
        except TypeError:
            return process.create_time()
    return process.create_time()



def process_identity():
    import psutil
    return {'pid': os.getpid(), 'born': process_birth_time(psutil.Process())}


def owner_alive(owner):
    if not isinstance(owner, dict) or not owner.get('pid') or not owner.get('born'):
        return None  # old records have no trustworthy owner
    import psutil
    try:
        p = psutil.Process(owner['pid'])
        return process_birth_time(p) == owner['born'] and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError, ValueError, TypeError, OverflowError):
        return None

