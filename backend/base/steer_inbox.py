"""steer_inbox.py — 턴 중 조향(steer) 인박스 (2026-08-15)

돌고 있는 에이전트에게 **멈추지 않고** 지시를 밀어 넣는 통로. 중단(cancel)이 유일한
개입 수단이던 갭의 해소 — 관측 3겹(스텝 원장·역할 기록·반복 가드) 위의 첫 조종 조각.

원리(dsh steer/inject 의 이음매 번역): 조향 메시지를 키(agent_id, task_id)별 인박스에 넣어 두면,
그 에이전트의 **다음 도구 결과**에 부록으로 실려 모델에게 도달한다 — 루프를 뜯지 않고
반복 가드와 같은 전달 채널을 쓴다. 배달 어댑터 둘(두-경로 대칭):
  ①직결 경로: system_tools.execute_tool 래퍼 (인프로세스 프로바이더 전부)
  ②클로드 코드 경로: api_ibl /ibl/execute (MCP 호출 = req.agent_id 명시된 것만 —
    앱/수동 모드의 결정론 결과를 오염시키지 않는 게이트)

도구 없는 종료도 공통 대화 경계가 take_or_seal로 확인한다. 접수와 종료 확정은
같은 잠금을 사용한다. 전달과 처리 완료는 구분하며 실패·취소의 미처리 지시는
주입된 journal 콜백을 통해 원래 대화 사건에 남긴다.
"""
import threading
import sqlite3
from contextlib import contextmanager
from itertools import count
from typing import List
from thread_context import execution_key

_inbox: dict = {}   # (agent_id, task_id) -> 사용자 지시 봉투 목록
_active: dict = {}  # 등록 별칭도 같은 작업의 정규 키로 해소
_sequence = count(1)
_lock = threading.Lock()
_journals: dict = {}
_delivered: dict = {}
_sealed: set = set()
_MAX_PER_KEY = 5        # 키당 대기 조향 상한 (초과 시 새 접수 거절)
_MAX_TEXT = 2000        # 조향 1건 길이 상한


@contextmanager
def task_scope(agents, task_id, journal=None):
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
            _inbox[owner] = sorted(queued, key=lambda row: row["sequence"])
        _sealed.discard(owner)
        _journals[owner] = journal
        _delivered[owner] = []
    try:
        yield
    finally:
        with _lock:
            left = len(_inbox.get(owner, []))
            _journals.pop(owner, None)
            delivered = _delivered.pop(owner, [])
            if journal:
                # 영속 사건이 다음 턴 인계를 소유한다. 같은 task 재개 시 메모리 중복 배달 방지.
                _inbox.pop(owner, None)
            elif delivered:
                # 저장소 없는 내부 실행도 미확정 배달을 조용히 버리지 않는다.
                _inbox[owner] = delivered + _inbox.get(owner, [])
            _sealed.discard(owner)
            for key in keys:
                if _active.get(key) == owner:
                    _active.pop(key, None)
        if left:
            print(f"[조향] 미처리 {left}건 보존 — 작업 종료")


_held: dict = {}    # task_id -> 겹친 수. 턴 뒤 마감(작업 닫기)까지 잇는 표면의 수명


@contextmanager
def turn_hold(task_id):
    """표면이 한 작업의 턴과 **그 뒤의 마감**까지 쥐고 있음을 알린다(긴문장 29회차 L29-1).

    task_scope 는 모델 턴만 덮는다 — 턴이 끝난 뒤 표면이 작업을 닫기 전의 틈에 같은 작업으로 온 메시지가
    새 턴을 열면 답이 둘이 된다. 마감까지 한 덩어리로 도는 표면은 이 수명으로 감싼다."""
    if not task_id:
        yield
        return
    with _lock:
        _held[task_id] = _held.get(task_id, 0) + 1
    try:
        yield
    finally:
        with _lock:
            left = _held.get(task_id, 0) - 1
            if left > 0:
                _held[task_id] = left
            else:
                _held.pop(task_id, None)


def task_busy(task_id) -> bool:
    """이 작업의 턴이 지금 살아 있는가(모델 턴 또는 표면의 마감). 같은 작업으로 온 메시지는 그동안 새 턴을 열 수 없다."""
    if not task_id:
        return False
    with _lock:
        return task_id in _held or any(key[1] == task_id for key in _active)


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


def post(key: str, text: str, task_id=None, *, require_active=False, request_id=None) -> int:
    """저장 성공 뒤 접수한다. 가득 찬 큐·긴 지시는 기존 내용을 버리지 않고 거절한다."""
    text = (text or "").strip()
    if not key or not text:
        return 0
    if len(text) > _MAX_TEXT:
        raise ValueError(f"조향은 {_MAX_TEXT}자 이내로 입력해주세요. 접수하지 않았습니다")
    with _lock:
        key = execution_key(key, task_id)
        if require_active and key not in _active:
            raise ValueError("대상 작업이 아직 시작되지 않았거나 이미 종료됐습니다")
        key = _active.get(key, key)
        if request_id:
            prior = next((r for r in _inbox.get(key, []) + _delivered.get(key, [])
                          if r.get("request_id") == request_id), None)
            if prior:
                if prior["instruction"] != text:
                    raise ValueError("같은 요청 신원으로 다른 조향을 보낼 수 없습니다")
                return max(1, len(_inbox.get(key, [])))
        if key in _sealed:
            raise ValueError("응답이 이미 확정되었습니다. 새 메시지로 보내주세요")
        q = _inbox.setdefault(key, [])
        if len(q) >= _MAX_PER_KEY:
            raise ValueError("대기 조향이 가득 찼습니다. 기존 지시를 보존하며 새 지시는 접수하지 않았습니다")
        from uuid import uuid4
        row = {"id": uuid4().hex, "source": "user", "target": {"agent": key[0], "task": key[1]},
               "sequence": next(_sequence), "instruction": text, "request_id": request_id}
        journal = _journals.get(key)
        if journal:
            try:
                journal("steer.accepted", row)
            except (OSError, sqlite3.Error) as exc:
                raise ValueError("추가 지시를 저장하지 못해 접수하지 않았습니다. 다시 보내주세요") from exc
        q.append(row)
        return len(q)


def _take(key):
    q = _inbox.get(key, [])
    journal = _journals.get(key)
    if q and journal:
        journal("steer.delivered", {"ids": [row["id"] for row in q]})
    _inbox.pop(key, None)
    if q:
        _delivered.setdefault(key, []).extend(q)
    return [row["instruction"] for row in q]


def drain(key: str, task_id=None) -> List[str]:
    """도구 결과에 전달한다. 최종 응답 확정 전까지 처리 완료로 보지 않는다."""
    with _lock:
        key = execution_key(key, task_id)
        return _take(_active.get(key, key))


def take_or_seal(key, task_id):
    """대기가 있으면 전달, 없으면 접수를 원자적으로 닫는다."""
    with _lock:
        key = _active.get((key, task_id), (key, task_id))
        if _inbox.get(key):
            return _take(key)
        _sealed.add(key)
        return []


def complete(key, task_id):
    """성공 응답이 확정된 뒤에만 전달한 지시를 처리 완료로 기록한다."""
    with _lock:
        key = _active.get((key, task_id), (key, task_id))
        rows = _delivered.get(key, [])
        journal = _journals.get(key)
        if rows and journal:
            journal("steer.completed", {"ids": [row["id"] for row in rows]})
        _delivered[key] = []


def hold(key, task_id, reason):
    """실패·취소는 재실행하지 않고 미처리 상태와 사유를 보존한다."""
    with _lock:
        key = _active.get((key, task_id), (key, task_id))
        _sealed.add(key)
        rows = _delivered.get(key, []) + _inbox.get(key, [])
        journal = _journals.get(key)
        if rows and journal:
            journal("steer.held", {"ids": [row["id"] for row in rows], "reason": reason})
        return len(rows)


def clear(key: str, task_id=None) -> int:
    """명시적 관리용 삭제. 정상 턴 종료에는 사용하지 않는다."""
    with _lock:
        key = execution_key(key, task_id)
        key = _active.get(key, key)
        _delivered.pop(key, None)
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
