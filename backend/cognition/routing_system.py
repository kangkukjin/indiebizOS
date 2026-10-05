"""routing_system.py — 시스템 라우터의 인지 능력 구현 (2026-08-05 감사 ⑦ 후반부).

왜 이 모듈인가: ibl_routing(언어층)의 `_route_system` 이 인지층(system_ai_*·
system_tools·body_ask·world_pulse·switch_runner·ai_agent…)을 14간선으로 직참조해
백엔드 매듭의 심장이었다. 라우터는 이름을 능력 테이블에서 찾을 뿐, **구현은 인지층의
것** — 여기로 이동하고, 조립 루트(boot_common.wire_local_subsystems)가 register_all()
로 테이블을 채운다. 파서 쌍(register_parse)·채팅 스트림 슬롯과 같은 의존 역전 패턴.

행동 불변 원칙: 각 능력 함수의 지연 import 는 옛 ibl_routing 자리 그대로다 —
없는 몸(폰 blocklist 등)에서는 옛날과 똑같이 호출 시점에 같은 에러가 난다.
"""

import json
import os
from pathlib import Path
from typing import Any


# === 위임 기계 — ibl_routing 에서 verbatim 이동 ===

def _delegate_unified(params: dict, project_path: str) -> Any:
    """위임 통합 디스패처 — mode(async/sync/workflow) × scope(same/cross/system).

    2026-10-05 수리(docs/ASYNC_DELEGATION_REPAIR_DESIGN_2026_10_05.md):
      · cross 가 mode 분기보다 먼저 반환해 sync 가 무시되던 것 → cross 도 접수 뒤 같은 task 를 기다린다.
      · same 의 sync 가 임시 AIAgent(별도 실행기)를 만들던 것 → async 와 같은 접수 경로(상주 러너)로
        접수하고 같은 task 를 기다린다. 두 mode 는 '기다리는가'만 다르다.
      · cross/system 의 workflow 는 구현된 적이 없다 → 명시적 미지원 오류(검사기 variant 와 일치).
      · 접수 응답은 delegation_tasks.accepted 모양(task_ref·status_url). 오류는 dict 봉투.
    """
    mode = (params.get("mode") or "async").lower()
    scope = (params.get("scope") or "same").lower()
    if mode not in {"async", "sync", "workflow"} or scope not in {"same", "cross", "system"}:
        return {"success": False, "error": "mode는 async/sync/workflow, scope는 same/cross/system입니다."}
    if mode == "workflow" and scope != "same":
        return {"success": False, "error_type": "capability",
                "error": (f"scope={scope} 의 mode=workflow 는 지원하지 않습니다. 타 프로젝트·시스템 AI 에는 "
                          "자연어 message 로 async/sync 위임하세요(do 는 같은 프로젝트 workflow 전용).")}

    if scope == "system":
        # 시스템 AI(자율주행 top-level)에게 자연어 의도를 fire-and-forget 위임.
        # 프로젝트 에이전트 레지스트리 밖의 자율주행이 대상 — 앱 "생성" 버튼처럼
        # "이거 알아서 해줘"를 넘길 때. report-viewer 가 파이썬 send_message 를 직접
        # 때렸던 그 능력의 일반 어휘화(scope 차원 확장, 새 액션 아님).
        message = params.get("message", params.get("query", ""))
        if not message:
            return {"error": "message 파라미터가 필요합니다. 예: {scope: \"system\", message: \"AI 동향 보고서 써줘\"}"}
        try:
            from system_ai_runner import SystemAIRunner
            from delegation_tasks import DelegationCycle, envelope, with_context
            try:
                env = envelope("system_ai", role=params.get("role"), allowed=params.get("allowed"), context=params.get("context"))
                message = with_context(message, params.get("context"))
            except DelegationCycle as cyc:
                return {"success": False, "error": str(cyc), "error_type": "delegation_cycle"}
            except ValueError as bad:
                return {"success": False, "error": str(bad)}
            # 부모 task 동봉 — fire-and-forget 큐가 스레드 컨텍스트를 잃으므로
            # 여기서 떠서 봉투에 싣는다(claude_code 재진입 env/헤더와 같은 부류,
            # 2026-08-21 ③-b). 없으면 러너 루프가 새로 발급한다.
            _parent_task = None
            try:
                from thread_context import get_current_task_id
                _parent_task = get_current_task_id() or None
            except Exception:
                pass
            # ③ 작업 선발급(2026-10-05): HTTP background 와 같은 접수 계약 — 큐에 올리기 **전에** 시스템 작업 행을
            # 만들어 접수증(task_ref·status_url)이 즉시 조회 가능한 id 를 돌려준다. 러너는 이 id 를 그대로 써서
            # 끝나면 complete_task 로 닫는다(옛 경로는 부모 task id 를 넘겨 자식 작업이 없었다 — 접수증에 id 가 없던 이유).
            import uuid as _uuid
            from system_ai_memory import create_task as _create_system_task
            from_agent = params.get("from_agent") or "앱"
            child_id = f"task_sysai_{_uuid.uuid4().hex[:8]}"
            _create_system_task(task_id=child_id, requester=f"{from_agent}@{Path(project_path).name}",
                                requester_channel="delegate", original_request=message,
                                delegated_to="system_ai", parent_task_id=_parent_task)
            SystemAIRunner.send_message(content=message, from_agent=from_agent,
                                        task_id=child_id, envelope=env)
        except Exception as e:  # noqa: BLE001 — 큐잉 실패는 그대로 보고
            return {"error": f"시스템 AI 위임 실패: {e}"}
        from delegation_tasks import SYSTEM_OWNER, accepted, await_child
        from thread_context import did_call_agent
        receipt = accepted(SYSTEM_OWNER, child_id, queued=True, target="시스템 AI", child_task_id=child_id,
                           parent_task_id=_parent_task, mode=mode,
                           **({"allowed": env["allowed"]} if env.get("allowed") else {}),
                           **({"allowed_clamped": env["allowed_clamped"]} if env.get("allowed_clamped") else {}),
                           message=f"시스템 AI에 요청을 전달했습니다 (task {child_id}). 접수 확인이며 결과는 아직 없습니다.")
        if mode != "sync":
            return receipt
        return await_child(Path(project_path).name, _parent_task, SYSTEM_OWNER, child_id,
                           prev_called=did_call_agent(), agent_label="시스템 AI", project_id=None)

    agent_id_raw = params.get("agent_id", "")
    if isinstance(agent_id_raw, (int, float)):
        agent_id_raw = str(int(agent_id_raw))
    agent_id_raw = str(agent_id_raw or "")
    # 옛 동기 경로는 '프로젝트/에이전트' 를 스스로 풀어 타 프로젝트까지 닿았다 — 그 도달 범위를
    # 유지한다: same 로 왔어도 다른 프로젝트를 가리키면 cross 접수로 보낸다.
    if scope == "same" and mode != "workflow" and "/" in agent_id_raw:
        other_project = agent_id_raw.split("/", 1)[0]
        if other_project and other_project != Path(project_path).name:
            scope = "cross"

    if scope == "cross":
        from system_ai_tools import _execute_call_project_agent
        if not agent_id_raw:
            return {"error": "agent_id가 필요합니다. 예: '의료/내과'"}
        # '프로젝트/에이전트' 자동 분리 (call_project_agent는 둘을 분리해서 받음)
        if "project_id" not in params and "/" in agent_id_raw:
            project_id, agent_id = agent_id_raw.split("/", 1)
            call_input = {**params, "project_id": project_id, "agent_id": agent_id}
        else:
            call_input = dict(params)
        call_input["mode"] = mode
        from thread_context import did_call_agent, get_current_task_id
        prev_called = did_call_agent()
        accept = _execute_call_project_agent(call_input)
        if mode != "sync" or not isinstance(accept, dict) or not accept.get("success"):
            return accept
        from delegation_tasks import SYSTEM_OWNER, await_child
        return await_child(SYSTEM_OWNER, accept.get("parent_task_id") or get_current_task_id(),
                           accept["task_ref"]["owner"], accept["child_task_id"],
                           prev_called=prev_called, agent_label=accept.get("agent") or agent_id_raw,
                           project_id=accept["task_ref"]["owner"], agent_id=call_input.get("agent_id"))

    if mode == "workflow":
        return _delegate_workflow(agent_id_raw or params.get("workflow", ""),
                                   params, project_path)

    # same: async/sync 모두 같은 접수 경로(상주 러너). sync 는 접수한 같은 task 를 기다린다.
    from system_tools import execute_call_agent
    from thread_context import did_call_agent, get_current_task_id
    prev_called = did_call_agent()
    message = params.get("message", params.get("query", ""))
    prev = params.get("_prev_result", "")
    if prev and message and prev not in message:
        message = f"{message}\n\n--- 이전 단계 결과 ---\n{prev}"
    call_input = {**params, "agent_id": agent_id_raw, "message": message, "mode": mode}
    raw = execute_call_agent(call_input, project_path)
    if mode != "sync":
        return raw
    try:
        accept = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {"success": False, "error": f"접수 응답을 해석할 수 없습니다: {str(raw)[:300]}"}
    if not isinstance(accept, dict) or not accept.get("success"):
        return accept
    child_id = accept.get("child_task_id")
    if not child_id:
        return {"success": False, "error": "동기 위임의 자식 작업이 만들어지지 않았습니다 — 접수 응답에 child_task_id 가 없습니다.",
                "accepted": True, "task_ref": accept.get("task_ref")}
    from delegation_tasks import await_child
    project_id = Path(project_path).name
    return await_child(project_id, get_current_task_id(), project_id, child_id,
                       prev_called=prev_called, agent_label=accept.get("agent") or agent_id_raw,
                       project_id=project_id, agent_id=agent_id_raw)


def _delegate_workflow(agent_id: str, params: dict, project_path: str) -> Any:
    """다른 에이전트에게 IBL 파이프라인을 위임

    Args:
        agent_id: 대상 에이전트 이름 또는 ID
        params: {"steps": [...], "message": "..."} 파이프라인 정의
    """
    if not agent_id:
        return {"error": "agent_id가 필요합니다."}

    steps = params.get("steps", [])
    if not steps:
        return {"error": "params.steps가 필요합니다. 파이프라인 단계를 정의해주세요."}

    # 파이프라인 steps를 JSON으로 직렬화
    steps_json = json.dumps(steps, ensure_ascii=False)
    user_message = params.get("message", "")

    # 위임 메시지 구성
    delegation_msg = f"""다음 IBL 파이프라인을 실행해주세요.

```json
{steps_json}
```

execute_ibl(node="system", action="run_pipeline", params={{"steps": {steps_json}}}) 로 실행하세요."""

    if user_message:
        delegation_msg = f"{user_message}\n\n{delegation_msg}"

    # call_agent으로 위임
    from system_tools import execute_call_agent
    return execute_call_agent(
        {"agent_id": agent_id, "message": delegation_msg},
        project_path
    )


# _agent_ask_sync (임시 AIAgent 동기 실행기) 은퇴 — 2026-10-05. 동기 위임은 execute_call_agent 로
# 접수한 같은 task 를 delegation_tasks.await_child 가 기다린다(같은 어휘의 두 mode 가 다른
# 실행기·다른 모델 해소로 돌던 뿌리 제거).


def _agent_info(agent_id: str) -> Any:
    """에이전트 상세 정보 [others:info]{agent_id: "투자/투자컨설팅"} (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    for n in nodes:
        if n["type"] == "agent" and n["id"] == agent_id:
            return n
    return {"error": f"에이전트 '{agent_id}'을 찾을 수 없습니다."}


# === 능력 래퍼 — 지연 import 를 옛 자리 그대로 유지(행동 불변) ===

def _cap_send_notification(params: dict, project_path: str) -> Any:
    from system_tools import execute_send_notification
    return execute_send_notification(dict(params), project_path)


def _cap_ask_body(params: dict) -> Any:
    from body_ask import ask_peer
    return ask_peer(dict(params))


def _cap_list_project_agents(params: dict) -> Any:
    from system_ai_tools import _execute_list_project_agents
    return _execute_list_project_agents(params)


def _cap_call_project_agent(params: dict) -> Any:
    from system_ai_tools import _execute_call_project_agent
    return _execute_call_project_agent(dict(params))


def _cap_schedule(params: dict, agent_id: str = None, project_path: str = None) -> Any:
    from system_ai_plans import _execute_schedule
    return _execute_schedule(params, agent_id=agent_id, project_path=project_path)


def _cap_manage_events(params: dict, project_path: str = None) -> Any:
    from system_ai_tools import _execute_manage_events
    return _execute_manage_events(params, project_path=project_path)


def _cap_list_switches(params: dict) -> Any:
    from system_ai_tools import _execute_list_switches
    return _execute_list_switches(params)


def _cap_run_switch(params: dict) -> Any:
    from switch_manager import SwitchManager
    from switch_runner import SwitchRunner
    switch_id = params.get("switch_id", "")
    if not switch_id:
        return {"success": False, "error": "switch_id가 필요합니다."}
    sm = SwitchManager()
    switch = sm.get_switch(switch_id)
    if not switch:
        return {"success": False, "error": f"스위치 없음: {switch_id}"}
    runner = SwitchRunner(sm)
    result = runner.run_switch(switch_id)
    return {"success": True, "switch_id": switch_id, "result": result}


def _cap_world_pulse(action_name: str, params: dict) -> Any:
    from world_pulse import execute_world_pulse
    return execute_world_pulse(action_name, params)


def _cap_self_check() -> Any:
    from world_pulse_health import run_daily_health_check
    return run_daily_health_check()


def _cap_self_check_results(params: dict) -> Any:
    """자가점검 결과 items 투영 (V17-1, 2026-08-20) — [sense:self_check]{op:"results"}.

    원장은 자기 list 를 가진다: run(실행)만 있고 결과는 REST 전용이라 "실패 항목만 알림"이
    IBL 로 표현 불가하던 갭의 해소. 행 = title(node:action)·success·response_ms·error·
    quality·checked_at·source — [table:filter]{where: "success == false"} 로 실패만.

    ★source (V18-2, 2026-08-22 18회차): 건강 원장은 **둘**이다 — 자가점검(self_checks)과
    실사용(action_health). 만성 실패 경보는 후자의 source='usage' 만 세는데 이 어휘는
    전자만 투영해서, 경보를 받은 쪽이 근거로 되짚어 오면 0건을 만났다. self_check(기본)|
    usage|all 로 열되, 기본 조회가 0건이어도 실사용 실패가 있으면 message 가 가리킨다."""
    from world_pulse_health import get_recent_self_checks, get_recent_action_health
    SELF_CHECK_RESULTS_MAX = 500
    try:
        requested = int(params.get("limit") or 50)
    except (TypeError, ValueError):
        requested = 50
    limit = max(1, min(SELF_CHECK_RESULTS_MAX, requested))

    source = str(params.get("source") or "self_check").strip().lower()
    if source not in ("self_check", "usage", "all"):
        return {"success": False,
                "error": f"source 는 self_check|usage|all 중 하나입니다 (받은 값: '{source}'). "
                         "self_check=자가점검 원장 · usage=실사용 원장(만성 실패 경보의 근거) · all=둘 다."}

    def _rows_self_check():
        return [{
            "title": f"{r.get('node')}:{r.get('action')}",
            "node": r.get("node"), "action": r.get("action"),
            "success": bool(r.get("success")),
            "response_ms": r.get("response_ms"),
            "error": r.get("error_message"),
            "quality": r.get("data_quality"),
            "checked_at": r.get("timestamp"),
            "source": "self_check",
        } for r in get_recent_self_checks(limit)]

    def _rows_usage(scope):
        return [{
            "title": f"{r.get('node')}:{r.get('action')}",
            "node": r.get("node"), "action": r.get("action"),
            "success": bool(r.get("success")),
            "response_ms": r.get("response_ms"),
            "error": r.get("error"),
            "quality": None,
            "checked_at": r.get("timestamp"),
            "source": r.get("source") or "usage",
        } for r in get_recent_action_health(limit, scope)]

    if source == "self_check":
        items = _rows_self_check()
    elif source == "usage":
        items = _rows_usage("usage")
    else:
        items = sorted(_rows_self_check() + _rows_usage("all"),
                       key=lambda i: i.get("checked_at") or "", reverse=True)[:limit]

    fails = sum(1 for i in items if not i["success"])
    label = {"self_check": "자가점검", "usage": "실사용", "all": "자가점검+실사용"}[source]
    out = {"success": True, "items": items, "count": len(items), "source": source,
           "message": f"최근 {label} 기록 {len(items)}건 (실패 {fails}건)"}

    # 여기 없으면 어디 있는지 말한다 (V18-2): 만성 실패 경보는 실사용 원장만 세므로,
    # 기본 조회가 조용히 0건이면 경보를 받은 쪽은 근거가 없다고 오판한다.
    if source == "self_check":
        usage_fails = sum(1 for r in get_recent_action_health(limit, "usage")
                          if not r.get("success"))
        if usage_fails:
            out["usage_failures"] = usage_fails
            out["message"] += (f" · 실사용 원장에 최근 실패 {usage_fails}건 "
                               "— 만성 실패 경보의 근거는 이쪽이다: source: \"usage\"")
    if requested != limit:
        out["clamped"] = True
        out["requested"] = requested
    return out


def _cap_oneshot_ai_call(**kwargs):
    """criteria 판정자용 원샷 — ibl_quality 가 능력 테이블로만 도달한다(층 역전)."""
    from consciousness_agent import oneshot_ai_call
    return oneshot_ai_call(**kwargs)


def _cap_reset_consciousness() -> None:
    from consciousness_agent import reset_consciousness_agent
    reset_consciousness_agent()


def register_all() -> None:
    """시스템 라우터 능력 테이블 주입 — 조립 루트(boot_common)가 부팅 시 1회 호출."""
    from ibl_routing import register_system_capabilities
    register_system_capabilities({
        "delegate": _delegate_unified,
        "agent_info": _agent_info,
        "send_notification": _cap_send_notification,
        "ask_body": _cap_ask_body,
        "list_project_agents": _cap_list_project_agents,
        "call_project_agent": _cap_call_project_agent,
        "schedule": _cap_schedule,
        "manage_events": _cap_manage_events,
        "list_switches": _cap_list_switches,
        "run_switch": _cap_run_switch,
        "world_pulse": _cap_world_pulse,
        "self_check": _cap_self_check,
        "self_check_results": _cap_self_check_results,
        "reset_consciousness": _cap_reset_consciousness,
        # criteria 품질 계약의 판정자 (ibl_quality._call_judge, 기어 평가 축) —
        # ibl 층은 인지층을 모른다(의존 역전, 2026-08-27).
        "oneshot_ai_call": _cap_oneshot_ai_call,
    })
    # ③ 작업 접수증(task_receipts): 위임 작업의 관찰 어댑터 — 코드(몸의 명사) 길. 패키지 종류는 yaml task_kinds 로.
    import task_receipts
    from delegation_tasks import KIND as _DELEGATION_KIND, task_status as _delegation_task_status
    task_receipts.register(_DELEGATION_KIND, _delegation_task_status)
