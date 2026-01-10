"""
base.py - AI 프로바이더 기본 클래스
IndieBiz OS Core
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable


class BaseProvider(ABC):
    """AI 프로바이더 기본 클래스"""

    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        tools: List[Dict] = None,
        project_path: str = ".",
        agent_name: str = "에이전트"
    ):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.project_path = project_path
        self.agent_name = agent_name
        self._client = None

    @abstractmethod
    def init_client(self) -> bool:
        """클라이언트 초기화. 성공 시 True 반환"""
        pass

    @abstractmethod
    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """
        메시지 처리

        Args:
            message: 사용자 메시지
            history: 대화 히스토리 [{"role": "user/assistant", "content": "..."}]
            images: 이미지 데이터 [{"base64": "...", "media_type": "image/png"}]
            execute_tool: 도구 실행 함수

        Returns:
            AI 응답 텍스트
        """
        pass

    @property
    def is_ready(self) -> bool:
        """클라이언트 준비 상태"""
        return self._client is not None
