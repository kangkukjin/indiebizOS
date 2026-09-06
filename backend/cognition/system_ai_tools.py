"""
system_ai_tools.py - 시스템 AI 도구 및 실행 모듈
IndieBiz OS Core

- 최상위 도구 목록 구성 (get_all_system_ai_tools)
- IBL 라우팅용 실행 함수: 프로젝트/에이전트 위임, 캘린더/스케줄, 스위치
"""

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from tool_loader import load_tool_schema
from runtime_utils import get_base_path as _get_base_path


def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI 도구: execute_ibl + 범용 언어 + 인지 도구 + read_guide

    프로젝트 에이전트와 동일한 도구 구조.
    차이는 IBL에서 접근 가능한 노드 범위뿐 (시스템 AI: 전체 노드).
    """
    import json as _json

    tools = []
    ibl_schema = load_tool_schema("execute_ibl")
    if ibl_schema:
        tools.append(ibl_schema)

    # 범용 도구 (프로젝트 에이전트와 동일)
    # 코드 실행 탈출구는 *몸의 네이티브 런타임*에 묶인다(마이크로 명령어):
    # - PC/맥: shell 이 있어 run_command 로 write→run (Python/Node 실행기는 제거됨).
    # - 폰: shell·standalone python 바이너리 부재. 대신 Chaquopy 인-프로세스 Python 이 유일한 탈출구.
    #   → shell 이 로컬에 없는 몸(폰)에만 execute_python 을 노출(capability-gate, profile 아님 — 무포크).
    pkg_base = Path(__file__).parent.parent.parent / "data" / "packages" / "installed" / "tools"
    lang_tools = [
        ("system_essentials", "run_command"),
        # 에이전트 인지 도구 — IBL 경유 불가 (파라미터 구조 불일치)
        ("system_essentials", "todo_write"),
        ("system_essentials", "ask_user_question"),
        ("system_essentials", "enter_plan_mode"),
        ("system_essentials", "exit_plan_mode"),
    ]
    try:
        from runtime_utils import detect_local_micros
        if detect_local_micros().get("escape") == "python":
            # 이 몸의 만능 탈출구가 python(=폰, 셸이 만능이 아님) → 네이티브 Python(인-프로세스) 노출.
            lang_tools.append(("python-exec", "execute_python"))
    except Exception as e:
        print(f"[시스템AI] 마이크로 감지 실패(execute_python 미노출): {e}")
    for pkg_id, tool_name in lang_tools:
        tool_json = pkg_base / pkg_id / "tool.json"
        if tool_json.exists():
            try:
                with open(tool_json, 'r', encoding='utf-8') as f:
                    pkg_data = _json.load(f)
                for tool_def in pkg_data.get("tools", []):
                    if tool_def.get("name") == tool_name:
                        tools.append(tool_def)
                        break
            except Exception as e:
                print(f"[시스템AI] {pkg_id}/tool.json 로드 실패: {e}")

    # 턴 안 재규정 — 자기 관리 도구 부류(ask_user_question 과 같은 자리, IBL 어휘 아님)
    try:
        from reframe import TOOL_SCHEMA as _REFRAME_TOOL
        tools.append(dict(_REFRAME_TOOL))
    except Exception as e:
        print(f"[시스템AI] reframe 도구 로드 실패(생략): {e}")

    # 가이드 검색 도구
    tools.append({
        "name": "read_guide",
        "description": "가이드 파일을 여는 도구. 가이드의 목차는 <execution_map> 각 가지의 guide: 줄이다 — 파일명(예: query='investment.md')을 그대로 주면 그 파일을 정확히 연다. 지도에 마땅한 가지가 없을 때만 키워드(예: query='동영상')로 검색한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드 (예: 캘린더, 스케줄, 영상)"},
                "read": {"type": "boolean", "description": "true(기본): 가이드 내용까지 반환, false: 목록만"}
            },
            "required": ["query"]
        }
    })

    return tools


def _execute_list_project_agents(tool_input: dict) -> str:
    """list_project_agents 도구 실행 - 모든 프로젝트/에이전트 목록 조회"""
    import yaml

    try:
        # projects 폴더 경로 (api.py의 BASE_PATH/projects와 동일)
        projects_path = _get_base_path() / "projects"
        result = []

        # 모든 프로젝트 폴더 순회
        for project_dir in projects_path.iterdir():
            if not project_dir.is_dir():
                continue
            if project_dir.name in ['trash', '.DS_Store']:
                continue

            agents_yaml = project_dir / "agents.yaml"
            if not agents_yaml.exists():
                continue

            try:
                data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
                agents = data.get("agents", [])

                agent_list = []
                for agent in agents:
                    if not agent.get("active", True):
                        continue  # 비활성화된 에이전트 제외
                    agent_list.append({
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "role_description": agent.get("role_description", "")
                    })

                if agent_list:  # 에이전트가 있는 프로젝트만 포함
                    result.append({
                        "project_id": project_dir.name,
                        "project_name": project_dir.name,
                        "agents": agent_list
                    })
            except Exception as e:
                print(f"[list_project_agents] {project_dir.name} 파싱 오류: {e}")
                continue

        # F8-agents (2026-08-16 6회차): 중첩 projects[{agents:[...]}] 만 있으면 take/filter 가
        # 못 문다 — 평평한 에이전트 행을 items 로 병기(원형 projects 보존).
        flat = [{"project": p["project_id"], "id": a.get("id"),
                 "name": a.get("name"), "role_description": a.get("role_description", "")}
                for p in result for a in p["agents"]]
        return json.dumps({
            "success": True,
            "projects": result,
            "items": flat,
            "count": len(flat),
            "total_projects": len(result),
            "total_agents": sum(len(p["agents"]) for p in result)
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


def _execute_call_project_agent(tool_input: dict) -> str:
    """프로젝트 에이전트 호출 실행 (자동 시작 포함)"""
    import uuid
    import yaml
    from agent_runner import AgentRunner
    from thread_context import get_current_task_id, set_called_agent
    from system_ai_memory import get_task, update_task_delegation

    project_id = tool_input.get("project_id", "")
    agent_id = tool_input.get("agent_id", "")
    message = tool_input.get("message", "")

    if not project_id or not agent_id or not message:
        return "오류: project_id, agent_id, message가 모두 필요합니다."

    # 대상 에이전트 찾기 (실행 중인지 확인)
    # agent_id는 id 또는 name일 수 있음 → 먼저 id로, 없으면 name으로 검색
    registry_key = f"{project_id}:{agent_id}"
    target = AgentRunner.agent_registry.get(registry_key)
    if not target:
        # name으로 검색 (registry는 project_id:agent_id 형식이므로 순회)
        for rkey, runner in AgentRunner.agent_registry.items():
            if rkey.startswith(f"{project_id}:") and runner.config.get("name") == agent_id:
                target = runner
                agent_id = runner.config.get("id", agent_id)
                registry_key = rkey
                break

    # 에이전트가 실행 중이 아니면 프로젝트 전체 에이전트 시작
    if not target:
        print(f"[시스템 AI] 프로젝트 활성화: {project_id}")
        try:
            # 프로젝트 경로 직접 계산
            project_path = _get_base_path() / "projects" / project_id
            agents_yaml = project_path / "agents.yaml"

            if not agents_yaml.exists():
                return f"오류: 프로젝트 '{project_id}'를 찾을 수 없습니다."

            data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
            agents = data.get("agents", [])

            # 대상 에이전트 확인 (id 또는 name으로 검색)
            target_config = None
            for agent in agents:
                if agent.get("id") == agent_id or agent.get("name") == agent_id:
                    target_config = agent
                    # agent_id를 실제 id로 통일 (registry_key 매칭용)
                    agent_id = agent.get("id", agent_id)
                    break

            if not target_config:
                return f"오류: 에이전트 '{agent_id}'를 찾을 수 없습니다."

            if not target_config.get("active", True):
                return f"오류: 에이전트 '{agent_id}'가 비활성화되어 있습니다."

            # 공통 설정 로드
            common_config = data.get("common", {})

            # 프로젝트의 모든 활성 에이전트 시작
            started_agents = []
            for agent_config in agents:
                if not agent_config.get("active", True):
                    continue

                aid = agent_config.get("id")
                rkey = f"{project_id}:{aid}"

                # 이미 실행 중이면 스킵
                if AgentRunner.agent_registry.get(rkey):
                    continue

                # 프로젝트 정보 추가 (api_agents.py 방식)
                agent_config["_project_path"] = str(project_path)
                agent_config["_project_id"] = project_id

                runner = AgentRunner(agent_config, common_config, delegated_from_system_ai=True)
                runner.start()
                started_agents.append(agent_config.get("name", aid))

            # 에이전트들이 준비될 때까지 잠시 대기
            import time
            time.sleep(0.5)

            if started_agents:
                print(f"[시스템 AI] 프로젝트 '{project_id}' 에이전트 시작 완료: {', '.join(started_agents)}")

            # 대상 에이전트 다시 조회 (agent_id는 실제 id로 통일됨)
            registry_key = f"{project_id}:{agent_id}"
            target = AgentRunner.agent_registry.get(registry_key)
            if not target:
                return f"오류: 에이전트 '{agent_id}' 시작 실패"

        except Exception as e:
            return f"오류: 프로젝트 활성화 실패 - {str(e)}"

    # 현재 태스크 ID (시스템 AI의 태스크)
    parent_task_id = get_current_task_id()
    if not parent_task_id:
        return "오류: 현재 태스크 ID가 없습니다. (내부 오류)"

    # 자식 태스크 생성
    child_task_id = f"task_{uuid.uuid4().hex[:8]}"

    # 위임 컨텍스트 업데이트
    parent_task = get_task(parent_task_id)
    if parent_task:
        delegation_context_str = parent_task.get('delegation_context')
        pending = parent_task.get('pending_delegations', 0)

        if delegation_context_str:
            delegation_context = json.loads(delegation_context_str)

            # 이전 사이클 완료 감지: delegations 있고 pending==0 → completed로 병합
            prev_delegations = delegation_context.get('delegations', [])
            if len(prev_delegations) > 0 and pending == 0:
                completed = delegation_context.get('completed', [])
                responses = delegation_context.get('responses', [])

                # 이전 사이클 결과를 completed에 병합
                response_map = {}
                for resp in responses:
                    child_id = resp.get('child_task_id', '')
                    response_map[child_id] = resp

                for deleg in prev_delegations:
                    child_id = deleg.get('child_task_id', '')
                    resp = response_map.get(child_id, {})
                    completed.append({
                        'to': deleg.get('delegated_to', ''),
                        'message': deleg.get('delegation_message', ''),
                        'result': resp.get('response', '(응답 없음)'),
                        'completed_at': resp.get('completed_at', deleg.get('delegation_time', ''))
                    })

                print(f"   [시스템 AI 위임 컨텍스트] 이전 사이클 {len(prev_delegations)}개 → completed 병합 (총 {len(completed)}개)")
                delegation_context = {
                    'original_request': parent_task.get('original_request', ''),
                    'requester': parent_task.get('requester', 'user@gui'),
                    'completed': completed,
                    'delegations': [],
                    'responses': []
                }
        else:
            delegation_context = {
                'original_request': parent_task.get('original_request', ''),
                'requester': parent_task.get('requester', 'user@gui'),
                'completed': [],
                'delegations': [],
                'responses': []
            }

        delegation_context['delegations'].append({
            'child_task_id': child_task_id,
            'delegated_to': target.config.get('name', agent_id),
            'delegation_message': message,
            'delegation_time': datetime.now().isoformat()
        })

        update_task_delegation(
            parent_task_id,
            json.dumps(delegation_context, ensure_ascii=False),
            increment_pending=True
        )

    # 프로젝트 에이전트의 DB에 자식 태스크 생성
    target.db.create_task(
        task_id=child_task_id,
        requester="system_ai",
        requester_channel="system_ai",
        original_request=message,
        delegated_to=target.config.get('name', agent_id),
        parent_task_id=parent_task_id
    )

    # 프로젝트 에이전트에게 메시지 전송
    msg_dict = {
        'content': f"[task:{child_task_id}] {message}",
        'from_agent': '시스템 AI',
        'task_id': child_task_id,
        'timestamp': datetime.now().isoformat()
    }

    with AgentRunner._lock:
        if registry_key not in AgentRunner.internal_messages:
            AgentRunner.internal_messages[registry_key] = []
        AgentRunner.internal_messages[registry_key].append(msg_dict)

    # call_agent 호출 플래그 설정
    set_called_agent(True)

    agent_name = target.config.get('name', agent_id)
    print(f"[시스템 AI] 위임: 시스템 AI → {agent_name} (task: {child_task_id})")

    return f"'{agent_name}'에게 작업을 위임했습니다. 결과를 기다리세요."


def _looks_like_ibl(text) -> bool:
    """`do` 값이 IBL 문장인가(액션 이름이 아니라)."""
    t = str(text or "").strip()
    return t.startswith("[") or "]{" in t


def _split_date_time(event_date, event_time):
    """`date:"2026-09-03 14:00"`·`"2026-09-03T14:00"` 같은 합쳐 쓴 값을 date/time 으로 가른다 (F54-3).

    옛 판은 원문을 그대로 저장해 실행 판정(`strptime("%Y-%m-%d")`)이 못 읽고 **침묵 미발화**했다.
    `_execute_schedule` 이 같은 입력을 가르던 규칙을 한 벌로.
    """
    d = str(event_date).strip() if event_date else None
    t = str(event_time).strip() if event_time else None
    if d and (" " in d or "T" in d):
        try:
            from datetime import datetime as _dt
            parsed = _dt.fromisoformat(d.replace(" ", "T"))
            d = parsed.strftime("%Y-%m-%d")
            if not t:
                t = parsed.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
    if t and len(t) == 8 and t.count(":") == 2:
        t = t[:5]
    return d, t


def _execute_manage_events(tool_input: dict, project_path: str = None) -> str:
    """manage_events 통합 도구 실행 (캘린더 + 스케줄러)

    정규 키=op (2026-07-21 op 어휘 단일화 합류, trigger 선례 — 입구 재매핑 후 기존 분기 그대로).
    action= 은 별칭: IBL 경로는 aliases 선언으로 op 정규화되지만, 레거시 도구 경로
    (별칭 정규화 미경유 직접 호출)도 있어 여기서도 폴백으로 받는다.
    project_path: 등록 프로젝트(발화 문맥, B54-1) — 실행 이벤트의 owner_project_id 가 된다.
    """
    from calendar_manager import get_calendar_manager

    action = tool_input.get("op") or tool_input.get("action", "")
    cm = get_calendar_manager()

    try:
        if action == "list":
            year = tool_input.get("year")
            month = tool_input.get("month")
            events = cm.list_events(year=year, month=month)
            if not events:
                return json.dumps({"success": True, "items": [], "message": "등록된 이벤트가 없습니다."}, ensure_ascii=False)
            # 단일 통화 items = native 이벤트(풍부 dict: id/date/time/title/repeat/type/description)
            # calendar 뷰가 id/date/title 직독, chart/document 소비자는 items에서 칸 탐색.
            return json.dumps({"success": True, "items": events, "count": len(events)}, ensure_ascii=False)

        elif action in ("add", "create"):
            title = tool_input.get("title")
            if not title:
                return json.dumps({"success": False, "error": "title은 필수입니다."}, ensure_ascii=False)

            event_date, event_time = _split_date_time(tool_input.get("date"), tool_input.get("time"))
            event_action = tool_input.get("event_action")
            action_params = tool_input.get("action_params")
            repeat = tool_input.get("repeat", "none")
            owner_project_id = None
            # ★B54-5 (54회차): 카탈로그는 "do 에 IBL 문장이 있으면 실행 이벤트"라 약속했는데 옛 판은
            #   문장을 액션 **이름**으로 저장해 발화 때 "알 수 없는 작업" 로그 한 줄만 남겼다.
            #   IBL 이면 run_pipeline + action_params.pipeline 로 정규화하고 등록 프로젝트를 싣는다.
            if event_action and _looks_like_ibl(event_action):
                action_params = dict(action_params or {})
                action_params["pipeline"] = str(event_action)
                event_action = "run_pipeline"
                from trigger_engine import project_id_of_path as _pid_of
                owner_project_id = _pid_of(project_path) or None
            elif event_action and event_action not in cm.actions:
                return json.dumps({"success": False,
                                   "error": (f"알 수 없는 실행 액션 '{str(event_action)[:60]}' — 등록된 액션: {sorted(cm.actions)}. "
                                             "IBL 문장을 실행하려면 do 에 문장을 주세요.")},
                                  ensure_ascii=False)

            # start_time 호환: "2026-03-09T17:44:00" → date + time 자동 분리
            start_time = tool_input.get("start_time")
            if start_time and (not event_date or not event_time):
                try:
                    from datetime import datetime as _dt
                    parsed = _dt.fromisoformat(start_time)
                    if not event_date:
                        event_date = parsed.strftime("%Y-%m-%d")
                    if not event_time:
                        event_time = parsed.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass

            # 실행 이벤트 (스케줄)인 경우 date 없이도 허용 (daily, interval 등)
            if not event_date and not event_action:
                return json.dumps({"success": False, "error": "date는 필수입니다. (YYYY-MM-DD)"}, ensure_ascii=False)

            event = cm.add_event(
                title=title,
                event_date=event_date,
                event_type=tool_input.get("type", "schedule" if event_action else "other"),
                repeat=repeat,
                description=tool_input.get("description", ""),
                event_time=event_time,
                action=event_action,
                action_params=action_params,
                enabled=tool_input.get("enabled", True),
                weekdays=tool_input.get("weekdays"),
                month=tool_input.get("month"),
                day=tool_input.get("day"),
                interval_hours=tool_input.get("interval_hours"),
                owner_project_id=owner_project_id,
            )
            return json.dumps({"success": True, "event": event, "message": f"이벤트 '{title}' 추가됨"}, ensure_ascii=False)

        elif action == "update":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)

            updates = {}
            for key in ["title", "date", "time", "type", "repeat", "description",
                         "enabled", "weekdays", "month", "day", "interval_hours", "action_params"]:
                if key in tool_input:
                    updates[key] = tool_input[key]
            if "date" in updates or "time" in updates:
                _d, _t = _split_date_time(updates.get("date"), updates.get("time"))
                if _d:
                    updates["date"] = _d
                if _t:
                    updates["time"] = _t
            if "event_action" in tool_input:
                _ea = tool_input["event_action"]
                if _ea and _looks_like_ibl(_ea):
                    _ap = dict(updates.get("action_params") or {})
                    _ap["pipeline"] = str(_ea)
                    updates["action_params"] = _ap
                    updates["action"] = "run_pipeline"
                elif _ea and _ea not in cm.actions:
                    return json.dumps({"success": False,
                                       "error": f"알 수 없는 실행 액션 '{str(_ea)[:60]}' — 등록된 액션: {sorted(cm.actions)}."},
                                      ensure_ascii=False)
                else:
                    updates["action"] = _ea

            if cm.update_event(event_id, **updates):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 수정됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "delete":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            if cm.delete_event(event_id):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 삭제됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "toggle":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            result = cm.toggle_task(event_id)
            if result is not None:
                status = "활성화" if result else "비활성화"
                return json.dumps({"success": True, "enabled": result, "message": f"이벤트 {status}됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "run_now":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            _why = cm.explain_run_now(event_id)
            if _why:
                return json.dumps({"success": False, "error": _why}, ensure_ascii=False)
            if cm.run_task_now(event_id):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 즉시 실행 시작"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다. (실행 가능한 이벤트만 run_now 가능)"}, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"알 수 없는 op: {action}. list, create, update, delete, toggle, run_now 중 선택하세요."}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _execute_list_switches(tool_input: dict) -> str:
    """list_switches 도구 실행"""
    try:
        from switch_manager import SwitchManager
        sm = SwitchManager()
        switches = sm.list_switches()

        result = []
        for sw in switches:
            if sw.get("in_trash"):
                continue
            result.append({
                "id": sw.get("id"),
                "name": sw.get("name"),
                "icon": sw.get("icon", ""),
                "command": sw.get("command", "")[:100],
                "project": sw.get("config", {}).get("projectId", ""),
                "agent": sw.get("config", {}).get("agent_name", ""),
                "run_count": sw.get("run_count", 0),
                "last_run": sw.get("last_run")
            })

        # items 병행 방출 — self:agents(d74461b)와 같은 이유·같은 방식. `switches` 만 내면
        # `[self:switch]{op:"list"} >> [table:take]` 가 "items 통화를 찾지 못했습니다"로 끊긴다.
        # 기존 키는 그대로 둔다(소비처 무손상).
        return json.dumps({"success": True, "switches": result, "items": result,
                           "count": len(result)}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
