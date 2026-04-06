"""
openrouter.py - OpenRouter 프로바이더
IndieBiz OS Core

OpenRouter는 OpenAI 호환 API를 사용합니다.
650+ 모델(무료 포함)에 단일 API 키로 접근 가능.
OpenAI 프로바이더를 상속하여 base_url만 변경합니다.

참고: https://openrouter.ai/docs
"""

from .openai import OpenAIProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter 프로바이더 — OpenAI 호환 API

    OpenAI 프로바이더의 모든 기능(스트리밍, 도구 호출, 병렬 실행 등)을
    그대로 사용하며, base_url만 OpenRouter로 변경합니다.
    """

    def init_client(self) -> bool:
        """OpenRouter 클라이언트 초기화"""
        if not self.api_key:
            print(f"[OpenRouter] {self.agent_name}: API 키 없음")
            return False

        try:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=OPENROUTER_BASE_URL,
            )
            print(f"[OpenRouter] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[OpenRouter] openai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[OpenRouter] 초기화 실패: {e}")
            return False
