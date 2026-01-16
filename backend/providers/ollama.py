"""
ollama.py - Ollama 로컬 LLM 프로바이더 (스트리밍 지원)
IndieBiz OS Core
"""

from typing import List, Dict, Callable, Generator, Any
from .base import BaseProvider


class OllamaProvider(BaseProvider):
    """Ollama 로컬 LLM 프로바이더 (OpenAI 호환 API, 스트리밍 지원)"""

    def __init__(self, **kwargs):
        # Ollama는 API 키 불필요
        kwargs['api_key'] = kwargs.get('api_key', 'ollama')
        super().__init__(**kwargs)

    def init_client(self) -> bool:
        """Ollama 클라이언트 초기화 (OpenAI 호환)"""
        try:
            import openai
            self._client = openai.OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"
            )
            print(f"[OllamaProvider] {self.agent_name}: 초기화 완료 (모델: {self.model}, 도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[OllamaProvider] openai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[OllamaProvider] 초기화 실패: {e}")
            return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """Ollama로 메시지 처리 (동기 모드 - 기존 호환성 유지)"""
        if not self._client:
            return "AI가 초기화되지 않았습니다."

        # 스트리밍 제너레이터를 실행하고 최종 결과만 반환
        final_text = ""
        for event in self.process_message_stream(message, history, images, execute_tool):
            if event["type"] == "text":
                final_text += event["content"]
            elif event["type"] == "final":
                final_text = event["content"]

        return final_text

    def process_message_stream(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Ollama로 메시지 처리 (스트리밍 모드)

        Yields:
            {"type": "text", "content": "..."} - 텍스트 청크
            {"type": "final", "content": "..."} - 최종 응답
            {"type": "error", "content": "..."} - 에러
        """
        if not self._client:
            yield {"type": "error", "content": "AI가 초기화되지 않았습니다."}
            return

        history = history or []
        messages = self._build_messages(message, history, images)

        yield from self._stream_response(messages)

    def _build_messages(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List[Dict]:
        """메시지 목록 구성"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # 히스토리
        for h in history:
            messages.append({
                "role": h["role"],
                "content": h["content"]
            })

        # 현재 메시지 (이미지 지원 모델인 경우)
        if images:
            content = []
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        return messages

    def _stream_response(
        self,
        messages: List[Dict]
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 응답 처리"""
        try:
            collected_text = ""

            # 스트리밍 API 호출
            # Ollama는 도구(function calling) 지원이 제한적이므로 기본 채팅만 사용
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True
            )

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # 텍스트 청크
                if delta.content:
                    collected_text += delta.content
                    yield {"type": "text", "content": delta.content}

            # 최종 결과
            yield {"type": "final", "content": collected_text}

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"type": "error", "content": f"Ollama 응답 오류: {str(e)}"}
