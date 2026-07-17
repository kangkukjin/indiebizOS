"""
system_tools.py - 시스템 도구 정의 및 실행
IndieBiz OS Core

에이전트 간 통신, 알림, 프로젝트 정보 등 시스템 수준 도구
"""

import json
import re
import time
import uuid
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from tool_loader import load_tool_handler, get_all_tool_names
from api_engine import is_registry_tool, execute_tool as registry_execute_tool

# 액션 서킷 브레이커·IBL 로그 상태는 system_tools_ibl.py 로 이동 (2026-07-18 모듈화) —
# 가변 전역(_action_fail_counter 가 reset 시 rebind)이라 hot-path(_execute_ibl_unified)와
# 같은 모듈에 살아야 한다. 재수출로 기존 경로 불변.
from system_tools_ibl import (  # noqa: E402,F401
    reset_action_breaker,
    get_action_breaker_state,
)

# ============ Async 핸들러 지원: 영구 이벤트 루프 ============
# Playwright 등 async 도구 패키지가 동일한 이벤트 루프에서 실행되어야
# 브라우저 세션이 호출 간에 유지됨.

_async_loop: asyncio.AbstractEventLoop = None
_async_thread: threading.Thread = None
_async_lock = threading.Lock()


def _get_async_loop() -> asyncio.AbstractEventLoop:
    """전용 async 이벤트 루프를 반환 (없으면 생성)"""
    global _async_loop, _async_thread
    with _async_lock:
        if _async_loop is None or _async_loop.is_closed():
            _async_loop = asyncio.new_event_loop()
            _async_thread = threading.Thread(
                target=_async_loop.run_forever,
                daemon=True,
                name="tool-async-loop"
            )
            _async_thread.start()
    return _async_loop


def _run_coroutine(coro, timeout=120):
    """coroutine을 영구 이벤트 루프에서 실행하고 결과를 동기적으로 반환"""
    loop = _get_async_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)



# ============ IBL 형식 로깅 ============

# ibl_* 도구 → 노드 매핑 (현재 7개 노드: system, team, interface, messenger, source, stream, forge)
_IBL_TOOL_PREFIX_MAP = {
    # 현재 노드
    "ibl_system": "system", "ibl_team": "team", "ibl_interface": "interface",
    "ibl_messenger": "messenger", "ibl_source": "source",
    "ibl_stream": "stream", "ibl_forge": "engines",
    # 하위 호환: 구 도구명 → 현재 노드
    "ibl_android": "interface", "ibl_browser": "interface", "ibl_desktop": "interface",
    "ibl_youtube": "stream", "ibl_radio": "stream",
    "ibl_informant": "source", "ibl_librarian": "source",
    "ibl_photo": "source", "ibl_blog": "source",
    "ibl_memory": "source", "ibl_health": "source",
    "ibl_finance": "source", "ibl_culture": "source", "ibl_study": "source",
    "ibl_legal": "source", "ibl_statistics": "source",
    "ibl_commerce": "source", "ibl_location": "source",
    "ibl_web": "source", "ibl_info": "source",
    "ibl_creator": "engines", "ibl_webdev": "engines", "ibl_design": "engines",
    "ibl_orchestrator": "system", "ibl_workflow": "system",
    "ibl_automation": "system", "ibl_output": "system",
    "ibl_user": "system", "ibl_filesystem": "system", "ibl_fs": "system",
    # 특수
    "execute_ibl": "ibl",
}

# 시스템 도구 → IBL 표기 매핑
_SYSTEM_IBL_MAP = {
    "call_agent": ("team", "delegate"),
    "list_agents": ("team", "list_projects"),
    "send_notification": ("system", "send_notify"),
    "get_project_info": ("team", "info"),
    "get_my_tools": ("system", "tools"),
    "request_user_approval": ("system", "approval"),
}

# 개별 도구 → (node, action) 역매핑 캐시
_reverse_node_map: dict = None


def _build_reverse_node_map() -> dict:
    """ibl_nodes.yaml에서 도구 이름 → (node, action) 역매핑 구축"""
    import yaml
    from runtime_utils import get_base_path

    result = {}
    path = get_base_path() / "data" / "ibl_nodes.yaml"
    if not path.exists():
        return result

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node_name, node_config in data.get("nodes", {}).items():
            for action_name, action_config in node_config.get("actions", {}).items():
                mapped_tool = action_config.get("tool")
                if mapped_tool:
                    result[mapped_tool] = (node_name, action_name)
    except Exception:
        pass

    return result


def _tool_to_ibl_notation(tool_name: str, tool_input: dict) -> tuple:
    """도구 이름을 IBL node:action 표기로 변환"""
    # execute_ibl: code 파라미터에서 노드/액션 추출
    if tool_name == "execute_ibl":
        import re
        code = tool_input.get("code") or tool_input.get("pipeline", "")
        if code:
            m = re.search(r'\[(\w+):(\w+)\]', code)
            if m:
                return m.group(1), m.group(2)
            return "ibl", "?"
        # 레거시 호환: node+action 파라미터
        node = tool_input.get("node", "")
        action = tool_input.get("action", "?")
        if node:
            return node, action
        return "ibl", action

    # ibl_* 도구
    if tool_name in _IBL_TOOL_PREFIX_MAP:
        node = _IBL_TOOL_PREFIX_MAP[tool_name]
        action = tool_input.get("action", "?")
        return node, action

    # 시스템 도구
    if tool_name in _SYSTEM_IBL_MAP:
        return _SYSTEM_IBL_MAP[tool_name]

    # 개별 도구 → ibl_nodes.yaml 역매핑
    global _reverse_node_map
    if _reverse_node_map is None:
        _reverse_node_map = _build_reverse_node_map()

    if tool_name in _reverse_node_map:
        return _reverse_node_map[tool_name]

    return ("tool", tool_name)


def _extract_hint(tool_input: dict) -> str:
    """tool_input에서 대표 파라미터 값 추출 (로그용)"""
    # params 내부에서 주요 값 찾기
    params = tool_input.get("params", {})
    search_in = {**params, **tool_input}

    for key in ("query", "path", "url", "pattern", "command", "pipeline", "code", "agent_id", "message"):
        if key in search_in:
            val = str(search_in[key])
            return val[:60] if len(val) > 60 else val

    return ""


def _log_ibl(tool_name: str, tool_input: dict, duration_ms: float,
             agent_id: str = None, success: bool = True):
    """도구 실행을 IBL 형식으로 콘솔 로그

    개별 IBL 액션 기록(thread_context, X-Ray 푸시)은
    ibl_engine.py의 execute_ibl() 내부에서 직접 수행.
    여기서는 콘솔 출력만 담당.
    """
    node, action = _tool_to_ibl_notation(tool_name, tool_input)
    hint = _extract_hint(tool_input)

    status = "OK" if success else "ERR"
    agent_tag = f"[{agent_id}] " if agent_id else ""
    timestamp = datetime.now().strftime("%H:%M:%S")

    hint_str = f" ({hint})" if hint else ""
    print(f"[{timestamp}] {agent_tag}[{node}:{action}]{hint_str} -> {status} ({duration_ms:.0f}ms)")

    # execute_ibl이 아닌 도구(request_user_approval 등)는 여기서 기록
    if tool_name != "execute_ibl":
        try:
            from thread_context import append_tool_call
            append_tool_call(tool_name, tool_input, success,
                             node=node, action=action, duration_ms=round(duration_ms))
        except Exception:
            pass
        try:
            from api_xray import push_xray_event
            push_xray_event("tool", {
                "node": node, "action": action, "hint": hint or "",
                "success": success, "ms": round(duration_ms),
                "agent": agent_id or "",
            })
        except Exception:
            pass


# ============ 시스템 도구 정의 ============

SYSTEM_TOOLS = [
    {
        "name": "request_user_approval",
        "description": """사용자 승인을 요청합니다.

## 사용 시점
- 파일 삭제, 시스템 설정 변경 등 위험한 작업 전
- 외부 서비스에 데이터 전송 전
- 비용이 발생할 수 있는 작업 전

## 중요 규칙
- 하나의 작업 요청에 대해 한 번만 호출
- 승인 후 모든 단계를 완료하고 결과 보고
- 같은 작업에 두 번 이상 호출 금지

## 사용하지 않을 때
- 일반적인 파일 읽기/쓰기
- 정보 조회
- 안전한 도구 실행""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "수행하려는 작업 유형 (예: 파일 삭제, 패키지 설치, 시스템 설정 변경)"
                },
                "description": {
                    "type": "string",
                    "description": "수행하려는 작업에 대한 상세 설명"
                },
                "affected_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "영향받는 파일, 패키지 등의 목록"
                }
            },
            "required": ["action_type", "description"]
        }
    },
    {
        "name": "call_agent",
        "description": """다른 에이전트에게 작업을 위임합니다 (비동기).

## 위임 흐름
1. call_agent 호출 → 대상 에이전트에게 메시지 전송
2. 대상 에이전트가 작업 수행 (비동기)
3. 완료 시 자동으로 결과가 당신에게 보고됨
4. 결과를 받아 최종 처리 후 사용자에게 응답

## 사용 시점
- 다른 전문 분야의 에이전트가 필요할 때
- 자신의 도구로 처리할 수 없는 작업일 때
- 병렬로 여러 작업을 진행해야 할 때

## 사용 전 확인
1. list_agents로 사용 가능한 에이전트 확인
2. get_my_tools로 자신의 도구 확인 (직접 처리 가능한지)

## 금지 사항
- 자기 자신에게 위임 금지
- 에이전트가 1명뿐이면 위임 불가 (직접 처리)
- 무한 위임 체인 금지

## 병렬 위임
여러 에이전트에게 동시 위임 가능. 모든 응답이 도착하면 통합 결과 수신.

## 주의
call_agent 호출 후 바로 응답하지 마세요. 결과 보고가 도착할 때까지 기다렸다가 최종 응답.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "호출할 에이전트 이름 또는 ID (예: '내과', 'agent_001')"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 요청 내용. 명확하고 구체적으로 작성."
                }
            },
            "required": ["agent_id", "message"]
        }
    },
    {
        "name": "list_agents",
        "description": """현재 프로젝트의 에이전트 목록을 조회합니다.

## 반환 정보
- id: 에이전트 ID
- name: 에이전트 이름
- role_description: 역할 설명
- active: 활성화 여부
- running: 현재 실행 중 여부

## 사용 시점
- call_agent 전 적합한 대상 확인
- 프로젝트 내 협업 가능한 에이전트 파악
- 실행 중인 에이전트 확인

## 주의
- running=false인 에이전트는 호출 불가
- 위임 전 반드시 확인 권장""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "send_notification",
        "description": """사용자에게 알림을 보냅니다.

## 알림 유형
- info: 일반 정보 (기본값)
- success: 성공 메시지 (녹색)
- warning: 주의 메시지 (노란색)
- error: 오류 메시지 (빨간색)

## 사용 시점
- 장시간 작업 완료 알림
- 중요한 이벤트 발생 시
- 스케줄 작업 결과 보고
- 오류/경고 상황 알림

## 주의
- 일반적인 응답은 알림 대신 직접 메시지로
- 너무 빈번한 알림은 피할 것""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "알림 제목 (간결하게)"
                },
                "message": {
                    "type": "string",
                    "description": "알림 본문 내용"
                },
                "type": {
                    "type": "string",
                    "description": "알림 유형: info, success, warning, error (기본: info)"
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "get_project_info",
        "description": """현재 프로젝트의 정보를 조회합니다.

## 반환 정보
- name: 프로젝트 이름
- description: 프로젝트 설명
- agent_count: 에이전트 수
- agents: 에이전트 목록 (id, name, active)
- path: 프로젝트 경로

## 사용 시점
- 프로젝트 구조 파악
- 협업 가능한 에이전트 확인
- 프로젝트 컨텍스트 이해""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_my_tools",
        "description": """현재 에이전트에게 허용된 도구 목록을 조회합니다.

## 반환 정보
- tools: 사용 가능한 전체 도구 목록
- base_tools: 시스템 기본 도구 (call_agent, list_agents 등)
- allowed_tools: 허용된 도구 패키지 도구들

## 사용 시점
- 위임 전 자가 처리 가능 여부 판단
- 자신의 역량 범위 확인
- 도구 사용 가능 여부 확인

## 위임 결정 기준
1. get_my_tools로 내 도구 확인
2. 필요한 작업이 내 도구로 가능하면 → 직접 처리
3. 내 도구로 불가능하면 → list_agents로 적합한 에이전트 찾아 call_agent로 위임""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# 시스템 도구 이름 목록
SYSTEM_TOOL_NAMES = [t["name"] for t in SYSTEM_TOOLS]


def is_system_tool(tool_name: str) -> bool:
    """시스템 도구인지 확인"""
    return tool_name in SYSTEM_TOOL_NAMES


# ============ 시스템 도구 실행 ============

# 위임 계층은 system_tools_delegate.py 로 이동 (2026-07-18 모듈화) — 재수출로 경로 불변.
from system_tools_delegate import (  # noqa: E402,F401
    execute_call_agent,
    _send_to_running_agent,
    _create_child_task,
    _get_or_create_delegation_context,
    _check_agents_yaml,
    execute_list_agents,
)


def execute_send_notification(tool_input: dict, project_path: str) -> str:
    """send_notification 도구 실행"""
    title = tool_input.get("title", "")
    message = tool_input.get("message", "")
    noti_type = tool_input.get("type", "info")

    try:
        from notification_manager import get_notification_manager
        nm = get_notification_manager()
        notification = nm.create(title=title, message=message, type=noti_type)
        return json.dumps({"success": True, "notification_id": notification["id"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_get_project_info(tool_input: dict, project_path: str) -> str:
    """get_project_info 도구 실행"""
    try:
        import yaml as yaml_lib

        project_json = Path(project_path) / "project.json"
        project_data = {}
        if project_json.exists():
            project_data = json.loads(project_json.read_text(encoding='utf-8'))

        agents_yaml = Path(project_path) / "agents.yaml"
        agents = []
        if agents_yaml.exists():
            agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
            agents = agents_data.get("agents", [])

        project_name = Path(project_path).name

        info = {
            "name": project_data.get("name", project_name),
            "description": project_data.get("description", ""),
            "agent_count": len(agents),
            "agents": [{"id": a.get("id"), "name": a.get("name"), "active": a.get("active", True)} for a in agents],
            "path": str(project_path)
        }

        return json.dumps({"success": True, "project": info}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_get_my_tools(tool_input: dict, project_path: str, agent_id: str = None) -> str:
    """get_my_tools 도구 실행

    Phase 16: ibl_only 모드에서는 IBL 환경(allowed_nodes)을 기반으로
    에이전트의 도구를 보여줌. execute_ibl이 유일한 실행 도구.
    """
    try:
        from agent_runner import AgentRunner
        from thread_context import get_current_registry_key, get_current_project_id

        # 1. thread_context에서 시도
        registry_key = get_current_registry_key()

        # 2. thread_context 실패 시 agent_id + project_path로 구성
        if not registry_key and agent_id:
            project_id = get_current_project_id()
            if not project_id and project_path:
                from pathlib import Path
                project_id = Path(project_path).name
            registry_key = f"{project_id}:{agent_id}" if project_id else agent_id

        if not registry_key:
            return json.dumps({
                "success": False,
                "tools": [],
                "message": "현재 에이전트를 식별할 수 없습니다"
            }, ensure_ascii=False)

        runner = AgentRunner.agent_registry.get(registry_key)

        # 3. registry_key로 못 찾으면 agent_id로 직접 검색 (fallback)
        if not runner and agent_id:
            with AgentRunner._lock:
                for key, r in AgentRunner.agent_registry.items():
                    if key.endswith(f":{agent_id}"):
                        runner = r
                        break

        if not runner:
            return json.dumps({
                "success": False,
                "tools": [],
                "message": f"에이전트 정보를 찾을 수 없습니다 (key: {registry_key})"
            }, ensure_ascii=False)

        # Phase 16: ibl_only 모드 - allowed_nodes 기반
        allowed_nodes = runner.config.get('allowed_nodes', [])
        ibl_tools = ["execute_ibl", "ask_user_question", "todo_write", "request_user_approval"]
        if runner._get_agent_count() > 1:
            ibl_tools.append("list_agents")

        return json.dumps({
            "success": True,
            "mode": "ibl_only",
            "tools": ibl_tools,
            "allowed_nodes": allowed_nodes if allowed_nodes else "all (제한 없음)",
            "message": f"IBL 모드: execute_ibl 1개 + 시스템 도구 {len(ibl_tools) - 1}개, 접근 가능 노드: {len(allowed_nodes) if allowed_nodes else '전체'}개"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "tools": [],
            "message": f"에러 발생: {str(e)}"
        }, ensure_ascii=False)


# ============ $file:N 치환 헬퍼 ============

# IBL 통합 실행 본체는 system_tools_ibl.py 로 이동 (2026-07-18 모듈화) — 재수출로 경로 불변.
from system_tools_ibl import (  # noqa: E402,F401
    _replace_file_refs_in_steps,
    _replace_file_refs_in_dict,
    _replace_file_refs_in_list,
    _enrich_error_with_param_hint,
    _execute_ibl_unified,
)


def execute_ask_user_question(tool_input: dict, project_path: str) -> str:
    """ask_user_question 실행 - 사용자에게 질문 (Phase 17: IBL user 노드)

    이 도구는 AI가 호출하면 input이 웹소켓을 통해 프론트엔드에 전달됩니다.
    실행 결과는 사용자 응답이 올 때까지 대기하는 마커를 반환합니다.
    """
    questions = tool_input.get("questions", [])
    if not questions:
        return json.dumps({"status": "no_questions"}, ensure_ascii=False)
    # 프론트엔드가 이 결과를 감지하여 질문 UI를 표시
    return json.dumps({
        "_ibl_user_action": "ask_user_question",
        "questions": questions
    }, ensure_ascii=False)


def execute_todo_write(tool_input: dict, project_path: str) -> str:
    """todo_write 실행 - 할일 목록 관리 (Phase 17: IBL user 노드)

    이 도구는 AI가 호출하면 input이 웹소켓을 통해 프론트엔드에 전달됩니다.
    """
    todos = tool_input.get("todos", [])
    return json.dumps({
        "_ibl_user_action": "todo_write",
        "todos": todos,
        "status": "updated",
        "count": len(todos)
    }, ensure_ascii=False)


def execute_request_user_approval(tool_input: dict, project_path: str) -> str:
    """request_user_approval 도구 실행 - 사용자 승인 요청"""
    action_type = tool_input.get("action_type", "작업")
    description = tool_input.get("description", "")
    affected_items = tool_input.get("affected_items", [])

    result_parts = [
        "🔔 **승인 요청**",
        f"**작업 유형**: {action_type}",
        f"**설명**: {description}"
    ]
    if affected_items:
        result_parts.append(f"**영향받는 항목**: {', '.join(affected_items)}")
    result_parts.append("\n진행하시려면 '승인' 또는 '진행해'라고 답해주세요.")

    # 특수 마커 추가 - 도구 호출 루프에서 이를 감지하여 중단
    return "[[APPROVAL_REQUESTED]]" + "\n".join(result_parts)


def _dict_to_json(result) -> str:
    """dict 결과를 JSON 문자열로 변환, _ibl_guide 잔여 메타데이터 제거"""
    if isinstance(result, dict):
        result.pop("_ibl_guide", None)
        return json.dumps(result, ensure_ascii=False, indent=2)
    return result



# ============ 지도 봉투 수확 (단일 관문) ============
# 채팅 지도 전달 계약: 핸들러가 map_data 봉투를 어디에 두든(단독 최상위 / 파이프 step 내부 /
# 병렬 브랜치 = JSON-문자열-in-리스트-in-문자열) 여기 한 곳에서 재귀 수확해 [MAP:] 태그로 변환한다.
# 프론트 parseMapData(chatUtils.ts)는 type==location_map|route_map 만 렌더하므로 정규화까지 책임진다.
# 모양별 승격 분기 금지 — 실행 모양이 늘 때마다 지도가 유실되던 원인(2026-07-13 에피소드 760~763).

def _pluck_map_envelopes(node, found, depth=0):
    """결과 트리에서 map_data 봉투를 pop 으로 뽑아 수집(변이). 중첩 JSON 문자열도 파고들어,
    뽑힌 층만 재직렬화해 되돌린다. 반환값 = 정리된 노드."""
    # 상한 16 (claude_code._extract_map_tags 와 동일): 실행 모양이 한두 겹 더 감싸져도
    # (래핑 문자열 1겹 = +2 깊이) 봉투가 조용히 유실되지 않게 여유를 둔다 — 에피소드 802.
    if depth > 16:
        return node
    if isinstance(node, dict):
        md = node.pop("map_data", None)
        if isinstance(md, dict):
            found.append(md)
        for k in list(node.keys()):
            node[k] = _pluck_map_envelopes(node[k], found, depth + 1)
        return node
    if isinstance(node, list):
        return [_pluck_map_envelopes(v, found, depth + 1) for v in node]
    if isinstance(node, str) and "map_data" in node:
        try:
            inner = json.loads(node)
        except (json.JSONDecodeError, TypeError):
            return node
        n_before = len(found)
        inner = _pluck_map_envelopes(inner, found, depth + 1)
        if len(found) > n_before:
            return json.dumps(inner, ensure_ascii=False, indent=2)
        return node
    return node


def _merge_map_envelopes(envelopes):
    """수확한 봉투들 → 프론트 렌더 계약으로 정규화. route_map 은 각자 유지,
    location 계열(type 없는 레거시 {markers} 포함)은 마커 합집합 한 장으로 병합."""
    routes, markers, seen = [], [], set()
    for e in envelopes:
        if not isinstance(e, dict):
            continue
        if e.get("type") == "route_map":
            routes.append(e)
            continue
        for m in e.get("markers", []) or []:
            try:
                lat, lng = float(m.get("lat")), float(m.get("lng"))
            except (TypeError, ValueError):
                continue
            key = (m.get("name"), round(lat, 6), round(lng, 6))
            if key in seen:
                continue
            seen.add(key)
            markers.append({**m, "lat": lat, "lng": lng})
    out = list(routes)
    if markers:
        clat = sum(m["lat"] for m in markers) / len(markers)
        clng = sum(m["lng"] for m in markers) / len(markers)
        spread = max(max(abs(m["lat"] - clat) for m in markers),
                     max(abs(m["lng"] - clng) for m in markers))
        zoom = 10 if spread > 0.2 else (11 if spread > 0.05 else 13)
        out.append({"type": "location_map",
                    "center": {"name": "검색 결과", "lat": clat, "lng": clng},
                    "zoom": zoom, "markers": markers})
    return out


# ============ 도구 중단 지원 ============

# 현재 실행 중인 도구 스레드 추적 (cancel 시 사용)
_active_tool_threads: dict[str, threading.Thread] = {}


class ToolCancelled(Exception):
    """도구 실행이 사용자에 의해 중단됨"""
    pass


def execute_tool(tool_name: str, tool_input: dict, project_path: str, agent_id: str = None,
                 cancel_check=None):
    """
    도구 실행 (IBL 형식 로깅 래퍼)
    cancel_check가 주어지면 별도 스레드에서 실행하고 중단 가능하게 함.

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력
        project_path: 프로젝트 경로 (필수, 호출자가 명시 전달)
        agent_id: 에이전트 ID (에이전트별 상태 저장용)
        cancel_check: 중단 여부 확인 함수 (None이면 기존 동기 실행)

    Returns:
        실행 결과 (JSON 문자열 또는 dict)
    """
    import time as _time
    start = _time.time()
    success = True

    try:
        # cancel_check가 있으면 별도 스레드에서 실행 (중단 가능)
        if cancel_check:
            result = _execute_tool_with_cancel(tool_name, tool_input, project_path, agent_id, cancel_check)
        else:
            result = _execute_tool_inner(tool_name, tool_input, project_path, agent_id)

        # [MAP:...] 태그 변환 — 결과 트리 전체를 재귀 수확하는 단일 관문.
        # 단독/파이프/병렬/중첩 깊이 무관. 태그는 결과 끝에 부착(프로바이더 재주입 regex가 끝 앵커).
        if isinstance(result, str) and "map_data" in result:
            try:
                tree = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                tree = None
            if tree is not None:
                _found = []
                tree = _pluck_map_envelopes(tree, _found)
                _maps = _merge_map_envelopes(_found)
                if _maps:
                    _tags = "".join(f"\n\n[MAP:{json.dumps(m, ensure_ascii=False)}]" for m in _maps)
                    result = json.dumps(tree, ensure_ascii=False, indent=2) + _tags

        # 결과에서 성공/실패 판단
        if isinstance(result, str):
            try:
                r = json.loads(result)
                if isinstance(r, dict) and r.get("success") is False:
                    success = False
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(result, dict) and result.get("success") is False:
            success = False

        return result
    except ToolCancelled:
        success = False
        return json.dumps({"success": False, "error": "사용자가 작업을 중단했습니다."}, ensure_ascii=False)
    except Exception as e:
        success = False
        raise
    finally:
        duration_ms = (_time.time() - start) * 1000
        _log_ibl(tool_name, tool_input, duration_ms, agent_id, success)


def _execute_tool_with_cancel(tool_name, tool_input, project_path, agent_id, cancel_check):
    """도구를 별도 스레드에서 실행하고, cancel_check로 중단 감지"""
    result_holder = [None]
    error_holder = [None]

    def _run():
        try:
            result_holder[0] = _execute_tool_inner(tool_name, tool_input, project_path, agent_id, cancel_check=cancel_check)
        except Exception as e:
            error_holder[0] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread_key = f"{agent_id or 'system'}_{id(thread)}"
    _active_tool_threads[thread_key] = thread
    thread.start()

    # 0.5초 간격으로 cancel 체크하며 스레드 완료 대기
    while thread.is_alive():
        thread.join(timeout=0.5)
        if cancel_check and cancel_check():
            print(f"[도구 중단] {tool_name} — 사용자 중단 요청, 스레드를 버리고 진행")
            _active_tool_threads.pop(thread_key, None)
            # 스레드는 daemon이므로 프로세스 종료 시 자동 정리됨
            raise ToolCancelled()

    _active_tool_threads.pop(thread_key, None)

    if error_holder[0]:
        raise error_holder[0]
    return result_holder[0]


def _execute_tool_inner(tool_name: str, tool_input: dict, project_path: str, agent_id: str = None, cancel_check=None) -> str:
    """도구 실행 내부 구현 (시스템 도구 + 동적 로딩). project_path는 필수."""
    try:
        # 승인 요청 도구 (가장 먼저 처리)
        if tool_name == "request_user_approval":
            return execute_request_user_approval(tool_input, project_path)

        # 가이드 검색 (독립 도구 — IBL/Python 어디서든 사용 가능)
        if tool_name == "read_guide":
            from ibl_engine import _search_guide
            query = tool_input.get("query", "")
            read = tool_input.get("read", True)
            result = _search_guide(query, {"read": read})
            return json.dumps(result, ensure_ascii=False, indent=2)

        # IBL 통합 실행기 (Phase 13)
        if tool_name == "execute_ibl":
            return _execute_ibl_unified(tool_input, project_path, agent_id, cancel_check=cancel_check)

        # 시스템 도구 처리
        if tool_name == "call_agent":
            return execute_call_agent(tool_input, project_path)
        elif tool_name == "list_agents":
            return execute_list_agents(tool_input, project_path)
        elif tool_name == "send_notification":
            return execute_send_notification(tool_input, project_path)
        elif tool_name == "get_project_info":
            return execute_get_project_info(tool_input, project_path)
        elif tool_name == "get_my_tools":
            return execute_get_my_tools(tool_input, project_path, agent_id)
        # API 레지스트리 기반 실행 (Phase 1)
        if is_registry_tool(tool_name):
            result = registry_execute_tool(tool_name, tool_input, project_path)
            if isinstance(result, dict) and "images" in result:
                return result
            result = _dict_to_json(result)
            return result

        # 동적 로딩된 도구 패키지에서 실행 (레지스트리 미등록 도구용)
        handler = load_tool_handler(tool_name)
        if handler and hasattr(handler, 'execute'):
            # 신규 시그니처 execute(tool_input, context: ToolContext)만 지원
            import inspect
            sig = inspect.signature(handler.execute)
            if 'context' not in sig.parameters:
                return json.dumps({
                    "success": False,
                    "error": (
                        f"도구 핸들러가 구 시그니처를 사용합니다: {tool_name}. "
                        "신규 시그니처 execute(tool_input, context: ToolContext)로 마이그레이션이 필요합니다."
                    )
                }, ensure_ascii=False)

            from ibl_routing import _resolve_project_path
            from tool_context import ToolContext, ToolContextError
            resolved_path = _resolve_project_path(project_path, tool_input)
            if not resolved_path:
                return json.dumps({
                    "success": False,
                    "error": (
                        f"활성 프로젝트 경로를 확보할 수 없어 도구를 실행할 수 없습니다: {tool_name}. "
                        "대상 프로젝트를 params.project_id로 명시하거나 "
                        "프로젝트 컨텍스트(thread_context.project_id) 안에서 호출하세요. "
                        "예: execute_ibl(code='[node:action]{..., project_id: \"컨텐츠\"}')"
                    )
                }, ensure_ascii=False)
            try:
                context = ToolContext.from_thread_context(resolved_path, tool_name)
            except ToolContextError as e:
                return json.dumps({"success": False, "error": f"ToolContext 생성 실패: {e}"}, ensure_ascii=False)

            result = handler.execute(tool_input, context)

            # async 핸들러 지원: coroutine이면 영구 이벤트 루프에서 실행
            if asyncio.iscoroutine(result):
                result = _run_coroutine(result)

            # [images] 이미지를 포함한 dict 결과는 그대로 반환 (providers가 처리)
            if isinstance(result, dict) and "images" in result:
                return result

            # dict → JSON 변환 (_ibl_guide 잔여 메타데이터 제거 포함)
            result = _dict_to_json(result)

            # 승인 필요 여부 확인
            if isinstance(result, str) and result.startswith("__REQUIRES_APPROVAL__:"):
                command = result.replace("__REQUIRES_APPROVAL__:", "")
                return json.dumps({
                    "requires_approval": True,
                    "command": command,
                    "message": f"⚠️ 위험한 명령어가 감지되었습니다:\n\n`{command}`\n\n이 명령어를 실행하려면 '승인' 또는 'yes'라고 답해주세요."
                }, ensure_ascii=False)

            return result
        else:
            # IBL 액션 패턴 감지 (node:action) → execute_ibl로 자동 라우팅
            # 모델이 execute_ibl 대신 "self:todo", "sense:search" 같은 이름으로 직접 호출하는 경우 방어
            if ':' in tool_name:
                node, action = tool_name.split(':', 1)
                ibl_nodes = ['sense', 'self', 'limbs', 'others', 'engines']
                if node in ibl_nodes:
                    # tool_input을 IBL params로 변환
                    params_str = ", ".join(f'{k}: "{v}"' if isinstance(v, str) else f'{k}: {v}' for k, v in tool_input.items()) if tool_input else ""
                    ibl_code = f"[{tool_name}]{{{params_str}}}" if params_str else f"[{tool_name}]"
                    print(f"[system_tools] ⚡ IBL 액션 직접 호출 감지: {tool_name} → execute_ibl({ibl_code})")
                    return _execute_ibl_unified({"code": ibl_code}, project_path, agent_id, cancel_check=cancel_check)
            return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
