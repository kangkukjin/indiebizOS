"""
system_ai_tools.py - 시스템 AI 도구 정의 및 실행 모듈
IndieBiz OS Core

시스템 AI가 사용하는 도구(tool)의 스키마 정의와 실행 함수를 포함합니다:
- 프로젝트/에이전트 목록 조회 및 위임
- 캘린더/스케줄 이벤트 관리
- 스위치 목록 조회
- IBL/언어 도구/가이드 도구 통합 로딩
"""

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from tool_loader import load_tool_schema
from runtime_utils import get_base_path as _get_base_path


def _get_list_project_agents_tool() -> Dict:
    """list_project_agents 도구 정의"""
    return {
        "name": "list_project_agents",
        "description": """시스템 내 모든 프로젝트와 에이전트 목록을 조회합니다.

## 반환 정보
- project_id: 프로젝트 ID (폴더명)
- project_name: 프로젝트 이름
- agents: 에이전트 목록
  - id: 에이전트 ID
  - name: 에이전트 이름
  - role_description: 역할 설명 (전문 분야)

## 사용 시점
- call_project_agent 전 적합한 대상 확인
- 어떤 프로젝트/에이전트가 있는지 파악
- role_description을 보고 작업에 적합한 에이전트 선택

## 참고
- 에이전트가 실행 중이 아니어도 call_project_agent 시 자동 시작됨""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }


def _get_call_project_agent_tool() -> Dict:
    """call_project_agent 도구 정의"""
    return {
        "name": "call_project_agent",
        "description": """프로젝트의 에이전트에게 작업을 위임합니다.

## 사용 전 확인
1. list_project_agents로 사용 가능한 에이전트 확인
2. role_description을 보고 적합한 에이전트 선택

## 사용 시나리오
- 특정 프로젝트의 전문 에이전트에게 작업을 맡기고 싶을 때
- 프로젝트별 도구나 컨텍스트가 필요한 작업일 때

## 주의사항
- 위임 후 결과를 기다려야 합니다
- 에이전트가 작업을 완료하면 자동으로 결과를 보고받습니다
- 에이전트가 실행 중이 아니면 자동으로 시작됩니다""",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "프로젝트 ID"
                },
                "agent_id": {
                    "type": "string",
                    "description": "에이전트 ID (agents.yaml의 id 필드)"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 작업 내용"
                }
            },
            "required": ["project_id", "agent_id", "message"]
        }
    }


def _get_manage_events_tool() -> Dict:
    """manage_events 통합 도구 정의 (캘린더 + 스케줄러)"""
    return {
        "name": "manage_events",
        "description": "캘린더 이벤트와 스케줄 작업을 통합 관리합니다 (기념일, 약속, 생일, 알림, 스케줄 등의 추가/수정/삭제/조회/토글).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "수행할 작업: list, add, update, delete, toggle, run_now"
                },
                "event_id": {
                    "type": "string",
                    "description": "이벤트 ID (update, delete, toggle, run_now 시 필수)"
                },
                "title": {
                    "type": "string",
                    "description": "이벤트 제목/이름 (add 시 필수)"
                },
                "date": {
                    "type": "string",
                    "description": "날짜 (YYYY-MM-DD 형식)"
                },
                "time": {
                    "type": "string",
                    "description": "시간 (HH:MM 형식)"
                },
                "type": {
                    "type": "string",
                    "description": "이벤트 타입: anniversary, birthday, appointment, reminder, schedule, other"
                },
                "repeat": {
                    "type": "string",
                    "description": "반복 유형: none, daily, weekly, monthly, yearly, interval"
                },
                "description": {
                    "type": "string",
                    "description": "이벤트 설명"
                },
                "event_action": {
                    "type": "string",
                    "description": "실행할 액션 (스케줄 작업일 때): run_pipeline, run_switch, send_notification, test. run_pipeline은 IBL 코드를 예약 실행할 때 사용. null이면 순수 캘린더 이벤트"
                },
                "action_params": {
                    "type": "object",
                    "description": "액션 파라미터. run_pipeline일 때: {pipeline: \"[limbs:play]{query: '검색어'}\"}, run_switch일 때: {switch_id: '...'}, send_notification일 때: {message: '...', title: '...'}"
                },
                "weekdays": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "요일 목록 (weekly일 때, 0=월 ~ 6=일)"
                },
                "month": {
                    "type": "integer",
                    "description": "월 (yearly일 때 1-12, list 시 조회 월)"
                },
                "day": {
                    "type": "integer",
                    "description": "일 (yearly일 때 1-31)"
                },
                "interval_hours": {
                    "type": "integer",
                    "description": "반복 간격 시간 (interval일 때)"
                },
                "year": {
                    "type": "integer",
                    "description": "조회 연도 (list 시 선택)"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "활성화 여부 (update 시)"
                }
            },
            "required": ["action"]
        }
    }


def _get_list_switches_tool() -> Dict:
    """list_switches 도구 정의"""
    return {
        "name": "list_switches",
        "description": """등록된 스위치 목록을 조회합니다. 스케줄에 스위치를 연결할 때 switch_id를 확인하는 용도입니다.

## 반환 정보
- id: 스위치 ID (스케줄 등록 시 사용)
- name: 스위치 이름
- command: 실행 명령어
- project: 연결된 프로젝트
- run_count: 총 실행 횟수
- last_run: 마지막 실행 시간""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }


def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI 도구: execute_ibl + 범용 언어 도구 + read_guide

    프로젝트 에이전트와 동일한 도구 구조.
    차이는 IBL에서 접근 가능한 노드 범위뿐 (시스템 AI: 전체 노드).
    """
    import json as _json

    tools = []
    ibl_schema = load_tool_schema("execute_ibl")
    if ibl_schema:
        tools.append(ibl_schema)

    # 범용 언어 도구 (프로젝트 에이전트와 동일)
    pkg_base = Path(__file__).parent.parent / "data" / "packages" / "installed" / "tools"
    lang_tools = [
        ("python-exec", "execute_python"),
        ("nodejs", "execute_node"),
        ("system_essentials", "run_command"),
    ]
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

    # 가이드 검색 도구
    tools.append({
        "name": "read_guide",
        "description": "가이드 파일을 읽는 도구. 검색, 투자 분석, 동영상 제작, 웹사이트 빌드 등 복잡한 작업의 단계별 가이드가 저장되어 있다. 작업 전에 이 도구로 가이드를 읽어라. 예: query='검색'이면 검색 가이드를 읽음.",
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

        return json.dumps({
            "success": True,
            "projects": result,
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


def _execute_manage_events(tool_input: dict) -> str:
    """manage_events 통합 도구 실행 (캘린더 + 스케줄러)"""
    from calendar_manager import get_calendar_manager

    action = tool_input.get("action", "")
    cm = get_calendar_manager()

    try:
        if action == "list":
            year = tool_input.get("year")
            month = tool_input.get("month")
            events = cm.list_events(year=year, month=month)
            if not events:
                return json.dumps({"success": True, "events": [], "message": "등록된 이벤트가 없습니다."}, ensure_ascii=False)
            return json.dumps({"success": True, "events": events, "count": len(events)}, ensure_ascii=False)

        elif action == "add":
            title = tool_input.get("title")
            if not title:
                return json.dumps({"success": False, "error": "title은 필수입니다."}, ensure_ascii=False)

            event_date = tool_input.get("date")
            event_time = tool_input.get("time")
            event_action = tool_input.get("event_action")
            repeat = tool_input.get("repeat", "none")

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
                action_params=tool_input.get("action_params"),
                enabled=tool_input.get("enabled", True),
                weekdays=tool_input.get("weekdays"),
                month=tool_input.get("month"),
                day=tool_input.get("day"),
                interval_hours=tool_input.get("interval_hours"),
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
            if "event_action" in tool_input:
                updates["action"] = tool_input["event_action"]

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
            if cm.run_task_now(event_id):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 즉시 실행 시작"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다. (실행 가능한 이벤트만 run_now 가능)"}, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"알 수 없는 action: {action}. list, add, update, delete, toggle, run_now 중 선택하세요."}, ensure_ascii=False)

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

        return json.dumps({"success": True, "switches": result, "count": len(result)}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
