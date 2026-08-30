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

    return provider_class(**kwargs)


def clear_cli_sessions_for_agent(session_key: str):
    """'새 대화' — 이 키에 걸린 **모든** CLI 프로바이더 세션을 끊는다.

    호출부(UI 리셋 버튼·SESSION_RESET 분류)는 지금 어떤 프로바이더가 걸려 있는지 모른다.
    기어가 턴 사이에 바뀔 수도 있으므로 프로바이더를 물어보지 않고 전부 비운다 —
    없는 매핑은 no-op 이라 비용은 파일 읽기 몇 번뿐이다.
    ★새 CLI 프로바이더를 추가할 때 이 함수를 고칠 필요는 없다: CliSessionStore 를 만들면
    자동 등록된다(cli_provider._SESSION_STORES).
    """
    clear_sessions_for_agent(session_key)
