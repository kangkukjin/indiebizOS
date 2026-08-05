"""system_tools 위임(delegation) 계층 (2026-07-18 모듈화 — 1500줄 규칙)

system_tools.py 에서 verbatim 이동: call_agent(가동 에이전트 직송/자식 태스크 생성·
위임 체인 컨텍스트·agents.yaml 검증)·list_agents. system_tools 가 재수출하므로
기존 `from system_tools import execute_call_agent` 경로 불변.
"""
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path


def execute_call_agent(tool_input: dict, project_path: str) -> str:
    """call_agent 도구 실행 - 에이전트 간 통신"""
    agent_id_or_name = tool_input.get("agent_id", "")
    message = tool_input.get("message", "")

    try:
        from agent_runner import AgentRunner
        from thread_context import (
            get_current_agent_id, get_current_agent_name,
            get_current_task_id, set_called_agent
        )
        from conversation_db import ConversationDB

        # call_agent 호출 플래그 설정 (자동 보고 스킵용)
        set_called_agent(True)

        # 프로젝트 ID 추출
        project_id = Path(project_path).name

        # 1. 실행 중인 에이전트 레지스트리에서 찾기
        target_runner = AgentRunner.get_agent_by_name(agent_id_or_name, project_id=project_id)
        if not target_runner:
            target_runner = AgentRunner.get_agent_by_id(agent_id_or_name, project_id=project_id)

        if target_runner:
            return _send_to_running_agent(target_runner, message, project_path)

        # 2. 레지스트리에 없으면 agents.yaml 확인
        return _check_agents_yaml(agent_id_or_name, project_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _send_to_running_agent(target_runner, message: str, project_path: str) -> str:
    """실행 중인 에이전트에게 메시지 전송"""
    from agent_runner import AgentRunner
    from thread_context import get_current_agent_name, get_current_task_id
    from conversation_db import ConversationDB

    target_id = target_runner.config.get("id")
    target_name = target_runner.config.get("name")

    # 발신자 정보
    current_agent_name = get_current_agent_name()
    from_agent = current_agent_name if current_agent_name else "system"

    # 태스크 처리
    current_task_id = get_current_task_id()
    new_task_id = None

    if current_task_id:
        # 태스크 태그 제거
        message = re.sub(r'\[task:[^\]]+\]\s*', '', message)

        # 자식 태스크 생성
        new_task_id = _create_child_task(current_task_id, target_name, message, project_path)

        # 메시지에 태스크 ID 추가
        task_for_message = new_task_id if new_task_id else current_task_id
        message = f"[task:{task_for_message}] {message}"

    # 메시지 전송
    success = AgentRunner.send_message(
        to_agent_id=target_runner.registry_key,
        message=message,
        from_agent=from_agent,
        task_id=new_task_id if new_task_id else current_task_id
    )

    if success:
        # 에이전트 간 위임 메시지 DB 기록
        try:
            db = ConversationDB(str(Path(project_path) / "conversations.db"))
            from_agent_id = db.get_or_create_agent(from_agent, "ai_agent")
            to_agent_id = db.get_or_create_agent(target_name, "ai_agent")
            db.save_message(from_agent_id, to_agent_id, message, contact_type='delegation')
        except Exception as e:
            print(f"[call_agent] 위임 메시지 DB 기록 실패: {e}")

        return json.dumps({
            "success": True,
            "message": f"'{target_name}'에게 메시지를 전송했습니다. 비동기로 처리됩니다.",
            "agent": target_name,
            "task_id": new_task_id if new_task_id else current_task_id,
            "async": True
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": f"메시지 전송 실패: {target_name}"
        }, ensure_ascii=False)


def _create_child_task(parent_task_id: str, target_name: str, message: str, project_path: str) -> str:
    """위임 시 자식 태스크 생성"""
    from conversation_db import ConversationDB
    from thread_context import get_current_agent_name

    try:
        db_path = Path(project_path) / "conversations.db"
        db = ConversationDB(str(db_path))
        parent_task = db.get_task(parent_task_id)

        if not parent_task:
            return None

        new_task_id = f"task_{uuid.uuid4().hex[:8]}"
        from_agent = get_current_agent_name() or "system"

        # 위임 컨텍스트 구성
        existing_context = _get_or_create_delegation_context(parent_task)
        existing_context['delegations'].append({
            'child_task_id': new_task_id,
            'delegated_to': target_name,
            'delegation_message': message,
            'delegation_time': datetime.now().isoformat()
        })

        delegation_context = json.dumps(existing_context, ensure_ascii=False)
        db.update_task_delegation(parent_task_id, delegation_context, increment_pending=True)

        # 자식 태스크 생성
        # requester_channel은 "나에게 직접 위임한 부모가 누구인가"를 나타냄
        # 프로젝트 내부 에이전트 간 위임이므로 'internal'
        db.create_task(
            task_id=new_task_id,
            requester=from_agent,  # 나에게 위임한 에이전트
            requester_channel='internal',  # 프로젝트 내부 위임
            original_request=message,  # 부모가 나에게 보낸 위임 메시지
            delegated_to=target_name,
            parent_task_id=parent_task_id
        )

        print(f"   [call_agent] 자식 태스크 생성: {new_task_id} (parent: {parent_task_id})")
        print(f"   [call_agent] 위임: {from_agent} → {target_name}")

        return new_task_id

    except Exception as e:
        import traceback
        print(f"   [call_agent] 태스크 생성 실패: {e}")
        traceback.print_exc()
        return None


def _get_or_create_delegation_context(parent_task: dict) -> dict:
    """위임 컨텍스트 가져오기 또는 생성

    이전 위임 사이클이 완료된 경우:
    - completed 배열은 유지 (이전 작업 기록)
    - delegations, responses는 비움 (새 사이클용)

    Note:
        pending_delegations 카운터를 기준으로 완료 여부 판단 (Race Condition 방지)
        responses 배열 길이는 동시성 문제로 정확하지 않을 수 있음
    """
    existing_context_str = parent_task.get('delegation_context')
    pending = parent_task.get('pending_delegations', 0)

    if existing_context_str:
        try:
            existing_context = json.loads(existing_context_str)
            if 'delegations' not in existing_context:
                # 구 형식 → 새 형식으로 변환 (completed 유지)
                existing_context = {
                    'original_request': existing_context.get('original_request', ''),
                    'requester': existing_context.get('requester', ''),
                    'completed': existing_context.get('completed', []),
                    'delegations': [],
                    'responses': []
                }
                return existing_context

            # 이전 위임 사이클이 완료되었는지 확인
            # pending_delegations 카운터를 기준으로 판단 (DB에서 원자적으로 관리됨)
            delegations = existing_context.get('delegations', [])

            # pending_delegations == 0 이고 이전 위임이 있었으면 → 새 사이클 시작
            # 단, completed 배열은 유지!
            if len(delegations) > 0 and pending == 0:
                # 모든 응답이 도착함 → 새 위임 사이클 시작
                # 이전 사이클의 delegations+responses를 completed로 병합
                print(f"   [위임 컨텍스트] 이전 사이클 완료 (pending=0, delegations={len(delegations)}) → 새 사이클 준비")
                completed = existing_context.get('completed', [])
                responses = existing_context.get('responses', [])

                # 이전 사이클 결과를 completed에 병합
                response_map = {}
                for resp in responses:
                    child_id = resp.get('child_task_id', '')
                    response_map[child_id] = resp

                for deleg in delegations:
                    child_id = deleg.get('child_task_id', '')
                    resp = response_map.get(child_id, {})
                    completed.append({
                        'to': deleg.get('delegated_to', ''),
                        'message': deleg.get('delegation_message', ''),
                        'result': resp.get('response', '(응답 없음)'),
                        'completed_at': resp.get('completed_at', deleg.get('delegation_time', ''))
                    })

                print(f"   [위임 컨텍스트] {len(delegations)}개 위임 → completed에 병합 (총 {len(completed)}개)")

                return {
                    'original_request': parent_task.get('original_request', ''),
                    'requester': parent_task.get('requester', ''),
                    'completed': completed,  # 이전 작업 기록 포함
                    'delegations': [],
                    'responses': []
                }

            return existing_context
        except json.JSONDecodeError:
            pass

    return {
        'original_request': parent_task.get('original_request', ''),
        'requester': parent_task.get('requester', ''),
        'completed': [],
        'delegations': [],
        'responses': []
    }


def _check_agents_yaml(agent_id_or_name: str, project_path: str) -> str:
    """agents.yaml에서 에이전트 확인"""
    import yaml as yaml_lib
    from agent_runner import AgentRunner

    agents_yaml = Path(project_path) / "agents.yaml"
    if not agents_yaml.exists():
        return json.dumps({
            "success": False,
            "error": "에이전트 설정 파일(agents.yaml)을 찾을 수 없습니다."
        }, ensure_ascii=False)

    agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
    agents = agents_data.get("agents", [])

    # 이름 또는 ID로 에이전트 찾기
    target_agent = None
    for agent in agents:
        if agent.get("id") == agent_id_or_name or agent.get("name") == agent_id_or_name:
            target_agent = agent
            break

    if not target_agent:
        available_running = AgentRunner.get_all_agent_names()
        available_yaml = [f"{a.get('name')} (id: {a.get('id')})" for a in agents if a.get("active", True)]
        return json.dumps({
            "success": False,
            "error": f"에이전트를 찾을 수 없습니다: {agent_id_or_name}",
            "running_agents": available_running,
            "available_agents": available_yaml
        }, ensure_ascii=False)

    return json.dumps({
        "success": False,
        "error": f"에이전트 '{target_agent.get('name')}'가 실행 중이 아닙니다. 먼저 에이전트를 시작해주세요.",
        "agent": target_agent.get("name"),
        "agent_id": target_agent.get("id")
    }, ensure_ascii=False)


def execute_list_agents(tool_input: dict, project_path: str) -> str:
    """list_agents 도구 실행"""
    try:
        from agent_runner import AgentRunner
        import yaml as yaml_lib

        running_agents = AgentRunner.get_all_agents()
        running_ids = {a["id"] for a in running_agents}

        agents_yaml = Path(project_path) / "agents.yaml"
        if not agents_yaml.exists():
            return json.dumps({
                "success": True,
                "agents": running_agents,
                "running_count": len(running_agents)
            }, ensure_ascii=False)

        agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
        agents = agents_data.get("agents", [])

        agent_list = []
        for agent in agents:
            agent_id = agent.get("id")
            agent_list.append({
                "id": agent_id,
                "name": agent.get("name"),
                "type": agent.get("type", "internal"),
                "role_description": agent.get("role_description", ""),
                "active": agent.get("active", True),
                "running": agent_id in running_ids
            })

        return json.dumps({
            "success": True,
            "agents": agent_list,
            "running_count": len(running_agents)
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
