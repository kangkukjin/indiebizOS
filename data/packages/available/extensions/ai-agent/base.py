"""
ai/base.py - AIAgent 기본 클래스
"""

import threading
import concurrent.futures

from tools import TOOLS

from .imports import DYNAMIC_TOOL_SELECTOR_AVAILABLE, get_base_tools
from .tool_executor import ToolExecutorMixin
from .providers import AnthropicMixin, OpenAIMixin, GoogleMixin, OllamaMixin


class AIAgent(ToolExecutorMixin, AnthropicMixin, OpenAIMixin, GoogleMixin, OllamaMixin):
    """AI 에이전트 (여러 제공자 지원)"""

    def __init__(self, ai_config: dict, system_prompt: str, agent_type: str = 'external', agent_name: str = None, agent_config: dict = None):
        self.provider = ai_config.get('provider', 'anthropic')
        self.api_key = ai_config.get('api_key')
        self.model = ai_config.get('model', 'claude-sonnet-4-20250514')
        self.system_prompt = system_prompt
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.client = None
        self.current_from_where = None
        self.cancel_event = threading.Event()

        # 에이전트별 도구 필터링
        self.tools = self._filter_tools()

        # 클라이언트 초기화
        self._init_client()

    def request_cancel(self):
        """작업 중단 요청"""
        self.cancel_event.set()
        print(f"[{self.agent_name}] 중단 요청됨")

    def reset_cancel(self):
        """중단 플래그 리셋"""
        self.cancel_event.clear()

    def _filter_tools(self) -> list:
        """에이전트별 도구 필터링 (기초 도구 + allowed_tools)"""
        # 기초 도구 목록 가져오기
        try:
            base_tool_names = get_base_tools() if DYNAMIC_TOOL_SELECTOR_AVAILABLE else []
        except:
            base_tool_names = []

        # allowed_tools 가져오기
        allowed_tools = None
        if self.agent_config:
            allowed_tools = self.agent_config.get('allowed_tools')

        # 기초 도구는 항상 포함
        filtered = [tool for tool in TOOLS if tool['name'] in base_tool_names]

        if allowed_tools is None:
            if self.agent_type == 'external':
                filtered = TOOLS
            else:
                filtered = [tool for tool in TOOLS if tool['name'] != 'send_email']
        else:
            for tool in TOOLS:
                if tool['name'] in allowed_tools and tool not in filtered:
                    filtered.append(tool)

        # 로그 출력
        if allowed_tools is not None:
            print(f"[도구 필터링] {self.agent_name}: 기초 {len(base_tool_names)}개 + 허용 {len(allowed_tools)}개 = {len(filtered)}개")
        else:
            print(f"[도구 필터링] {self.agent_name}: {len(filtered)}개 (제한 없음)")

        return filtered

    def _init_client(self):
        """AI 클라이언트 초기화"""
        if self.provider == 'anthropic':
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)

        elif self.provider == 'openai':
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("pip install openai")

        elif self.provider == 'google':
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError("pip install google-genai")

        elif self.provider == 'deepseek':
            try:
                import openai
                self.client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url="https://api.deepseek.com"
                )
            except ImportError:
                raise ImportError("pip install openai")

        elif self.provider == 'ollama':
            try:
                import ollama
                self.client = ollama
            except ImportError:
                raise ImportError("pip install ollama")

    def process_message_with_history(self, message_content: str, from_email: str, history: list, reply_to: str = None, timeout: int = 120, task_id: str = None, images: list = None) -> str:
        """대화 히스토리를 유지하며 메시지 처리 (GUI용)

        Args:
            timeout: AI 응답 대기 최대 시간 (초). 기본 120초.
            task_id: 현재 태스크 ID (스레드 간 전달용)
            images: 이미지 데이터 배열 [{base64, media_type}, ...]
        """
        self.reset_cancel()
        self.current_from_where = from_email
        self._last_called_agent = False

        def _do_process():
            if task_id:
                from tools import set_current_task_id, clear_called_agent
                set_current_task_id(task_id)
                clear_called_agent()

            try:
                if self.provider == 'anthropic':
                    response = self._process_anthropic_with_history(message_content, from_email, history, images)
                elif self.provider == 'openai':
                    response = self._process_openai_with_history(message_content, from_email, history, images)
                elif self.provider == 'google':
                    response = self._process_google_with_history(message_content, from_email, history, images)
                elif self.provider == 'deepseek':
                    response = self._process_deepseek_with_history(message_content, from_email, history, images)
                elif self.provider == 'ollama':
                    response = self._process_ollama_with_history(message_content, from_email, history, images)
                else:
                    response = self.process_message(message_content, from_email)

                from tools import did_call_agent
                self._last_called_agent = did_call_agent()
                return response
            finally:
                if task_id:
                    from tools import clear_current_task_id, clear_called_agent
                    clear_current_task_id()
                    clear_called_agent()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_process)

            try:
                while not future.done():
                    if self.cancel_event.is_set():
                        future.cancel()
                        print(f"[{self.agent_name}] 작업 중단됨")
                        return "⛔ 작업이 중단되었습니다."

                    try:
                        result = future.result(timeout=0.5)
                        return result
                    except concurrent.futures.TimeoutError:
                        continue

                return future.result()

            except concurrent.futures.TimeoutError:
                print(f"[{self.agent_name}] 응답 시간 초과 ({timeout}초)")
                return f"⏱️ 응답 시간이 초과되었습니다 ({timeout}초)."
            except Exception as e:
                print(f"[{self.agent_name}] 처리 오류: {e}")
                return f"오류가 발생했습니다: {str(e)}"
