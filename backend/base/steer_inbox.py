"""steer_inbox.py — 턴 중 조향(steer) 인박스 (2026-08-15)

돌고 있는 에이전트에게 **멈추지 않고** 지시를 밀어 넣는 통로. 중단(cancel)이 유일한
개입 수단이던 갭의 해소 — 관측 3겹(스텝 원장·역할 기록·반복 가드) 위의 첫 조종 조각.

원리(dsh steer/inject 의 이음매 번역): 조향 메시지를 키(agent_id, task_id)별 인박스에 넣어 두면,
그 에이전트의 **다음 도구 결과**에 부록으로 실려 모델에게 도달한다 — 루프를 뜯지 않고
반복 가드와 같은 전달 채널을 쓴다. 배달 어댑터 둘(두-경로 대칭):
  ①직결 경로: system_tools.execute_tool 래퍼 (인프로세스 프로바이더 전부)
  ②클로드 코드 경로: api_ibl /ibl/execute (MCP 호출 = req.agent_id 명시된 것만 —
    앱/수동 모드의 결정론 결과를 오염시키지 않는 게이트)

한계(정직): 도구를 더 부르지 않는 턴에는 배달할 수 없다 — 미배달분은 턴 종료 시
폐기되고 로그에 남는다(다음 턴으로 새는 stale 조향 방지). 조향은 지시의 *주입*이지
보장된 *수신*이 아니다.
"""
import threading
import time
from contextlib import contextmanager
from itertools import count
from typing import List
from thread_context import execution_key

_inbox: dict = {}   # (agent_id, task_id) -> 사용자 지시 봉투 목록
_active: dict = {}  # 등록 별칭도 같은 작업의 정규 키로 해소
_sequence = count(1)
_lock = threading.Lock()
_MAX_PER_KEY = 5        # 키당 대기 조향 상한 (초과 시 오래된 것부터 밀어냄)
_MAX_TEXT = 2000        # 조향 1건 길이 상한
_TTL_SECONDS = 1800     # 30분 지난 조향은 배달하지 않음 (유령 방지)


@contextmanager
def task_scope(agents, task_id):
    """감독 비활성 턴도 등록한다. 별칭과 미배달분의 종료 정리는 이 수명이 소유한다."""
    agents = list(dict.fromkeys(agent for agent in agents if agent))
    keys = [execution_key(agent, task_id) for agent in agents]
    owner = keys[0] if keys else None
    with _lock:
        if any(key in _active for key in keys):
            raise RuntimeError("이미 실행 중인 조향 대상 작업입니다")
        queued = []
        for key in keys:
            _active[key] = owner
            queued.extend(_inbox.pop(key, []))
        if queued:
            _inbox[owner] = sorted(queued, key=lambda row: row["sequence"])[-_MAX_PER_KEY:]
    try:
        yield
    finally:
        with _lock:
            left = len(_inbox.pop(owner, []))
            for key in keys:
                if _active.get(key) == owner:
                    _active.pop(key, None)
        if left:
            print(f"[조향] 미배달 {left}건 폐기 — 작업 종료")


def resolve_task(agent_id, task_id=None):
    """외부 조향의 대상 확인. 작업 생략은 활성 작업이 정확히 하나일 때만 허용한다."""
    with _lock:
        tasks = {key[1] for key in _active if key[0] == agent_id}
    if task_id is not None:
        if task_id in tasks:
            return task_id
        raise ValueError("해당 에이전트의 활성 task_id가 아닙니다")
    if len(tasks) == 1:
        return next(iter(tasks))
    raise ValueError("활성 작업이 없거나 여러 개입니다. 대상 task_id를 지정하세요")


def post(key: str, text: str, task_id=None, *, require_active=False) -> int:
    """조향 1건 접수. 반환 = 그 키의 대기 건수."""
    text = (text or "").strip()[:_MAX_TEXT]
    if not key or not text:
        return 0
    with _lock:
        key = execution_key(key, task_id)
        if require_active and key not in _active:
            raise ValueError("대상 작업이 아직 시작되지 않았거나 이미 종료됐습니다")
        key = _active.get(key, key)
        q = _inbox.setdefault(key, [])
        now = time.time()
        q.append({"source": "user", "target": {"agent": key[0], "task": key[1]},
                  "sequence": next(_sequence), "expires_at": now + _TTL_SECONDS,
                  "conditions": None, "instruction": text})
        del q[:-_MAX_PER_KEY]
        return len(q)


def drain(key: str, task_id=None) -> List[str]:
    """대기 조향 전부 회수(비움). TTL 지난 것은 버린다."""
    with _lock:
        key = execution_key(key, task_id)
        key = _active.get(key, key)
        q = _inbox.pop(key, [])
    now = time.time()
    return [row["instruction"] for row in q if now <= row["expires_at"]]


def clear(key: str, task_id=None) -> int:
    """턴 종료 시 미배달분 폐기. 반환 = 폐기 건수 (0이면 조용)."""
    with _lock:
        key = execution_key(key, task_id)
        key = _active.get(key, key)
        return len(_inbox.pop(key, []))


def render(texts: List[str]) -> str:
    """배달 부록 렌더 — 반복 가드 조언과 같은 결(부록, 결과 변조 아님).
    자기예약 콘텐츠와 같은 위생: 내용은 사용자 지시로 명시(untrusted 프레이밍의 역방향 —
    이건 진짜 사용자에게서 온 것임을 표시)."""
    if not texts:
        return ""
    body = "\n".join(f"- {t}" for t in texts)
    return ("\n\n[사용자 조향] 작업이 도는 동안 사용자가 지시를 보냈습니다. "
            "지금까지의 계획보다 이 지시를 우선해 즉시 반영하세요:\n" + body)
