"""
anthropic.py - Anthropic Claude 프로바이더
IndieBiz OS Core
"""

from typing import List, Dict, Callable
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Claude 프로바이더"""

    def init_client(self) -> bool:
        """Anthropic 클라이언트 초기화"""
        if not self.api_key:
            print(f"[AnthropicProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
            print(f"[AnthropicProvider] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[AnthropicProvider] anthropic 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[AnthropicProvider] 초기화 실패: {e}")
            return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """Claude로 메시지 처리"""
        if not self._client:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

        history = history or []
        messages = []

        # 히스토리 변환
        for h in history:
            messages.append({
                "role": h["role"],
                "content": h["content"]
            })

        # 현재 메시지 (이미지 포함 가능)
        if images:
            content = []
            for img in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["base64"]
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        # API 호출
        if self.tools:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages
            )
        else:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                messages=messages
            )

        # 도구 사용 처리
        return self._handle_response(response, messages, execute_tool)

    def _handle_response(
        self,
        response,
        messages: List[Dict],
        execute_tool: Callable,
        depth: int = 0
    ) -> str:
        """응답 처리 (도구 사용 루프)"""
        if depth > 10:
            return "도구 사용 깊이 제한에 도달했습니다."

        result_parts = []
        tool_results = []

        for block in response.content:
            if block.type == "text":
                result_parts.append(block.text)
            elif block.type == "tool_use":
                print(f"   [도구 사용] {block.name}")

                # 도구 실행
                if execute_tool:
                    tool_output = execute_tool(block.name, block.input, self.project_path)
                else:
                    tool_output = '{"error": "도구 실행 함수가 없습니다"}'

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output
                })

        # 도구 결과가 있으면 후속 호출
        if tool_results:
            messages.append({
                "role": "assistant",
                "content": response.content
            })
            messages.append({
                "role": "user",
                "content": tool_results
            })

            # 후속 호출
            if self.tools:
                followup = self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    tools=self.tools,
                    messages=messages
                )
            else:
                followup = self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    messages=messages
                )

            followup_text = self._handle_response(followup, messages, execute_tool, depth + 1)
            result_parts.append(followup_text)

        return "\n".join(result_parts)
