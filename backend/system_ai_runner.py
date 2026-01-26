"""
system_ai_runner.py - 시스템 AI 실행 엔진
IndieBiz OS Core

시스템 AI를 상주 프로세스로 실행하고 메시지 큐를 처리합니다.
프로젝트 에이전트로부터 위임 결과를 수신하고 처리합니다.
"""

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from ai_agent import AIAgent
from system_ai_memory import (
    load_user_profile,
    save_conversation,
    get_recent_conversations,
    create_task,
    get_task,
    complete_task,
    update_task_delegation,
    decrement_pending_and_update_context
)
from system_ai import (
    SYSTEM_AI_DEFAULT_PACKAGES,
    load_tools_from_packages,
    execute_system_tool
)
from prompt_builder import build_system_ai_prompt


class SystemAIRunner:
    """시스템 AI 실행기 - 메시지 큐 기반 비동기 처리"""

    # 클래스 변수 (AgentRunner와 공유 가능하도록 설계)
    internal_messages: List[dict] = []  # 시스템 AI 전용 메시지 큐
    _instance: Optional['SystemAIRunner'] = None  # 싱글톤
    _lock = threading.RLock()

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.ai: Optional[AIAgent] = None

        # 경로 설정
        self.backend_path = Path(__file__).parent
        self.data_path = self.backend_path.parent / "data"

        # 싱글톤 등록
        SystemAIRunner._instance = self

    @classmethod
    def get_instance(cls) -> Optional['SystemAIRunner']:
        """싱글톤 인스턴스 반환"""
        return cls._instance

    @classmethod
    def send_message(cls, content: str, from_agent: str, task_id: str = None, project_id: str = None):
        """시스템 AI에게 메시지 전송 (외부에서 호출)

        Args:
            content: 메시지 내용
            from_agent: 발신 에이전트 이름
            task_id: 태스크 ID
            project_id: 프로젝트 ID (에이전트 식별용)
        """
        msg_dict = {
            'content': content,
            'from_agent': from_agent,
            'task_id': task_id,
            'project_id': project_id,
            'timestamp': datetime.now().isoformat()
        }
        with cls._lock:
            cls.internal_messages.append(msg_dict)
        print(f"[SystemAIRunner] 메시지 수신 대기열 추가: {from_agent}@{project_id}")

    def start(self):
        """시스템 AI 시작"""
        if self.running:
            return

        self.running = True
        self.cancel_event.clear()

        # AI 에이전트 초기화
        self._init_ai()

        # 백그라운드 스레드 시작
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print("[SystemAIRunner] 시스템 AI 시작됨")

    def stop(self):
        """시스템 AI 중지"""
        self.running = False
        self.cancel_event.set()

        if self.thread:
            self.thread.join(timeout=5)

        print("[SystemAIRunner] 시스템 AI 중지됨")

    def _init_ai(self):
        """AI 에이전트 초기화"""
        from api_system_ai import load_system_ai_config

        config = load_system_ai_config()
        user_profile = load_user_profile()

        ai_config = {
            "provider": config.get("provider", "anthropic"),
            "model": config.get("model", "claude-sonnet-4-20250514"),
            "api_key": config.get("apiKey", "")
        }

        tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES)

        # 위임 관련 도구 추가 (api_system_ai.py에서 가져옴)
        from api_system_ai import _get_list_project_agents_tool, _get_call_project_agent_tool
        tools.append(_get_list_project_agents_tool())
        tools.append(_get_call_project_agent_tool())

        # Git 활성화 조건: run_command 도구가 있고 .git 폴더가 있을 때
        tool_names = [t.get("name") for t in tools]
        git_enabled = "run_command" in tool_names and (self.data_path / ".git").exists()

        system_prompt = build_system_ai_prompt(user_profile=user_profile, git_enabled=git_enabled)

        self.ai = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name="시스템 AI",
            agent_id="system_ai",
            project_path=str(self.data_path),
            tools=tools,
            execute_tool_func=self._execute_tool
        )

    def _get_call_project_agent_tool(self) -> dict:
        """call_project_agent 도구 정의"""
        return {
            "name": "call_project_agent",
            "description": """프로젝트의 에이전트에게 작업을 위임합니다.

사용 시나리오:
- 특정 프로젝트의 전문 에이전트에게 작업을 맡기고 싶을 때
- 프로젝트별 도구나 컨텍스트가 필요한 작업일 때

주의사항:
- 위임 후 결과를 기다려야 합니다
- 에이전트가 작업을 완료하면 자동으로 결과를 보고받습니다""",
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

    def _execute_tool(self, tool_name: str, tool_input: dict, work_dir: str = None, agent_id: str = None) -> str:
        """도구 실행 (api_system_ai.py의 execute_system_tool 재사용)"""
        from api_system_ai import execute_system_tool as execute_system_ai_tool
        return execute_system_ai_tool(tool_name, tool_input, work_dir or str(self.data_path), agent_id)

    def _execute_call_project_agent(self, tool_input: dict) -> str:
        """프로젝트 에이전트 호출 실행"""
        from agent_runner import AgentRunner
        from thread_context import get_current_task_id, set_called_agent

        project_id = tool_input.get("project_id", "")
        agent_id = tool_input.get("agent_id", "")
        message = tool_input.get("message", "")

        if not project_id or not agent_id or not message:
            return "오류: project_id, agent_id, message가 모두 필요합니다."

        # 대상 에이전트 찾기
        registry_key = f"{project_id}:{agent_id}"
        target = AgentRunner.agent_registry.get(registry_key)

        if not target:
            return f"오류: 에이전트를 찾을 수 없습니다. (project_id: {project_id}, agent_id: {agent_id})"

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
            if delegation_context_str:
                delegation_context = json.loads(delegation_context_str)
            else:
                delegation_context = {
                    'original_request': parent_task.get('original_request', ''),
                    'requester': parent_task.get('requester', 'user@gui'),
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
        project_id = target.project_id
        print(f"[SystemAIRunner] 위임: 시스템 AI → {agent_name} (task: {child_task_id})")

        # 시스템 AI → 프로젝트 에이전트 위임 메시지 DB 기록 (system_ai_memory.db)
        try:
            save_conversation(
                role="delegation",
                content=f"[위임] 시스템 AI → {agent_name}@{project_id}: {message}",
                source=f"system_ai→{agent_name}@{project_id}"
            )
        except Exception as e:
            print(f"[SystemAIRunner] 위임 메시지 system_ai_memory DB 기록 실패: {e}")

        # 프로젝트 conversations.db에도 기록 (중복 기록)
        try:
            system_ai_id = target.db.get_or_create_agent("시스템 AI", "system")
            agent_db_id = target.db.get_or_create_agent(agent_name, "ai_agent")
            target.db.save_message(system_ai_id, agent_db_id, message, contact_type='system_ai_delegation')
        except Exception as e:
            print(f"[SystemAIRunner] 위임 메시지 프로젝트 DB 기록 실패: {e}")

        return f"'{agent_name}'에게 작업을 위임했습니다. 결과를 기다리세요."

    def _run_loop(self):
        """백그라운드 루프 (메시지 큐 폴링)"""
        import time

        while self.running and not self.cancel_event.is_set():
            try:
                self._check_internal_messages()

                # 1초마다 메시지 확인
                time.sleep(1)

            except Exception as e:
                print(f"[SystemAIRunner] 루프 에러: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

    def _check_internal_messages(self):
        """내부 메시지 확인 및 처리"""
        with SystemAIRunner._lock:
            if not SystemAIRunner.internal_messages:
                return
            msg_dict = SystemAIRunner.internal_messages.pop(0)

        while msg_dict:
            if not isinstance(msg_dict, dict):
                with SystemAIRunner._lock:
                    if not SystemAIRunner.internal_messages:
                        break
                    msg_dict = SystemAIRunner.internal_messages.pop(0)
                continue

            try:
                from_agent = msg_dict.get('from_agent', 'unknown')
                content = msg_dict.get('content', '')
                task_id = msg_dict.get('task_id')
                project_id = msg_dict.get('project_id', '')

                # 에이전트 식별자: 에이전트명@프로젝트ID
                agent_identifier = f"{from_agent}@{project_id}" if project_id else from_agent

                print(f"[SystemAIRunner] 메시지 수신: {agent_identifier}")
                print(f"   내용: {content[:100]}..." if len(content) > 100 else f"   내용: {content}")

                # 프로젝트 에이전트 → 시스템 AI 메시지 DB 기록
                try:
                    save_conversation(
                        role="agent_report",
                        content=f"[수신] {agent_identifier} → 시스템 AI: {content}",
                        source=f"{agent_identifier}→system_ai"
                    )
                except Exception as e:
                    print(f"[SystemAIRunner] 수신 메시지 DB 기록 실패: {e}")

                # 태스크 ID 추출
                extracted_task_id = task_id
                if not extracted_task_id:
                    task_match = re.search(r'\[task:([^\]]+)\]', content)
                    if task_match:
                        extracted_task_id = task_match.group(1)

                if extracted_task_id:
                    print(f"   [task_id] {extracted_task_id}")

                # 위임 컨텍스트 복원
                delegation_context = None
                is_report_message = any(keyword in content for keyword in ['완료', '보고', '결과'])

                if is_report_message and extracted_task_id:
                    task = get_task(extracted_task_id)
                    if task and task.get('delegation_context'):
                        try:
                            delegation_context = json.loads(task['delegation_context'])
                            delegations = delegation_context.get('delegations', [])
                            print(f"   [위임 컨텍스트 복원] {len(delegations)}개 위임의 결과 수신")
                        except json.JSONDecodeError:
                            print(f"   [위임 컨텍스트] JSON 파싱 실패")

                # AI 처리
                if self.ai:
                    ai_message = content
                    history = []

                    # 컨텍스트 리마인더 및 히스토리 구성
                    if delegation_context:
                        original_request = delegation_context.get('original_request', '')
                        completed = delegation_context.get('completed', [])

                        # 완료된 위임 기록을 히스토리로 변환
                        history = self._build_history_from_completed(completed)

                        # 완료된 작업 목록 포맷팅
                        completed_summary = self._format_completed_delegations(completed)

                        ai_message = f"""[위임 결과]
{content}

---
{completed_summary}
원래 요청: {original_request}

위 결과를 바탕으로:
- 추가 작업이 필요하면 다른 에이전트에게 위임하세요.
- 모든 작업이 완료되었으면 사용자에게 최종 결과를 전달하세요."""

                    from thread_context import set_current_task_id, clear_current_task_id, set_called_agent, did_call_agent, clear_called_agent

                    if extracted_task_id:
                        set_current_task_id(extracted_task_id)
                    clear_called_agent()

                    response = self.ai.process_message_with_history(
                        message_content=ai_message,
                        from_email=f"{from_agent}@internal",
                        history=history,
                        reply_to=f"{from_agent}@internal"
                    )
                    print(f"[SystemAIRunner] 응답 생성: {len(response)}자")

                    # 시스템 AI가 에이전트 보고를 받아 처리한 결과는 사용자에게 전달됨
                    # (에이전트에게 응답하는 것이 아님 - 시스템 AI는 위임만 하고 위임받지 않음)
                    # 최종 응답은 _finalize_task()에서 save_conversation("assistant", response)로 기록됨

                    called_another = did_call_agent()

                    if called_another:
                        # 새 위임이 발생함 → 태스크 유지, 위임 결과 대기
                        print(f"[SystemAIRunner] call_project_agent 호출됨 - 새 위임 사이클 시작")
                    else:
                        # 새 위임 없음 → 최종 응답, 태스크 완료 (삭제됨)
                        if extracted_task_id:
                            self._finalize_task(extracted_task_id, response)
                        else:
                            print(f"[SystemAIRunner] 응답 (태스크 없음): {response[:200]}...")

                    clear_current_task_id()
                    clear_called_agent()

            except Exception as e:
                import traceback
                print(f"[SystemAIRunner] 메시지 처리 실패: {e}")
                traceback.print_exc()

            # 다음 메시지
            with SystemAIRunner._lock:
                if not SystemAIRunner.internal_messages:
                    break
                msg_dict = SystemAIRunner.internal_messages.pop(0)

    def _build_history_from_completed(self, completed: list) -> list:
        """완료된 위임 기록을 AI 히스토리 형식으로 변환

        Args:
            completed: 완료된 위임 기록 리스트

        Returns:
            AI 히스토리 형식의 리스트 [{"role": "...", "content": "..."}]
        """
        history = []
        for entry in completed:
            to_agent = entry.get('to', '')
            message = entry.get('message', '')
            result = entry.get('result', '')

            # 내가 위임한 내역 (assistant 역할)
            history.append({
                "role": "assistant",
                "content": f"[위임] {to_agent}에게 요청: {message}"
            })

            # 에이전트의 응답 (user 역할로 표현 - 외부 입력이므로)
            if result:
                history.append({
                    "role": "user",
                    "content": f"[{to_agent} 응답] {result[:500]}..." if len(result) > 500 else f"[{to_agent} 응답] {result}"
                })

        return history

    def _format_completed_delegations(self, completed: list) -> str:
        """완료된 위임 기록을 텍스트로 포맷팅

        Args:
            completed: 완료된 위임 기록 리스트

        Returns:
            포맷팅된 문자열
        """
        if not completed:
            return ""

        lines = ["[이미 완료된 작업]"]
        for i, entry in enumerate(completed, 1):
            to_agent = entry.get('to', '')
            result = entry.get('result', '')
            # 파일 경로가 포함된 결과는 그대로 표시, 아니면 500자로 요약
            if '파일로 저장' in result or '/outputs/' in result:
                result_summary = result[:800] if len(result) > 800 else result
            else:
                result_summary = result[:500] + "..." if len(result) > 500 else result
            lines.append(f"{i}. {to_agent}: {result_summary}")

        return "\n".join(lines) + "\n"

    def _finalize_task(self, task_id: str, response: str):
        """태스크 완료 처리 및 사용자에게 응답"""
        task = get_task(task_id)
        if not task:
            print(f"[SystemAIRunner] task를 찾을 수 없음: {task_id}")
            return

        requester = task.get('requester', '')
        channel = task.get('requester_channel', 'gui')
        ws_client_id = task.get('ws_client_id')

        if channel == 'gui' and ws_client_id:
            self._send_to_gui(ws_client_id, response)  # 전체 응답 전송
        else:
            print(f"[SystemAIRunner] 최종 응답: {response[:200]}...")

        # 대화 히스토리에 저장
        save_conversation("assistant", response)

        # 태스크 완료 (요약본 저장)
        result_summary = response[:500] if len(response) > 500 else response
        complete_task(task_id, result_summary)
        print(f"[SystemAIRunner] 태스크 완료: {task_id}")

    def _send_to_gui(self, ws_client_id: str, response: str):
        """WebSocket을 통해 GUI에 응답 전송"""
        import asyncio

        try:
            from websocket_manager import manager

            if ws_client_id not in manager.active_connections:
                print(f"[SystemAIRunner] 클라이언트 연결 없음: {ws_client_id}")
                return

            asyncio.run(manager.send_message(ws_client_id, {
                "type": "system_ai_report",
                "content": response,
                "agent": "시스템 AI"
            }))
            print(f"[SystemAIRunner] WebSocket 전송 완료: {ws_client_id}")

        except Exception as e:
            print(f"[SystemAIRunner] GUI 전송 실패: {e}")
            import traceback
            traceback.print_exc()


# 편의 함수
def start_system_ai_runner(config: dict = None) -> SystemAIRunner:
    """시스템 AI Runner 시작"""
    runner = SystemAIRunner(config)
    runner.start()
    return runner


def stop_system_ai_runner():
    """시스템 AI Runner 중지"""
    instance = SystemAIRunner.get_instance()
    if instance:
        instance.stop()
