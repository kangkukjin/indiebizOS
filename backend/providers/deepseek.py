"""
deepseek.py - DeepSeek 프로바이더
IndieBiz OS Core

DeepSeek는 OpenAI 호환 API를 사용합니다.
OpenAI 프로바이더를 상속하여 base_url만 변경합니다.

모델 (V4 세대, 2026-04):
- deepseek-v4-pro: 플래그십 1.6T MoE (활성 49B)
- deepseek-v4-flash: 경량 284B MoE (활성 13B)
둘 다 tool call·JSON·thinking/non-thinking 모드 지원.

참고: https://api-docs.deepseek.com
"""

from .openai import OpenAIProvider

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek 프로바이더 — OpenAI 호환 API

    OpenAI 프로바이더의 모든 기능(스트리밍, 도구 호출, 병렬 실행 등)을
    그대로 사용하며, base_url만 DeepSeek로 변경합니다.
    """

    def init_client(self) -> bool:
        """DeepSeek 클라이언트 초기화"""
        if not self.api_key:
            print(f"[DeepSeek] {self.agent_name}: API 키 없음")
            return False

        try:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=DEEPSEEK_BASE_URL,
            )
            print(f"[DeepSeek] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[DeepSeek] openai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[DeepSeek] 초기화 실패: {e}")
            return False
