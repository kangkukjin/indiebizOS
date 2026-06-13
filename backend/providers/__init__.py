"""
providers - AI 프로바이더 모듈
IndieBiz OS Core

지원 프로바이더:
- Anthropic (Claude)
- OpenAI (GPT)
- Google (Gemini)
- OpenRouter (650+ 모델, 무료 포함)
- Ollama (로컬 LLM)
- Claude Code (CLI subprocess, Max 플랜 사용)
"""

from .base import BaseProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider
from .ollama import OllamaProvider
from .claude_code import ClaudeCodeProvider
from .gemini_http import GeminiHTTPProvider  # SDK 없는 Gemini REST (폰 네이티브)

__all__ = [
    'BaseProvider',
    'AnthropicProvider',
    'OpenAIProvider',
    'GeminiProvider',
    'OpenRouterProvider',
    'OllamaProvider',
    'ClaudeCodeProvider',
    'GeminiHTTPProvider',
]


def get_provider(provider_name: str, **kwargs):
    """프로바이더 팩토리 함수"""
    providers = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'google': GeminiProvider,
        'gemini': GeminiProvider,
        'openrouter': OpenRouterProvider,
        'ollama': OllamaProvider,
        'claude_code': ClaudeCodeProvider,
        'claude-code': ClaudeCodeProvider,
        'claudecode': ClaudeCodeProvider,
        'gemini_http': GeminiHTTPProvider,
        'gemini-http': GeminiHTTPProvider,
        'google_http': GeminiHTTPProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"지원하지 않는 프로바이더: {provider_name}")

    return provider_class(**kwargs)
