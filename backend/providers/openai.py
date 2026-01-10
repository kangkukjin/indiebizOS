"""
openai.py - OpenAI GPT 프로바이더
IndieBiz OS Core
"""

import json
from typing import List, Dict, Callable
from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI GPT 프로바이더"""

    def init_client(self) -> bool:
        """OpenAI 클라이언트 초기화"""
        if not self.api_key:
            print(f"[OpenAIProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
            print(f"[OpenAIProvider] {self.agent_name}: 초기화 완료")
            return True
        except ImportError:
            print("[OpenAIProvider] openai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[OpenAIProvider] 초기화 실패: {e}")
            return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """GPT로 메시지 처리"""
        if not self._client:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

        history = history or []
        messages = [{"role": "system", "content": self.system_prompt}]

        # 히스토리
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
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        # OpenAI 도구 형식 변환
        openai_tools = self._convert_tools()

        # API 호출
        if openai_tools:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools,
                max_tokens=4096
            )
        else:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096
            )

        return self._handle_response(response, messages, execute_tool)

    def _convert_tools(self) -> List[Dict]:
        """도구를 OpenAI 형식으로 변환"""
        if not self.tools:
            return []

        openai_tools = []
        for tool in self.tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            })
        return openai_tools

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

        message = response.choices[0].message

        # 도구 호출이 있는 경우
        if message.tool_calls:
            messages.append(message)

            for tool_call in message.tool_calls:
                print(f"   [도구 사용] {tool_call.function.name}")

                if execute_tool:
                    tool_input = json.loads(tool_call.function.arguments)
                    tool_output = execute_tool(tool_call.function.name, tool_input, self.project_path)
                else:
                    tool_output = '{"error": "도구 실행 함수가 없습니다"}'

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output
                })

            # 후속 호출
            openai_tools = self._convert_tools()
            if openai_tools:
                followup = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools,
                    max_tokens=4096
                )
            else:
                followup = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=4096
                )

            return self._handle_response(followup, messages, execute_tool, depth + 1)

        return message.content or ""
