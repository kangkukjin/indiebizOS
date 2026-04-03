"""
agent_runner.py - 에이전트 실행 엔진
IndieBiz OS Core

에이전트를 백그라운드에서 실행하고 AI 대화를 처리합니다.
비동기 메시지 큐를 통한 에이전트 간 통신 및 위임 체인을 지원합니다.

모듈화:
- agent_cognitive.py: AI 초기화, 프롬프트, 의식 에이전트, 요청 분류, 평가 루프
- agent_communication.py: 채널 관리, 메시지 폴링, 내부 통신, 위임 체인
- agent_goals.py: Goal 실행, 판단 루프, 전략 해석, 조건 평가
"""

import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

from ai_agent import AIAgent
from conversation_db import ConversationDB, HISTORY_LIMIT_AGENT
from thread_context import (
    set_current_agent_id, set_current_agent_name, set_current_project_id,
    get_current_agent_id, get_current_agent_name, get_current_registry_key,
    set_current_task_id, get_current_task_id, clear_current_task_id,
    set_called_agent, did_call_agent, clear_called_agent,
    set_allowed_nodes
)

# Mixin 모듈
from agent_cognitive import AgentCognitiveMixin
from agent_communication import AgentCommunicationMixin
from agent_goals import AgentGoalsMixin


class AgentRunner(AgentCognitiveMixin, AgentCommunicationMixin, AgentGoalsMixin):
    """에이전트 실행기 - 비동기 메시지 큐 및 위임 체인 지원"""

    # 클래스 변수 (모든 인스턴스가 공유)
    internal_messages: Dict[str, List[dict]] = {}  # agent_id -> [메시지 dict]
    agent_registry: Dict[str, 'AgentRunner'] = {}  # agent_id -> AgentRunner 인스턴스
    # RLock 사용: 같은 스레드에서 중첩 호출 시 데드락 방지
    # (예: 메시지 처리 중 call_agent 호출 시 다시 Lock 획득 필요한 경우)
    _lock = threading.RLock()

    def __init__(self, agent_config: dict, common_config: dict = None, delegated_from_system_ai: bool = False):
        self.config = agent_config
        self.common_config = common_config or {}
        self.delegated_from_system_ai = delegated_from_system_ai

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()

        # AI 에이전트
        self.ai: Optional[AIAgent] = None

        # 채널 관리 (외부 에이전트용)
        self.channels: List = []
        self.processed_ids: set = set()

        # 프로젝트 정보
        self.project_path = Path(agent_config.get("_project_path", "."))
        self.project_id = agent_config.get("_project_id", "")

        # 대화 DB
        db_path = self.project_path / "conversations.db"
        self.db = ConversationDB(str(db_path))

        # 레지스트리에 등록 (스레드 안전)
        # 키 형식: {project_id}:{agent_id} - 프로젝트 간 충돌 방지
        agent_id = agent_config.get("id")
        if agent_id:
            registry_key = f"{self.project_id}:{agent_id}" if self.project_id else agent_id
            self.registry_key = registry_key  # stop()에서 사용
            with AgentRunner._lock:
                AgentRunner.agent_registry[registry_key] = self
                if registry_key not in AgentRunner.internal_messages:
                    AgentRunner.internal_messages[registry_key] = []
            print(f"[AgentRunner] {agent_config.get('name')} 레지스트리 등록됨 (key: {registry_key})")

    def start(self):
        """에이전트 시작"""
        if self.running:
            return

        self.running = True
        self.cancel_event.clear()

        # AI 에이전트 초기화
        self._init_ai()

        # 백그라운드 스레드 시작 (내부 메시지 폴링)
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print(f"[AgentRunner] {self.config.get('name')} 시작됨")

        # 에이전트 노드 캐시 무효화 (Phase 11)
        try:
            from node_registry import invalidate_agent_cache
            invalidate_agent_cache()
        except ImportError:
            pass

    def stop(self):
        """에이전트 중지"""
        self.running = False
        self.cancel_event.set()

        if self.thread:
            self.thread.join(timeout=5)

        # 레지스트리에서 제거
        registry_key = getattr(self, 'registry_key', None)
        if registry_key:
            with AgentRunner._lock:
                if registry_key in AgentRunner.agent_registry:
                    del AgentRunner.agent_registry[registry_key]
                if registry_key in AgentRunner.internal_messages:
                    del AgentRunner.internal_messages[registry_key]

        # 프로바이더 캐시 정리 (Gemini 컨텍스트 캐시 등)
        provider = getattr(self.ai, '_provider', None) if self.ai else None
        if provider and hasattr(provider, 'cleanup'):
            try:
                provider.cleanup()
            except Exception:
                pass

        # 에이전트 노드 캐시 무효화 (Phase 11)
        try:
            from node_registry import invalidate_agent_cache
            invalidate_agent_cache()
        except ImportError:
            pass

        print(f"[AgentRunner] {self.config.get('name')} 중지됨")

    def cancel(self):
        """현재 작업 취소"""
        self.cancel_event.set()

    # ============ 클래스 메서드: 에이전트 검색 ============

    @classmethod
    def get_agent_by_name(cls, name: str, project_id: str = None) -> Optional['AgentRunner']:
        """이름으로 에이전트 찾기 (스레드 안전)

        Args:
            name: 에이전트 이름
            project_id: 프로젝트 ID (지정하면 해당 프로젝트 내에서만 검색)
        """
        with cls._lock:
            for registry_key, runner in cls.agent_registry.items():
                if runner.config.get('name') == name:
                    # 프로젝트 ID가 지정되면 같은 프로젝트만 반환
                    if project_id and runner.project_id != project_id:
                        continue
                    return runner
        return None

    @classmethod
    def get_agent_by_id(cls, agent_id: str, project_id: str = None) -> Optional['AgentRunner']:
        """ID로 에이전트 찾기 (스레드 안전)

        Args:
            agent_id: 에이전트 ID
            project_id: 프로젝트 ID (지정하면 해당 프로젝트의 레지스트리 키로 검색)
        """
        with cls._lock:
            # 프로젝트 ID가 있으면 복합 키로 검색
            if project_id:
                registry_key = f"{project_id}:{agent_id}"
                return cls.agent_registry.get(registry_key)
            # 없으면 agent_id만으로 검색 (하위 호환)
            return cls.agent_registry.get(agent_id)

    @classmethod
    def get_all_agent_names(cls) -> List[str]:
        """모든 에이전트 이름 목록 (스레드 안전)"""
        with cls._lock:
            return [runner.config.get('name', '') for runner in cls.agent_registry.values()]

    @classmethod
    def get_all_agents(cls) -> List[dict]:
        """모든 에이전트 정보 목록 (스레드 안전)"""
        with cls._lock:
            result = []
            for agent_id, runner in cls.agent_registry.items():
                result.append({
                    "id": agent_id,
                    "name": runner.config.get("name", ""),
                    "type": runner.config.get("type", "internal"),
                    "running": runner.running
                })
            return result

    @classmethod
    def send_message(cls, to_agent_id: str, message: str, from_agent: str = "system",
                     task_id: str = None) -> bool:
        """
        에이전트에게 메시지 전송 (비동기)

        Args:
            to_agent_id: 대상 에이전트 ID
            message: 전달할 메시지
            from_agent: 발신 에이전트 이름
            task_id: 연관된 태스크 ID

        Returns:
            성공 여부
        """
        with cls._lock:
            if to_agent_id not in cls.agent_registry:
                return False

            msg_dict = {
                'content': message,
                'from_agent': from_agent,
                'task_id': task_id,
                'timestamp': datetime.now().isoformat()
            }

            if to_agent_id not in cls.internal_messages:
                cls.internal_messages[to_agent_id] = []

            cls.internal_messages[to_agent_id].append(msg_dict)
            print(f"[AgentRunner] 메시지 큐 추가: {from_agent} → {to_agent_id}")
            return True

    @classmethod
    def send_message_by_name(cls, to_agent_name: str, message: str, from_agent: str = "system",
                             task_id: str = None, project_id: str = None) -> bool:
        """
        에이전트 이름으로 메시지 전송 (비동기)

        Args:
            to_agent_name: 대상 에이전트 이름
            message: 전달할 메시지
            from_agent: 발신 에이전트 이름
            task_id: 연관된 태스크 ID
            project_id: 프로젝트 ID (지정하면 해당 프로젝트 내에서만 검색)

        Returns:
            성공 여부
        """
        target = cls.get_agent_by_name(to_agent_name, project_id=project_id)
        if not target:
            return False

        registry_key = getattr(target, 'registry_key', None)
        if not registry_key:
            return False

        return cls.send_message(registry_key, message, from_agent, task_id)
