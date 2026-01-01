"""
ai/providers/google.py - Google Gemini 처리
"""


class GoogleMixin:
    """Google Gemini API 처리 믹스인"""

    def _convert_history_to_gemini(self, history: list) -> list:
        """우리 히스토리 형식을 Gemini 새 API 형식으로 변환"""
        from google.genai import types

        gemini_history = []

        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # role 매핑: assistant -> model
            gemini_role = "model" if role == "assistant" else role

            if gemini_role not in ["user", "model"]:
                continue

            parts = []

            if isinstance(content, str):
                parts.append(types.Part.from_text(text=content))

            elif isinstance(content, list):
                for block in content:
                    block_type = getattr(block, 'type', block.get('type', ''))

                    if block_type == 'text':
                        text = getattr(block, 'text', block.get('text', ''))
                        if text:
                            parts.append(types.Part.from_text(text=text))

                    elif block_type == 'tool_use':
                        tool_name = getattr(block, 'name', block.get('name', ''))
                        tool_input = getattr(block, 'input', block.get('input', {}))

                        parts.append(types.Part.from_function_call(
                            name=tool_name,
                            args=tool_input
                        ))

                    elif block_type == 'tool_result':
                        tool_use_id = block.get('tool_use_id', '')
                        result_content = block.get('content', '')

                        parts.append(types.Part.from_function_response(
                            name=tool_use_id,
                            response={"result": result_content}
                        ))

            if parts:
                gemini_history.append(types.Content(
                    role=gemini_role,
                    parts=parts
                ))

        return gemini_history

    def _process_google_with_history(self, message_content: str, from_email: str, history: list, images: list = None) -> str:
        """Google Gemini 새 API로 히스토리 기반 처리"""
        from google.genai import types
        import base64

        response_instruction = ""
        if "@indiebiz.local" in from_email:
            sender_name = from_email.split('@')[0]
            response_instruction = f"\n\n중요: 이것은 동료 에이전트 '{sender_name}'로부터 온 요청입니다. 작업을 완료한 후 결과를 직접 응답하세요. send_message_to_agent를 사용할 필요가 없습니다."

        text_content = f"[현재 요청]\n발신자: {from_email}{response_instruction}\n\n내용:\n{message_content}"

        # 이미지가 있으면 멀티파트 콘텐츠로 구성
        if images and len(images) > 0:
            text_content += f"\n\n[첨부된 이미지: {len(images)}개 - 사용자가 직접 첨부한 이미지입니다. 카메라로 추가 촬영할 필요 없이 이 이미지를 분석하세요.]"
            parts = []
            for img in images:
                parts.append(types.Part.from_bytes(
                    data=base64.b64decode(img.get("base64", "")),
                    mime_type=img.get("media_type", "image/jpeg")
                ))
            parts.append(types.Part.from_text(text=text_content))
            current_content = parts
            print(f"   [AI] 이미지 {len(images)}개 포함된 메시지 (Gemini)")
        else:
            current_content = text_content

        tool_declarations = self._convert_tools_to_google()

        system_instruction = self.system_prompt.strip()
        if not system_instruction:
            system_instruction = "당신은 사용자의 요청을 처리하는 AI 어시스턴트입니다."

        max_retries = 3

        for attempt in range(max_retries):
            try:
                gemini_history = []
                if history:
                    gemini_history = self._convert_history_to_gemini(history)
                    if gemini_history:
                        print(f"   [Gemini] {len(gemini_history)}개 히스토리 메시지 로드됨")

                chat = self.client.chats.create(
                    model=self.model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[types.Tool(function_declarations=tool_declarations)]
                    ),
                    history=gemini_history if gemini_history else None
                )

                response = chat.send_message(current_content)
                result = self._handle_google_response(response, chat)

                history.append({
                    "role": "user",
                    "content": current_content
                })

                history.append({
                    "role": "assistant",
                    "content": result
                })

                return result

            except Exception as e:
                error_msg = str(e)

                if "MALFORMED_FUNCTION_CALL" in error_msg:
                    print(f"   [Gemini] 도구 호출 실패 - 시도 {attempt + 1}/{max_retries}")

                    if attempt < max_retries - 1:
                        print(f"   [Gemini] 재시도 중...")
                        continue
                    else:
                        print(f"   [Gemini] 3번 모두 실패, 도구 없이 다시 시도")
                        try:
                            response_obj = self.client.models.generate_content(
                                model=self.model,
                                contents=current_content,
                                config=types.GenerateContentConfig(
                                    system_instruction=system_instruction + "\n\n중요: 도구를 사용하지 말고 직접 답변하세요."
                                )
                            )
                            result = response_obj.text

                            history.append({"role": "user", "content": current_content})
                            history.append({"role": "assistant", "content": result})

                            return result
                        except:
                            error_result = "도구 호출 오류가 발생했습니다. 질문을 다르게 표현해주세요."
                            history.append({"role": "user", "content": current_content})
                            history.append({"role": "assistant", "content": error_result})
                            return error_result
                else:
                    print(f"   [Gemini] 오류: {error_msg}")
                    error_result = f"오류가 발생했습니다: {error_msg}"

                    history.append({"role": "user", "content": current_content})
                    history.append({"role": "assistant", "content": error_result})

                    return error_result

        error_result = "도구 호출에 계속 실패했습니다."
        history.append({"role": "user", "content": current_content})
        history.append({"role": "assistant", "content": error_result})
        return error_result

    def _handle_google_response(self, response, chat, depth=0) -> str:
        """새 google-genai API용 응답 처리"""
        from google.genai import types

        if depth > 20:
            return "처리 깊이 제한에 도달했습니다."

        try:
            if not response.candidates or len(response.candidates) == 0:
                print(f"   [AI] 경고: Gemini가 응답 후보를 생성하지 못했습니다.")
                return "죄송합니다. 적절한 응답을 생성하지 못했습니다. 질문을 다시 표현해주시겠어요?"

            candidate = response.candidates[0]

            if not hasattr(candidate, 'content') or not candidate.content or not candidate.content.parts:
                finish_reason = getattr(candidate, 'finish_reason', 'UNKNOWN')
                print(f"   [AI] 경고: Gemini 응답이 비어있음 (finish_reason={finish_reason})")

                if str(finish_reason) == "STOP" or finish_reason == 1:
                    return ""
                elif str(finish_reason) == "MAX_TOKENS" or finish_reason == 3:
                    return "죄송합니다. 컨텍스트가 너무 길어서 응답을 생성하지 못했습니다."
                else:
                    return f"죄송합니다. 응답을 생성하는 중 문제가 발생했습니다 (finish_reason={finish_reason})."

            function_calls = []
            text_parts = []

            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)
                elif hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)

            if function_calls:
                function_responses = []
                for fc in function_calls:
                    args_dict = dict(fc.args) if hasattr(fc.args, 'items') else fc.args

                    tool_output = self._execute_tool(fc.name, args_dict)

                    function_responses.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": tool_output}
                        )
                    )

                followup = chat.send_message(function_responses)
                return self._handle_google_response(followup, chat, depth + 1)

            if text_parts:
                return "\n".join(text_parts)

            return response.text if hasattr(response, 'text') else ""

        except Exception as e:
            error_msg = str(e)
            if "MALFORMED_FUNCTION_CALL" in error_msg:
                print(f"   [AI] 경고: Gemini가 도구 호출 실패 (MALFORMED_FUNCTION_CALL)")
                print(f"   [AI] 대신 직접 답변으로 전환")
                try:
                    response_obj = self.client.models.generate_content(
                        model=self.model,
                        contents=chat.get_history()[-1].parts[0].text if chat.get_history() else "",
                        config=types.GenerateContentConfig(
                            system_instruction=self.system_prompt + "\n\n중요: 도구를 사용하지 말고 직접 답변하세요."
                        )
                    )
                    return response_obj.text
                except Exception as retry_error:
                    print(f"   [AI] Gemini 재시도 실패: {retry_error}")
                    return "도구 호출 오류가 발생했습니다. 질문을 다르게 표현해주세요."
            else:
                print(f"   [AI] Gemini 오류: {error_msg}")
                return f"오류가 발생했습니다: {error_msg}"

    def _convert_tools_to_google(self) -> list:
        """Anthropic 도구를 Google 새 API 형식으로 변환"""
        from google.genai import types

        declarations = []
        for tool in self.tools:
            schema = tool["input_schema"]

            func_decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=schema
            )
            declarations.append(func_decl)

        return declarations
