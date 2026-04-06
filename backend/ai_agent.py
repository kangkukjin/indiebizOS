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

import re
from typing import Optional, List, Dict, Generator, Any, Callable

# 모듈 임포트
from tool_loader import load_agent_tools, load_installed_tools
from system_tools import SYSTEM_TOOLS, execute_tool
from providers import get_provider

# 미완료 약속 감지 — 도구 호출 없이 "하겠습니다"만 하고 끝나는 응답 방지
FORCE_EXECUTE_PROMPT = "계획을 설명하지 말고 지금 바로 도구를 사용해서 작업을 실행하세요."

_PROMISE_PATTERNS = [
    "하겠습니다", "진행하겠습니다", "시작하겠습니다",
    "분석하겠습니다", "조사하겠습니다", "검색하겠습니다",
    "작성하겠습니다", "생성하겠습니다", "수행하겠습니다",
    "파고들겠습니다", "보고드리겠습니다", "제공하겠습니다",
    "진행 중", "수행 중", "작업 계획",
    "기다려 주", "잠시만 기다려",
]


def _is_unfulfilled_promise(text: str, had_tool_calls: bool = False) -> bool:
    """도구 호출 없이 실행을 약속만 하는 응답인지 감지

    Args:
        text: AI 응답 텍스트
        had_tool_calls: 이번 턴에서 도구 호출이 있었는지

    Returns:
        True이면 미완료 약속 (도구 없이 계획만 선언)
    """
    # 도구를 사용했으면 정상 응답
    if had_tool_calls:
        return False
    # 텍스트가 짧으면 약속이 아님
    if not text or len(text) < 50:
        return False
    # 약속 패턴이 2개 이상 매칭되면 미완료 약속으로 판단
    count = sum(1 for p in _PROMISE_PATTERNS if p in text)
    return count >= 2


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

        # 도구 실행 중 수집된 이미지 (턴 단위)
        self._last_tool_images = []

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

    def get_last_tool_images(self):
        """현재 턴에서 도구가 반환한 이미지 목록 반환 후 초기화"""
        images = self._last_tool_images
        self._last_tool_images = []
        return images if images else None

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
        미완료 약속 감지: 도구 호출 없이 "하겠습니다"만 하고 끝나면 자동으로 실행 유도

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
            self._last_tool_images = []  # 턴 시작 시 초기화
            response = self._provider.process_message(
                message=message_content,
                history=history,
                images=images,
                execute_tool=tool_executor
            )

            # 프로바이더에서 수집된 도구 이미지 가져오기
            if hasattr(self._provider, '_last_tool_images') and self._provider._last_tool_images:
                self._last_tool_images.extend(self._provider._last_tool_images)
                self._provider._last_tool_images = []

            # 미완료 약속 감지 → 실행 유도 (1회)
            if _is_unfulfilled_promise(response):
                print(f"[AIAgent] ⚡ 미완료 약속 감지, 실행 유도")
                retry_history = list(history) + [
                    {"role": "user", "content": message_content},
                    {"role": "assistant", "content": response}
                ]
                response = self._provider.process_message(
                    message=FORCE_EXECUTE_PROMPT,
                    history=retry_history,
                    images=None,
                    execute_tool=tool_executor
                )

            return response
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
        미완료 약속 감지: 도구 호출 없이 "하겠습니다"만 하고 끝나면 자동으로 실행 유도

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
                # 이벤트 수집 — final 이벤트는 미완료 약속 체크 후 전달
                had_tool_calls = False
                final_content = ""
                self._last_tool_images = []  # 턴 시작 시 초기화

                for event in self._provider.process_message_stream(
                    message=message_content,
                    history=history,
                    images=images,
                    execute_tool=tool_executor,
                    cancel_check=cancel_check
                ):
                    event_type = event.get("type", "")

                    if event_type in ("tool_start", "tool_result"):
                        had_tool_calls = True

                    # tool_result에서 이미지 수집
                    if event_type == "tool_result" and event.get("images"):
                        self._last_tool_images.extend(event["images"])

                    if event_type == "final":
                        final_content = event.get("content", "")
                        # final은 아직 전달하지 않음 — 미완료 약속 체크 후 결정
                        continue

                    yield event

                # 미완료 약속 감지 → 실행 유도 (1회)
                if _is_unfulfilled_promise(final_content, had_tool_calls):
                    print(f"[AIAgent] ⚡ 미완료 약속 감지 (스트리밍), 실행 유도")
                    yield {"type": "thinking", "content": "⚡ 실행 유도 — 계획이 아닌 실행을 시작합니다"}

                    retry_history = list(history) + [
                        {"role": "user", "content": message_content},
                        {"role": "assistant", "content": final_content}
                    ]

                    for event in self._provider.process_message_stream(
                        message=FORCE_EXECUTE_PROMPT,
                        history=retry_history,
                        images=None,
                        execute_tool=tool_executor,
                        cancel_check=cancel_check
                    ):
                        yield event
                else:
                    yield {"type": "final", "content": final_content}

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

                # 미완료 약속 감지 → 실행 유도 (1회)
                if _is_unfulfilled_promise(response):
                    print(f"[AIAgent] ⚡ 미완료 약속 감지 (일괄), 실행 유도")
                    retry_history = list(history) + [
                        {"role": "user", "content": message_content},
                        {"role": "assistant", "content": response}
                    ]
                    response = self._provider.process_message(
                        message=FORCE_EXECUTE_PROMPT,
                        history=retry_history,
                        images=None,
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
