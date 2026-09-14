"""
providers - AI 프로바이더 모듈
IndieBiz OS Core

지원 프로바이더:
- Anthropic (Claude)
- OpenAI (GPT)
- Google (Gemini)
- OpenRouter (650+ 모델, 무료 포함)
- DeepSeek (V4 Pro/Flash, OpenAI 호환)
- Ollama (로컬 LLM)
- Claude Code (CLI subprocess, Max 플랜 사용)
- Codex (CLI subprocess, ChatGPT 구독 사용)

★아웃오브프로세스 CLI 프로바이더(claude_code·codex)의 몸통은 cli_provider 에 있다 —
세션 영속·신원 전파·스트림 오케스트레이션은 벤더 무관이라 거기서 공유한다.
"""

from .base import BaseProvider
from .cli_provider import CliSubprocessProvider, clear_sessions_for_agent
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider
from .deepseek import DeepSeekProvider
from .ollama import OllamaProvider
from .claude_code import ClaudeCodeProvider
from .codex import CodexProvider
from .gemini_http import GeminiHTTPProvider  # SDK 없는 Gemini REST (폰 네이티브)
from .deepseek_http import DeepSeekHTTPProvider  # SDK 없는 DeepSeek REST (폰 네이티브)

__all__ = [
    'BaseProvider',
    'get_provider',
    'create_initialized_provider',
    'CliSubprocessProvider',
    'AnthropicProvider',
    'OpenAIProvider',
    'GeminiProvider',
    'OpenRouterProvider',
    'DeepSeekProvider',
    'OllamaProvider',
    'ClaudeCodeProvider',
    'CodexProvider',
    'GeminiHTTPProvider',
    'DeepSeekHTTPProvider',
    'clear_cli_sessions_for_agent',
]


def get_provider(provider_name: str, **kwargs):
    """프로바이더 팩토리 함수"""
    providers = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'google': GeminiProvider,
        'gemini': GeminiProvider,
        'openrouter': OpenRouterProvider,
        'deepseek': DeepSeekProvider,
        'ollama': OllamaProvider,
        'claude_code': ClaudeCodeProvider,
        'claude-code': ClaudeCodeProvider,
        'claudecode': ClaudeCodeProvider,
        'codex': CodexProvider,
        'codex_cli': CodexProvider,
        'codex-cli': CodexProvider,
        'gemini_http': GeminiHTTPProvider,
        'gemini-http': GeminiHTTPProvider,
        'google_http': GeminiHTTPProvider,
        'deepseek_http': DeepSeekHTTPProvider,
        'deepseek-http': DeepSeekHTTPProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"지원하지 않는 프로바이더: {provider_name}")

    from member_runtime import is_member
    if is_member() and issubclass(provider_class, CliSubprocessProvider):
        raise PermissionError("회원 세션은 로컬 도구·영속 로그를 갖는 CLI 제공자를 사용할 수 없습니다. API 모델을 지정하세요.")
    return provider_class(**kwargs)


def create_initialized_provider(provider_name: str, *, isolated_session=False,
                                no_tools=False, disable_thinking=False, **kwargs):
    """새 제공자 생성·초기화와 호출 역할의 공통 옵션. 객체 캐시는 호출자가 소유한다.

    get_provider는 초기화 여부·시간을 직접 검사하는 온보딩 등의 원시 생성 계약으로
    유지한다. init_client의 False 반환은 종전처럼 is_ready로 관측하며 예외는 전파한다.
    """
    provider = get_provider(provider_name, **kwargs)
    provider.init_client()
    if isolated_session and hasattr(provider, "disable_session_persistence"):
        provider.disable_session_persistence = True
    if no_tools:
        provider.no_tools = True
    if disable_thinking:
        provider.disable_thinking = True
    return provider


def clear_cli_sessions_for_agent(session_key: str):
    """'새 대화' — 이 키에 걸린 **모든** CLI 프로바이더 세션을 끊는다.

    호출부(UI 리셋 버튼·SESSION_RESET 분류)는 지금 어떤 프로바이더가 걸려 있는지 모른다.
    기어가 턴 사이에 바뀔 수도 있으므로 프로바이더를 물어보지 않고 전부 비운다 —
    없는 매핑은 no-op 이라 비용은 파일 읽기 몇 번뿐이다.
    ★새 CLI 프로바이더를 추가할 때 이 함수를 고칠 필요는 없다: CliSessionStore 를 만들면
    자동 등록된다(cli_provider._SESSION_STORES).
    """
    clear_sessions_for_agent(session_key)
