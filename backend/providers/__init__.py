"""
providers - AI 프로바이더 모듈
IndieBiz OS Core

지원 프로바이더:
- Anthropic (Claude)
- OpenAI (GPT)
- Google (Gemini)
- Ollama (로컬 LLM)
"""

from .base import BaseProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider

__all__ = [
    'BaseProvider',
    'AnthropicProvider',
    'OpenAIProvider',
    'GeminiProvider',
    'OllamaProvider',
]


def get_provider(provider_name: str, **kwargs):
    """프로바이더 팩토리 함수"""
    providers = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'google': GeminiProvider,
        'gemini': GeminiProvider,
        'ollama': OllamaProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"지원하지 않는 프로바이더: {provider_name}")

    return provider_class(**kwargs)
