"""회원 턴의 사적 임시 상태. contextvars는 공통 워커와 함께 이동한다."""
import contextvars
import logging
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_turn = contextvars.ContextVar("member_turn", default=None)
_install_lock = threading.Lock()


def is_member():
    import principal
    return principal.current().kind == principal.KIND_MEMBER


def current():
    return _turn.get()


def adopt(state):
    """공통 thread_context 스냅샷을 거치는 워커에 취소·한도·임시 경로를 함께 옮긴다."""
    _turn.set(state)
    from common.spill import _spill_root
    _spill_root.set(str(Path(state["path"]) / "spill") if state else None)


def private_path(name):
    state = current()
    if state is None:
        raise PermissionError("회원 턴 문맥이 없습니다")
    root = Path(state["path"]).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("회원 턴 경로 이탈")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def turn_scope(path, device_id, task_id, cancel, policy):
    state = {"path": str(path), "device_id": device_id, "task_id": task_id,
             "cancel": cancel, "policy": policy, "step": 0, "lock": threading.Lock(),
             "jobs": set(), "deadline": time.monotonic() + float(policy.get("deadline_s", 180))}
    from common.spill import _spill_root
    spill_token = _spill_root.set(str(Path(path) / "spill"))
    token = _turn.set(state)
    try:
        yield state
    finally:
        _turn.reset(token)
        _spill_root.reset(spill_token)


class _PrivateOutput:
    """프로세스 출력 객체는 공유하되 필터 판정은 호출 문맥별이다. 다른 턴은 그대로 출력한다."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        if not is_member():
            return self.stream.write(text)
        return len(text)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def install_output_guard():
    with _install_lock:
        for name in ("stdout", "stderr"):
            stream = getattr(sys, name)
            if not isinstance(stream, _PrivateOutput):
                setattr(sys, name, _PrivateOutput(stream))
        # 이미 생성된 FileHandler도 회원 본문을 쓰지 않는다.
        if not getattr(logging, "_member_factory_installed", False):
            original = logging.getLogRecordFactory()
            def factory(*args, **kwargs):
                record = original(*args, **kwargs)
                if is_member():
                    record.msg, record.args = "[member] private event", ()
                    record.exc_info = record.exc_text = record.stack_info = None
                return record
            logging.setLogRecordFactory(factory)
            logging._member_factory_installed = True
