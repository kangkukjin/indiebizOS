"""
ai/providers/anthropic.py - Anthropic Claude 처리
"""


class AnthropicMixin:
    """Anthropic API 처리 믹스인"""

    def _process_anthropic_with_history(self, message_content: str, from_email: str, history: list, images: list = None) -> str:
        """Anthropic API로 히스토리 기반 처리 (tool_use/tool_result 완전 보존)"""
        # 내부 메시지인지 확인
        response_instruction = ""
        if "@indiebiz.local" in from_email:
            sender_name = from_email.split('@')[0]
            response_instruction = f"\n\n중요: 이것은 동료 에이전트 '{sender_name}'로부터 온 요청입니다. 작업을 완료한 후 결과를 직접 응답하세요. send_message_to_agent를 사용할 필요가 없습니다."

        # 현재 메시지 생성 (이미지 포함 가능)
        text_content = f"[현재 요청]\n발신자: {from_email}{response_instruction}\n\n내용:\n{message_content}"

        # 이미지가 있으면 멀티모달 형식으로 구성
        if images and len(images) > 0:
            text_content += f"\n\n[첨부된 이미지: {len(images)}개 - 사용자가 직접 첨부한 이미지입니다. 카메라로 추가 촬영할 필요 없이 이 이미지를 분석하세요.]"
            content_blocks = []
            # 이미지 블록 추가
            for img in images:
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/jpeg"),
                        "data": img.get("base64", "")
                    }
                })
            # 텍스트 블록 추가
            content_blocks.append({
                "type": "text",
                "text": text_content
            })
            current_message = {
                "role": "user",
                "content": content_blocks
            }
            print(f"   [AI] 이미지 {len(images)}개 포함된 메시지")
        else:
            current_message = {
                "role": "user",
                "content": text_content
            }

        # 원본 히스토리 길이 기록
        original_history_len = len(history)

        # 히스토리가 비어있으면 현재 메시지만
        if not history:
            messages = [current_message]
        else:
            if history[-1].get('content') == current_message['content']:
                messages = history.copy()
            else:
                messages = history.copy()
                messages.append(current_message)

        # Anthropic web_search 도구 추가
        anthropic_tools = self.tools + [{
            "type": "web_search_20250305",
            "name": "web_search"
        }]

        # system_prompt가 비어있으면 파라미터 자체를 생략
        if self.system_prompt:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.system_prompt,
                tools=anthropic_tools,
                messages=messages
            )
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                tools=anthropic_tools,
                messages=messages
            )

        # messages를 직접 업데이트하면서 처리
        final_text, updated_messages = self._handle_anthropic_response_with_history(
            response, messages, anthropic_tools
        )

        # 히스토리 업데이트
        new_messages = updated_messages[original_history_len:]
        history.extend(new_messages)

        return final_text

    def _handle_anthropic_response_with_history(self, response, messages, tools=None, depth=0):
        """
        Anthropic 응답 처리 (히스토리 완전 보존 버전)
        Returns: (final_text, updated_messages)
        """
        if tools is None:
            tools = self.tools + [{"type": "web_search_20250305", "name": "web_search"}]
        if depth > 20:
            return "처리 깊이 제한에 도달했습니다.", messages

        result_parts = []

        # 1. assistant 메시지 추가
        messages.append({
            "role": "assistant",
            "content": response.content
        })

        # 2. tool_use 처리
        tool_results = []
        for block in response.content:
            if block.type == "text":
                result_parts.append(block.text)
            elif block.type == "tool_use":
                tool_info = f"[도구 사용] {block.name}"
                print(tool_info)

                tool_output = self._execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output
                })

        # 3. tool_results가 있으면 followup
        if tool_results:
            messages.append({
                "role": "user",
                "content": tool_results
            })

            if self.system_prompt:
                followup = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=self.system_prompt,
                    tools=tools,
                    messages=messages
                )
            else:
                followup = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    tools=tools,
                    messages=messages
                )

            followup_text, messages = self._handle_anthropic_response_with_history(
                followup, messages, tools, depth + 1
            )
            result_parts.append(followup_text)

        final_text = "\n".join(result_parts)
        return final_text, messages
