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

    # V4 공식 1M 컨텍스트의 80% × 이 시스템 실측 2자/토큰 = 1.6M자.
    # 옛 205K자는 128K 모델 시절 값이라 정상 장기 작업을 너무 일찍 압축했다.
    COMPACTION_CHAR_THRESHOLD = 1_600_000

    # thinking 모드에서 tools를 실은 요청은 후속 assistant 턴의 reasoning_content를
    # 그대로 되돌려 보내야 한다(누락 시 DeepSeek API 400).
    preserve_reasoning_content = True

    # v4 하이브리드 thinking: 추론과 본문이 max_tokens 한 예산을 나눠 쓴다.
    # 4096이면 무거운 프롬프트에서 추론이 예산을 전부 태워 본문 0자(length)가
    # 난다(2026-08-09 실측: 입력 32.7K에 추론 4095/4096). 추론이 완주하고도
    # 본문을 쓸 공간이 남게 넉넉히 잡는다(16384 수용 실측).
    DEFAULT_MAX_TOKENS = 16384

    def _openai_compaction_ack(self):
        """모델이 만들지 않은 ACK에는 보존할 reasoning_content가 없으므로 넣지 않는다."""
        return None

    def _thinking_off_params(self):
        """v4 하이브리드 thinking 차단 — 2026-08-01 라이브 실측: 이 파라미터로
        reasoning_tokens가 0이 됨(enable_thinking/chat_template_kwargs는 무시됨).
        미지정 시 서버가 자체 판단으로 thinking에 빠져 원샷 호출(증류·분류)이
        max_tokens를 추론으로 전부 태울 수 있다(ep889: 증류 1건에 7콜 4.5분)."""
        return {"thinking": {"type": "disabled"}}

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
