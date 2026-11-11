"""EXAONE Chat Completions 어댑터. 스트리밍·도구 루프는 OpenAI 경로를 공유한다."""

from .openai import OpenAIProvider


class ExaoneProvider(OpenAIProvider):
    """K-EXAONE은 항상 추론하므로 원샷/off 요청도 low로 낮춰 전달한다."""

    CONTEXT_PROVIDER = "exaone"
    DEFAULT_MAX_TOKENS = 16384  # 추론과 답변이 출력 예산을 공유한다.
    preserve_reasoning_content = True

    def init_client(self) -> bool:
        if not self.api_key:
            print(f"[EXAONE] {self.agent_name}: API 키 없음")
            return False
        try:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key, base_url="https://api.exaone.ai/v1")
            return True
        except ImportError:
            print("[EXAONE] openai 라이브러리 없음")
            return False
        except Exception as exc:
            print(f"[EXAONE] 초기화 실패: {exc}")
            return False

    def _openai_compaction_ack(self):
        # 합성 ACK에는 모델이 만든 추론 이력이 없다.
        return None

    def _thinking_off_params(self):
        # enable_thinking=false는 지원하지 않는다. 비스트리밍 요약·최종 보고에도 적용.
        return {"reasoning_effort": "low", "temperature": 1.0, "top_p": 0.95,
                "chat_template_kwargs": {"preserve_thinking": True}}

    def _create_stream_with_retry(self, create_params):
        params = dict(create_params)
        params.setdefault("temperature", 1.0)
        params.setdefault("top_p", 0.95)
        params["extra_body"] = {
            "chat_template_kwargs": {"preserve_thinking": True},
            **params.get("extra_body", {}),
        }
        return super()._create_stream_with_retry(params)
