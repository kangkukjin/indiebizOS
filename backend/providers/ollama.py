"""
ollama.py - Ollama 로컬 LLM 프로바이더
IndieBiz OS Core
"""

from typing import List, Dict, Callable
from .base import BaseProvider


class OllamaProvider(BaseProvider):
    """Ollama 로컬 LLM 프로바이더 (OpenAI 호환 API 사용)"""

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
        """Ollama로 메시지 처리"""
        if not self._client:
            return "AI가 초기화되지 않았습니다."

        history = history or []
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

        try:
            # Ollama는 도구(function calling) 지원이 제한적이므로 기본 채팅만 사용
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Ollama 응답 오류: {str(e)}"
