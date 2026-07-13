"""phone_jobs.py — 맥→폰 푸시 작업 큐 (LTE/CGNAT 우회 반전 전달).

폰이 LTE(통신사 NAT) 뒤에 있으면 맥이 폰의 등록 URL 로 직접 못 들어간다(인바운드 차단).
그래서 방향을 뒤집는다: 폰의 기존 heartbeat(/nodes/heartbeat)가 롱폴로 승격돼
"작업 있어?" 를 물으며 hold 하고, 맥은 여기 큐에 작업을 넣어 그 응답에 실어 내려보낸다.
폰이 실행 결과를 /nodes/job-result 로 회신하면, 대기 중이던 포워드(wait_result)가
동기적으로 받아간다 → ibl_engine._forward_to_phone 의 동기 의미가 큐 경로에서도 보존된다.

동기화는 threading 프리미티브: 엔진 포워드는 동기 스레드에서 돌고, FastAPI 핸들러는
anyio.to_thread 로 워커 스레드에서 pull_blocking 을 hold 한다(이벤트 루프 비차단).
큐는 인메모리 — 백엔드 재시작 시 유실되지만 푸시 op(클립보드·알림)는 재시도가 싸다.
"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_QUEUES: Dict[str, List[dict]] = {}          # device_id -> 대기 작업
_JOB_EVENTS: Dict[str, threading.Event] = {}  # device_id -> 작업 도착 신호
_RESULTS: Dict[str, dict] = {}                # job_id -> {result, ts}
_RESULT_EVENTS: Dict[str, threading.Event] = {}

JOB_TTL = 600.0     # 폰이 이 시간 안에 안 당겨가면 작업 폐기(낡은 클립보드 밀어넣기 방지)
RESULT_TTL = 300.0  # 대기자가 이미 떠난 결과의 보존 시간


def _job_event(device_id: str) -> threading.Event:
    with _LOCK:
        ev = _JOB_EVENTS.get(device_id)
        if ev is None:
            ev = _JOB_EVENTS[device_id] = threading.Event()
        return ev


def _gc_locked(now: float) -> None:
    """_LOCK 보유 상태에서 호출 — 낡은 결과/작업 정리."""
    stale = [k for k, v in _RESULTS.items() if now - v.get("ts", 0) > RESULT_TTL]
    for k in stale:
        _RESULTS.pop(k, None)
        _RESULT_EVENTS.pop(k, None)
    for did, q in list(_QUEUES.items()):
        _QUEUES[did] = [j for j in q if now - j.get("ts", 0) <= JOB_TTL]


def enqueue(device_id: str, code: str, agent_id: Optional[str] = None) -> str:
    """폰이 당겨갈 작업 적재. code = 폰 /ibl/execute 에 그대로 넘길 IBL 코드."""
    job = {"id": uuid.uuid4().hex[:12], "code": code, "ts": time.time()}
    if agent_id:
        job["agent_id"] = agent_id
    with _LOCK:
        _gc_locked(job["ts"])
        _QUEUES.setdefault(device_id, []).append(job)
    _job_event(device_id).set()
    return job["id"]


def pull_blocking(device_id: str, wait: float = 0.0) -> List[dict]:
    """대기 작업 전량 회수. wait>0 이면 작업 도착까지 최대 wait초 hold(롱폴).

    신호 유실 방지: 이벤트를 먼저 clear 한 뒤 큐를 확인한다 — 확인 후 도착한
    작업은 set() 이 wait 를 즉시 깨운다.
    """
    deadline = time.time() + max(0.0, float(wait))
    ev = _job_event(device_id)
    while True:
        ev.clear()
        now = time.time()
        with _LOCK:
            q = _QUEUES.get(device_id) or []
            fresh = [j for j in q if now - j.get("ts", 0) <= JOB_TTL]
            _QUEUES[device_id] = []
        if fresh or now >= deadline:
            return fresh
        ev.wait(timeout=max(0.05, deadline - time.time()))


def set_result(job_id: str, result: Any) -> None:
    """폰의 실행 결과 회신 — 대기 중인 wait_result 를 깨운다."""
    with _LOCK:
        _RESULTS[job_id] = {"result": result, "ts": time.time()}
        ev = _RESULT_EVENTS.get(job_id)
        _gc_locked(time.time())
    if ev:
        ev.set()


def wait_result(job_id: str, timeout: float = 20.0) -> Any:
    """작업 결과를 동기 대기. 시간 내 미도착이면 None(호출부가 queued 로 응답)."""
    with _LOCK:
        if job_id in _RESULTS:
            return _RESULTS.pop(job_id).get("result")
        ev = _RESULT_EVENTS.setdefault(job_id, threading.Event())
    hit = ev.wait(timeout=timeout)
    with _LOCK:
        _RESULT_EVENTS.pop(job_id, None)
        entry = _RESULTS.pop(job_id, None)
    return entry.get("result") if (hit and entry) else None
