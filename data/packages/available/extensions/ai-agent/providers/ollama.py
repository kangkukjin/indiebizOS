"""
ai/providers/ollama.py - Ollama 처리
"""

import json
import traceback


class OllamaMixin:
    """Ollama API 처리 믹스인"""

    def _process_ollama_with_history(self, message_content: str, from_email: str, history: list, images: list = None) -> str:
        """Ollama로 히스토리 기반 처리 (도구 호출 지원)"""
        response_instruction = ""
        if "@indiebiz.local" in from_email:
            sender_name = from_email.split('@')[0]
            response_instruction = f"\n\n중요: 이것은 동료 에이전트 '{sender_name}'로부터 온 요청입니다. 작업을 완료한 후 결과를 직접 응답하세요."

        text_content = f"[현재 요청]\n발신자: {from_email}{response_instruction}\n\n내용:\n{message_content}"

        # 이미지가 있으면 Ollama 형식으로 구성
        if images and len(images) > 0:
            current_message = {
                "role": "user",
                "content": text_content,
                "images": [img.get("base64", "") for img in images]
            }
            print(f"   [AI] 이미지 {len(images)}개 포함된 메시지 (Ollama)")
        else:
            current_message = {
                "role": "user",
                "content": text_content
            }

        # 히스토리 구성 (Ollama 형식)
        messages = []

        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })

        for msg in history:
            if msg.get('role') in ['user', 'assistant']:
                content = msg.get('content', '')
                if isinstance(content, list):
                    text_content = []
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text_content.append(item.get('text', ''))
                    content = '\n'.join(text_content)

                if content:
                    messages.append({
                        "role": msg['role'],
                        "content": content
                    })

        messages.append(current_message)

        # 도구를 OpenAI 형식으로 변환
        ollama_tools = self._convert_tools_to_openai()

        max_iterations = 10
        full_response = ""

        try:
            for iteration in range(max_iterations):
                response = self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=ollama_tools if ollama_tools else None
                )

                assistant_message = response['message']
                messages.append(assistant_message)

                if 'tool_calls' not in assistant_message or not assistant_message['tool_calls']:
                    final_text = assistant_message.get('content', '')
                    if final_text:
                        full_response += final_text
                    break

                for tool_call in assistant_message['tool_calls']:
                    function = tool_call.get('function', {})
                    tool_name = function.get('name', '')
                    tool_args = function.get('arguments', {})

                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except:
                            tool_args = {}

                    print(f"[Ollama 도구 호출] {tool_name}")

                    tool_result = self._execute_tool(tool_name, tool_args)

                    messages.append({
                        "role": "tool",
                        "content": tool_result
                    })

            return full_response if full_response else "작업을 완료했습니다."

        except Exception as e:
            error_trace = traceback.format_exc()
            return f"[Ollama 오류] {str(e)}\n\n{error_trace}\n\nOllama 서버가 실행 중인지 확인하세요."

    def _convert_tools_to_openai(self) -> list:
        """Anthropic 도구를 OpenAI 형식으로 변환 (Ollama 호환)"""
        from tools import TOOLS
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
            }
            for tool in TOOLS
        ]
