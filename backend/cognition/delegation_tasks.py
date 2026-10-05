"""위임·백그라운드 작업의 공통 접수증·상태 투영·동기 대기 (2026-10-05).

접수증 통화는 이제 base 의 task_receipts(③ 작업 수명)가 정본이고 이 모듈은 그 `delegation` 종류의 어댑터다.

왜 이 모듈인가 — 설계 정본 docs/ASYNC_DELEGATION_REPAIR_DESIGN_2026_10_05.md.
  ① HTTP background 접수가 "작업을 시작했습니다" 문구만 돌려주고 task_id 가 없어 런처가
     *새 메시지 번호*로 답을 추측했다(다른 작업의 답을 자기 답으로 회수할 수 있다).
  ② `[others:delegate]{scope:cross, mode:sync}` 가 mode 를 무시하고 접수 응답만 돌려줬고,
     same 의 sync 는 임시 AIAgent 를 따로 만들어 async(상주 러너)와 실행기가 둘이었다.
  ③ 부모가 자식에게 넘기는 봉투에 출처(origin=training)가 없어 훈련이 위임을 지나면
     자식이 실사용으로 기록됐고, 순환 위임(A→B→A)을 막는 장치가 없었다.

이 모듈은 **새 저장소를 만들지 않는다.** 시스템 AI 의 tasks(system_ai_memory)와 프로젝트의
tasks(conversation_db)를 각 소유자가 그대로 유지하고, 여기서는 둘을 같은 모양으로 읽는
투영(task_view)·같은 모양의 접수증(accepted)·동기 대기(await_child)·봉투(envelope/received)만
제공한다. 상태 이름은 코딩 앱(api_coding)의 task/run/cancel 과 같은 결을 따르되 저장소는
섞지 않는다. 투영 상태: queued/running/waiting_children/succeeded/failed/cancelled, 그 밖의
수리 대기 상태(waiting_user 등)는 원문 그대로 보존한다.
"""
import json
import time
from contextlib import contextmanager
from pathlib import Path

from runtime_utils import get_base_path
from thread_context import (
    actor_context, get_current_agent_id, get_current_agent_name, get_current_project_id,
    get_delegation_chain, get_task_origin, set_delegation_chain, set_called_agent,
)

SYSTEM_OWNER = "system"
KIND = "delegation"   # 접수증 통화의 작업 종류(task_receipts)
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})
# 동기 위임 기본 대기 상한(초). 옛 임시 에이전트 경로도 모델 턴 전체를 막았으므로 같은 규모.
# 상한이 끝나도 작업을 실패·취소로 바꾸지 않고 같은 task 의 현재 상태를 돌려준다.
SYNC_WAIT_SECONDS = 600
# HTTP 조회의 제한 대기 상한(초) — 클라이언트가 무한 대기를 지정하지 못한다.
HTTP_WAIT_MAX = 30
POLL_SECONDS = 0.5


class DelegationCycle(ValueError):
    """대상이 이미 조상 사슬에 있다(자기 자신 포함) — 재위임 순환."""


# ── 행위자 식별과 봉투 ─────────────────────────────────────────────────────────

def actor_identity() -> str:
    """현재 스레드 행위자의 식별자. 프로젝트 에이전트='프로젝트:에이전트id', 그 밖='system_ai'."""
    project_id = get_current_project_id() or ""
    agent_id = get_current_agent_id() or get_current_agent_name() or ""
    if project_id and agent_id and agent_id not in ("system_ai", "system_ai_delegation"):
        return f"{project_id}:{agent_id}"
    return "system_ai"


def target_identity(project_id: str, agent_id: str) -> str:
    return f"{project_id}:{agent_id}"


# 봉투 열쇠(송신 send_message 들이 msg_dict 로 복사하는 전부) — origin·chain(2026-10-05 수리) + role·allowed·context(⑨ 위임 범위).
ENVELOPE_KEYS = ("origin", "chain", "role", "allowed", "context")
CONTEXT_MAX_BYTES = 64 * 1024


def narrowed_allowed(requested) -> tuple:
    """⑨ 허용 집합은 **부모 권한을 좁히기만** 한다(principal.narrow 와 같은 방향) — (유효 집합 목록 | None, 잘린 노드 목록).

    부모(현재 스레드 allowed_nodes)가 None(무제한)이면 요청을 그대로(agents.yaml 과 같은 해석 — 표준 코어는 항상 포함).
    요청이 없으면 부모 집합을 그대로 **상속**한다(하위 위임이 조용히 넓어지지 않게). 부모 밖 노드는 잘라내고 이름을 돌려준다."""
    from thread_context import get_allowed_nodes
    from ibl_access import resolve_allowed_nodes
    parent = get_allowed_nodes()
    if requested in (None, "", [], ()):
        return (sorted(parent) if parent else None), []
    names = [str(x).strip() for x in (requested if isinstance(requested, (list, tuple, set)) else [requested]) if str(x).strip()]
    wanted = resolve_allowed_nodes(names) or set()
    if parent is None:
        return sorted(wanted), []
    return sorted(wanted & set(parent)), sorted(wanted - set(parent))


def with_context(message: str, context) -> str:
    """⑨ 구조화 맥락을 메시지에 동봉 — 자식은 LLM 턴이라 JSON 블록이 운반체다(봉투에도 그대로 실린다). 64KB 상한."""
    if context in (None, "", {}, []):
        return message
    text = json.dumps(context, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) > CONTEXT_MAX_BYTES:
        raise ValueError(f"context 가 {CONTEXT_MAX_BYTES // 1024}KB 를 넘습니다 — 파일로 쓰고 경로를 넘기세요")
    return f"{message}\n\n[context — 위임자가 준 구조화 맥락]\n```json\n{text}\n```"


def envelope(target: str, *, role: str = None, allowed=None, context=None) -> dict:
    """자식에게 실어 보낼 봉투. 순환이면 DelegationCycle.

    chain = 조상 행위자 목록 + 나. 대상이 그 안에 있으면(자기 자신 포함) 거절한다.
    origin 은 서버가 실행 문맥에서 정한다 — 모델이 임의로 바꾸지 않는다.
    ⑨ role(프롬프트 조립 선택 — 시스템 AI 위임의 force_role)·allowed(부모 ∩ 요청, 좁히기만·상속)·context(구조화 맥락)."""
    me = actor_identity()
    chain = get_delegation_chain()
    if me not in chain:
        chain = chain + [me]
    if target in chain:
        raise DelegationCycle(
            f"순환 위임: '{target}' 은(는) 이미 위임 사슬 {' → '.join(chain)} 에 있습니다. "
            "같은 요청을 조상에게 되돌려 보내지 말고 직접 수행하거나 부모에게 필요성을 보고하세요.")
    env = {"origin": get_task_origin(), "chain": chain}
    effective, clamped = narrowed_allowed(allowed)
    if effective is not None:
        env["allowed"] = effective
    if clamped:
        env["allowed_clamped"] = clamped
    if role:
        env["role"] = str(role)
    if context not in (None, "", {}, []):
        env["context"] = context
    return env


@contextmanager
def received(msg_dict: dict):
    """수신 측 — 봉투의 origin·chain(·allowed) 을 처리 동안 스레드 컨텍스트에 세우고 끝나면 복원.

    에피소드 시작(start_episode)이 출처를 읽으므로 **그 전에** 들어가야 한다.
    allowed 가 있으면 처리 동안 allowed_nodes 로 세운다 — 실행 관문(판본 1·2)과 프롬프트 어휘 스코핑이 같은 집합을 읽고,
    이 턴이 다시 위임하면 envelope() 이 그것을 부모 집합으로 상속한다."""
    from thread_context import get_allowed_nodes, set_allowed_nodes
    origin = msg_dict.get("origin") if isinstance(msg_dict, dict) else None
    chain = msg_dict.get("chain") if isinstance(msg_dict, dict) else None
    allowed = msg_dict.get("allowed") if isinstance(msg_dict, dict) else None
    prev_chain = get_delegation_chain()
    prev_allowed = get_allowed_nodes()
    set_delegation_chain(chain)
    if isinstance(allowed, (list, tuple, set)) and allowed:
        set_allowed_nodes(set(str(x) for x in allowed))
    try:
        # None 이면 actor_context 가 칸을 건드리지 않는다 — 봉투에 출처가 없는 메시지
        # (스케줄러 하달·앱 버튼)는 러너 스레드의 빈 출처 그대로(fail-closed) 돈다.
        with actor_context(origin=(origin if origin else "")):
            yield
    finally:
        set_delegation_chain(prev_chain)
        set_allowed_nodes(prev_allowed)


@contextmanager
def scoped(*, role: str = None, allowed=None, context=None):
    """⑨ 얇은 통로용 — HTTP 표면(포식 브라우저 등)이 큐를 거치지 않고 **같은 봉투 계약**으로 한 턴을 돌린다.
    envelope() 과 같은 좁힘·상속 규칙, received() 와 같은 집행. yield 값 = 봉투(allowed 가 유효 집합)."""
    env = {"origin": get_task_origin() or None, "chain": get_delegation_chain()}
    effective, clamped = narrowed_allowed(allowed)
    if effective is not None:
        env["allowed"] = effective
    if clamped:
        env["allowed_clamped"] = clamped
    if role:
        env["role"] = str(role)
    if context not in (None, "", {}, []):
        env["context"] = context
    with received(env):
        yield env


# ── 저장소 접근 (소유자별) ────────────────────────────────────────────────────

def project_db(project_id: str):
    """프로젝트 conversations.db — 프로젝트 폴더가 없으면 None."""
    from conversation_db import ConversationDB
    folder = Path(get_base_path()) / "projects" / project_id
    if not folder.is_dir():
        return None
    return ConversationDB(str(folder / "conversations.db"))


def get_task_row(owner: str, task_id: str):
    if owner == SYSTEM_OWNER:
        from system_ai_memory import get_task
        return get_task(task_id)
    db = project_db(owner)
    return db.get_task(task_id) if db else None


def settle_sync(owner: str, parent_task_id: str, child_task_id: str):
    if owner == SYSTEM_OWNER:
        from system_ai_memory import settle_sync_delegation
        return settle_sync_delegation(parent_task_id, child_task_id)
    db = project_db(owner)
    return db.settle_sync_delegation(parent_task_id, child_task_id) if db else None


# ── 상태 투영 ──────────────────────────────────────────────────────────────────

def state_of(row: dict) -> str:
    status = (row or {}).get("status") or "pending"
    if status == "completed":
        return "succeeded"
    if status in ("failed", "cancelled"):
        return status
    if status == "pending":
        return "waiting_children" if (row.get("pending_delegations") or 0) > 0 else "running"
    return status  # waiting_user 등 수리 대기 상태는 그대로


def status_url(owner: str, task_id: str, agent_id: str = None) -> str:
    if owner == SYSTEM_OWNER:
        return f"/system-ai/tasks/{task_id}"
    return f"/projects/{owner}/agents/{agent_id or '-'}/tasks/{task_id}"


def task_view(owner: str, task_id: str, agent_id: str = None):
    """두 저장소를 같은 모양으로 읽는다. 없으면 None. result 는 종료 상태에서만, **전문**."""
    row = get_task_row(owner, task_id)
    if not row:
        return None
    state = state_of(row)
    try:
        ctx = json.loads(row.get("delegation_context") or "{}")
    except (ValueError, TypeError):
        ctx = {}
    if not isinstance(ctx, dict):
        ctx = {}
    responded = {r.get("child_task_id") for r in ctx.get("responses") or [] if isinstance(r, dict)}
    children = [{
        "child_task_id": d.get("child_task_id"),
        "delegated_to": d.get("delegated_to"),
        "mode": d.get("mode") or "async",
        "responded": d.get("child_task_id") in responded,
    } for d in ctx.get("delegations") or [] if isinstance(d, dict)]
    parent_id = row.get("parent_task_id") or None
    parent_owner = None
    if parent_id:
        parent_owner = SYSTEM_OWNER if row.get("requester_channel") == "system_ai" else owner
    terminal = state in TERMINAL_STATES
    return {
        "task_ref": {"kind": KIND, "owner": owner, "task_id": task_id},
        "parent_task_ref": {"kind": KIND, "owner": parent_owner, "task_id": parent_id} if parent_id else None,
        "run_id": row.get("run_id"),
        "parent_run_id": row.get("parent_run_id") or None,
        "state": state,
        "status": row.get("status"),
        "delegated_to": row.get("delegated_to"),
        "requester_channel": row.get("requester_channel"),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
        "pending_children": row.get("pending_delegations") or 0,
        "children": children,
        "result": (row.get("result") or "") if terminal and state != "failed" else None,
        "error": (row.get("result") or "") if state == "failed" else None,
        "status_url": status_url(owner, task_id, agent_id),
    }


def wait_for_task(owner: str, task_id: str, timeout: float, agent_id: str = None, poll: float = POLL_SECONDS):
    """종료 상태가 되거나 timeout 이 끝날 때까지 기다린 뒤 현재 투영을 돌려준다(없으면 None)."""
    deadline = time.monotonic() + max(0.0, float(timeout or 0))
    while True:
        view = task_view(owner, task_id, agent_id)
        if view is None or view["state"] in TERMINAL_STATES:
            return view
        left = deadline - time.monotonic()
        if left <= 0:
            return view
        time.sleep(min(poll, left))


# ── 접수증과 동기 대기 ──────────────────────────────────────────────────────────

def accepted(owner: str, task_id: str, agent_id: str = None, **extra) -> dict:
    """HTTP background 와 위임이 같은 모양으로 돌려주는 접수증."""
    from episode_logger import trajectory_run_id
    import task_receipts
    return task_receipts.receipt(KIND, task_id, owner=owner, status_url=status_url(owner, task_id, agent_id),
                                 run_id=trajectory_run_id(task_id), **extra)


def task_status(ref: dict) -> dict:
    """③ 접수증 어댑터 — task_ref{kind: delegation, owner, task_id} → 공통 투영. routing_system.register_all 이 등록."""
    import task_receipts as T
    owner = ref.get("owner") or SYSTEM_OWNER
    v = task_view(owner, ref["task_id"])
    if v is None:
        return T.view(ref, T.UNKNOWN, error=f"작업 {ref['task_id']} 을(를) {owner} 저장소에서 찾지 못했습니다")
    state = v["state"] if v["state"] in T.STATES else T.RUNNING   # waiting_user 등 수리 대기 = 아직 살아 있음
    progress = {"pending_children": v["pending_children"], "children": v["children"], "status": v["status"]}
    return T.view(ref, state, progress=progress, result=v.get("result"), error=v.get("error"),
                  status_url=v["status_url"], run_id=v.get("run_id"))


def await_child(parent_owner: str, parent_task_id: str, child_owner: str, child_task_id: str, *,
                prev_called: bool, agent_label: str, project_id: str = None, agent_id: str = None,
                timeout: float = None) -> dict:
    """동기 위임 = 접수한 **같은 작업**을 제한 시간 동안 기다린다.

    끝나면 called_agent 플래그를 접수 전 값으로 되돌린다 — 결과를 손에 든 부모의 턴이
    "위임 중"으로 열려 있지 않게. 시간 초과면 실패로 바꾸지 않고 현재 상태와 같은 task 를
    돌려주며, settle_sync 로 그 뒤의 보고가 평소대로 부모 러너에 전달되게 한다."""
    if timeout is None:
        timeout = SYNC_WAIT_SECONDS  # 호출 시점의 모듈 값(시험이 바꿀 수 있게 기본값을 늦게 읽는다)
    view = wait_for_task(child_owner, child_task_id, timeout, agent_id)
    ref = {"owner": child_owner, "task_id": child_task_id}
    url = status_url(child_owner, child_task_id, agent_id)
    if view and view["state"] in TERMINAL_STATES:
        set_called_agent(prev_called)
        return _sync_result(view, agent_label, project_id, ref, url)
    settled = settle_sync(parent_owner, parent_task_id, child_task_id) if parent_task_id else None
    if settled:
        set_called_agent(prev_called)
        again = task_view(child_owner, child_task_id, agent_id)
        if again and again["state"] in TERMINAL_STATES:
            return _sync_result(again, agent_label, project_id, ref, url)
        failed = bool(settled.get("failed"))
        return {"success": not failed, "agent": agent_label, "project": project_id, "sync": True,
                "task_ref": ref, "status_url": url, "state": "failed" if failed else "succeeded",
                **({"error": settled.get("response") or "자식 실패"} if failed
                   else {"response": settled.get("response") or ""})}
    return {
        "success": False, "accepted": True, "sync": True, "agent": agent_label, "project": project_id,
        "task_ref": ref, "status_url": url, "state": (view or {}).get("state") or "unknown",
        "error": (f"동기 대기 {int(timeout)}초가 끝났습니다. 작업 {child_task_id} 은(는) 계속 실행 중이며 "
                  f"결과는 비동기 보고로 도착합니다 — 접수를 완료로 취급하지 마세요."),
    }


def _sync_result(view: dict, agent_label: str, project_id, ref: dict, url: str) -> dict:
    base = {"agent": agent_label, "project": project_id, "sync": True, "task_ref": ref,
            "status_url": url, "state": view["state"]}
    if view["state"] == "succeeded":
        text = view.get("result") or ""
        if not text.strip():
            # ★빈 응답을 성공으로 포장하지 않는다 — 동기 위임의 계약은 '답을 돌려준다'.
            return {**base, "success": False,
                    "error": f"'{agent_label}'이(가) 빈 응답을 반환했습니다. 프로바이더 인증·모델 설정 실패일 수 있습니다."}
        return {**base, "success": True, "response": text}
    return {**base, "success": False, "error": view.get("error") or f"작업이 {view['state']} 상태로 끝났습니다."}
