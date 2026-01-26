"""
ai_agent.py - AI 에이전트 (도구 사용 지원)
IndieBiz OS Core

Anthropic, OpenAI, Google Gemini, Ollama를 지원하는 통합 AI 에이전트
- 도구(tool use) 지원
- 이미지 입력 지원
- 대화 히스토리 지원
- 스트리밍 응답 지원

모듈 구조:
- tool_loader.py: 도구 패키지 로딩/캐싱
- system_tools.py: 시스템 도구 정의/실행
- providers/: AI 프로바이더별 처리
"""

from typing import Optional, List, Dict, Generator, Any, Callable

# 모듈 임포트
from tool_loader import load_agent_tools, load_installed_tools
from system_tools import SYSTEM_TOOLS, execute_tool
from providers import get_provider


class AIAgent:
    """AI 에이전트 - 도구 사용 지원"""

    def __init__(
        self,
        ai_config: dict,
        system_prompt: str,
        agent_name: str = "에이전트",
        agent_id: str = None,
        project_path: str = ".",
        tools: List[Dict] = None,
        execute_tool_func: Callable = None
    ):
        self.config = ai_config
        self.system_prompt = system_prompt
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.project_path = project_path

        # 커스텀 도구 실행 함수 (시스템 AI 등에서 사용)
        self._custom_execute_tool = execute_tool_func

        # 시스템 도구 + 프로젝트 기본 도구 + 에이전트별 도구
        if tools is not None:
            self.tools = tools
        else:
            agent_tools = load_agent_tools(project_path, agent_id)
            self.tools = SYSTEM_TOOLS + agent_tools

        self.provider_name = ai_config.get("provider", "anthropic")
        self.model = ai_config.get("model", "claude-sonnet-4-20250514")
        self.api_key = ai_config.get("api_key", "")

        # 프로바이더 초기화
        self._provider = None
        self._init_provider()

    def _init_provider(self):
        """프로바이더 초기화"""
        try:
            self._provider = get_provider(
                self.provider_name,
                api_key=self.api_key,
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
                project_path=self.project_path,
                agent_name=self.agent_name,
                agent_id=self.agent_id
            )
            self._provider.init_client()
        except Exception as e:
            print(f"[AIAgent] 프로바이더 초기화 실패: {e}")
            self._provider = None

    @property
    def _client(self):
        """하위 호환성을 위한 client 속성"""
        return self._provider._client if self._provider else None

    def process_message_with_history(
        self,
        message_content: str,
        from_email: str = "",
        history: List[Dict] = None,
        reply_to: str = "",
        task_id: str = None,
        images: List[Dict] = None
    ) -> str:
        """
        메시지 처리 (히스토리 포함, 도구 사용 지원)

        Args:
            message_content: 사용자 메시지
            from_email: 발신자
            history: 대화 히스토리 [{"role": "user/assistant", "content": "..."}]
            reply_to: 답장 대상
            task_id: 태스크 ID
            images: 이미지 데이터 [{"base64": "...", "media_type": "image/png"}]

        Returns:
            AI 응답 텍스트
        """
        if not self._provider or not self._provider.is_ready:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

        history = history or []

        # 커스텀 execute_tool이 있으면 사용, 없으면 기본 execute_tool 사용
        tool_executor = self._custom_execute_tool if self._custom_execute_tool else execute_tool

        try:
            return self._provider.process_message(
                message=message_content,
                history=history,
                images=images,
                execute_tool=tool_executor
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"AI 응답 생성 실패: {str(e)}"

    def process_message_stream(
        self,
        message_content: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        스트리밍 메시지 처리

        Args:
            message_content: 사용자 메시지
            history: 대화 히스토리
            images: 이미지 데이터
            cancel_check: 중단 여부를 확인하는 콜백 함수

        Yields:
            스트리밍 이벤트 딕셔너리:
            - {"type": "text", "content": "..."} - 텍스트 청크
            - {"type": "tool_start", "name": "..."} - 도구 시작
            - {"type": "tool_result", "name": "...", "result": "..."} - 도구 결과
            - {"type": "thinking", "content": "..."} - AI 사고 과정
            - {"type": "final", "content": "..."} - 최종 응답
            - {"type": "error", "content": "..."} - 에러
        """
        if not self._provider or not self._provider.is_ready:
            yield {"type": "error", "content": "AI가 초기화되지 않았습니다."}
            return

        history = history or []

        # 커스텀 execute_tool이 있으면 사용, 없으면 기본 execute_tool 사용
        tool_executor = self._custom_execute_tool if self._custom_execute_tool else execute_tool

        # 프로바이더가 스트리밍을 지원하는지 확인
        if hasattr(self._provider, 'process_message_stream'):
            try:
                yield from self._provider.process_message_stream(
                    message=message_content,
                    history=history,
                    images=images,
                    execute_tool=tool_executor,
                    cancel_check=cancel_check
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield {"type": "error", "content": f"AI 응답 생성 실패: {str(e)}"}
        else:
            # 스트리밍 미지원 프로바이더는 일괄 응답
            try:
                response = self._provider.process_message(
                    message=message_content,
                    history=history,
                    images=images,
                    execute_tool=tool_executor
                )
                yield {"type": "final", "content": response}
            except Exception as e:
                yield {"type": "error", "content": f"AI 응답 생성 실패: {str(e)}"}


# ============ 하위 호환성을 위한 함수 export ============

# 기존 코드에서 직접 import하는 경우를 위해 re-export
from tool_loader import (
    load_agent_tools,
    load_installed_tools,
    load_tool_handler as _load_tool_handler,
    build_tool_package_map as _build_tool_package_map,
    get_all_tool_names,
)

from system_tools import (
    SYSTEM_TOOLS,
    execute_tool,
)
