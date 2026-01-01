"""
ai/providers/openai.py - OpenAI/DeepSeek 처리
"""

import json


class OpenAIMixin:
    """OpenAI API 처리 믹스인 (DeepSeek도 호환)"""

    def _process_openai_with_history(self, message_content: str, from_email: str, history: list, images: list = None) -> str:
        """OpenAI API로 히스토리 기반 처리 (tool_calls 완전 보존)"""
        response_instruction = ""
        if "@indiebiz.local" in from_email:
            sender_name = from_email.split('@')[0]
            response_instruction = f"\n\n중요: 이것은 동료 에이전트 '{sender_name}'로부터 온 요청입니다. 작업을 완료한 후 결과를 직접 응답하세요. send_message_to_agent를 사용할 필요가 없습니다."

        # 현재 메시지 생성 (이미지 포함 가능)
        text_content = f"[현재 요청]\n발신자: {from_email}{response_instruction}\n\n내용:\n{message_content}"

        # 이미지가 있으면 멀티모달 형식으로 구성 (OpenAI 형식)
        if images and len(images) > 0:
            text_content += f"\n\n[첨부된 이미지: {len(images)}개 - 사용자가 직접 첨부한 이미지입니다. 카메라로 추가 촬영할 필요 없이 이 이미지를 분석하세요.]"
            content_blocks = []
            content_blocks.append({
                "type": "text",
                "text": text_content
            })
            for img in images:
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/jpeg')};base64,{img.get('base64', '')}"
                    }
                })
            current_message = {
                "role": "user",
                "content": content_blocks
            }
            print(f"   [AI] 이미지 {len(images)}개 포함된 메시지 (OpenAI)")
        else:
            current_message = {
                "role": "user",
                "content": text_content
            }

        # system_prompt가 있으면 추가
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 히스토리를 그대로 복사
        for msg in history:
            if msg.get("role") and msg.get("content") is not None:
                messages.append(msg)

        if not history or history[-1].get('content') != current_message['content']:
            messages.append(current_message)

        openai_tools = self._convert_tools_to_openai()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools
        )

        final_text, updated_messages = self._handle_openai_response_with_history(
            response, messages
        )

        # 히스토리 업데이트
        original_len = len(history)
        new_messages = [m for m in updated_messages[1:] if m not in messages[:len(history)+1]]
        history.extend(new_messages)

        return final_text

    def _process_deepseek_with_history(self, message_content: str, from_email: str, history: list, images: list = None) -> str:
        """DeepSeek API로 히스토리 기반 처리 (OpenAI 호환)"""
        return self._process_openai_with_history(message_content, from_email, history, images)

    def _handle_openai_response_with_history(self, response, messages, depth=0):
        """
        OpenAI 응답 처리 (히스토리 완전 보존 버전)
        Returns: (final_text, updated_messages)
        """
        if depth > 20:
            return "처리 깊이 제한에 도달했습니다.", messages

        message = response.choices[0].message

        # assistant 메시지 추가
        messages.append(message.model_dump())

        if not message.tool_calls:
            return message.content or "", messages

        # 도구 결과 처리
        for tool_call in message.tool_calls:
            tool_input = json.loads(tool_call.function.arguments)
            tool_output = self._execute_tool(tool_call.function.name, tool_input)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_output
            })

        # followup API 호출
        followup = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._convert_tools_to_openai()
        )

        return self._handle_openai_response_with_history(followup, messages, depth + 1)

    def _convert_tools_to_openai(self) -> list:
        """Anthropic 도구를 OpenAI 형식으로 변환"""
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
