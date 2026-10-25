"""이번 실행 안에서 동일 입력·동일 결과의 연속 횟수만 관측한다."""
import hashlib
import json
import threading
from contextlib import contextmanager
from uuid import uuid4

THRESHOLDS = (3, 5, 8)  # 표시 빈도이며 실패/종료 기준이 아니다.
_chains = {}
_active = {}
_lock = threading.Lock()


@contextmanager
def execution_scope(agents, task_id):
    from thread_context import execution_key
    keys = [execution_key(a, task_id) for a in dict.fromkeys(agents) if a]
    key = uuid4().hex
    with _lock:
        if any(k in _active for k in keys):
            raise RuntimeError("이미 활성인 반복 관측 실행입니다")
        _chains[key] = None
        for alias in keys:
            _active[alias] = key
    try:
        yield key
    finally:
        with _lock:
            _chains.pop(key, None)
            for alias in keys:
                if _active.get(alias) == key:
                    _active.pop(alias, None)


def advise(execution_key, signature, result_digest):
    """결과를 읽은 뒤 호출한다. 같은 결과도 정상 대기일 수 있으므로 행동은 지시하지 않는다."""
    with _lock:
        if execution_key not in _chains:
            return ""
        chain = _chains[execution_key]
        n = chain[2] + 1 if chain and chain[:2] == (signature, result_digest) else 1
        _chains[execution_key] = (signature, result_digest, n)
    return f"\n\n[반복 관측] 같은 입력으로 같은 결과를 연속 {n}회 관측했습니다." if n in THRESHOLDS else ""


def digest(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def observe_result(tool_name, tool_input, result, agent_id=None, task_id=None, *, read_observation=None):
    """직결·MCP가 같은 백엔드 수명에서 센다. 감독이 켜진 실행은 기존 감독 관측만 사용한다."""
    from thread_context import execution_key
    from supervision_bus import current
    actor = execution_key(agent_id, task_id)
    supervisor = current(*actor)
    if supervisor and supervisor.enabled:
        return ""
    with _lock:
        key = _active.get(actor)
    if key is None:
        return ""
    observed = result
    if tool_name == "execute_ibl":
        from result_read_contract import is_observation_request
        if is_observation_request(tool_input or {}):
            return ""  # 증거 페이지 회수는 실행 횟수가 아니다.
        if read_observation is None:
            return ""  # IBL 표시본은 생산자의 원 결과 해소가 필요하다.
        try:
            observed = read_observation(result)
        except (ValueError, TypeError, KeyError, OSError):
            return ""  # 읽지 못한 원문 대신 잘린 표시본을 관측으로 세지 않는다.
    return advise(key, tool_name + "|" + digest(tool_input), digest(observed))


def inputs_digest(inputs=None):
    return digest(inputs)[:16] if inputs else ""


def reset_all():
    """시험 격리용."""
    with _lock:
        _chains.clear()
        _active.clear()


def append_advisory(raw, advisory):
    if not advisory:
        return raw
    if isinstance(raw, dict):
        return {**raw, "_model_advisory": str(raw.get("_model_advisory", "")) + advisory}
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return str(raw) + advisory
    if isinstance(obj, dict):
        return json.dumps(append_advisory(obj, advisory), ensure_ascii=False)
    return str(raw) + advisory
