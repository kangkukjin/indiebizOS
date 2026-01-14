"""
gemini.py - Google Gemini 프로바이더
IndieBiz OS Core
"""

import base64 as b64
from typing import List, Dict, Callable, Any
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini 프로바이더"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._genai_client = None
        self._genai_types = None

    def init_client(self) -> bool:
        """Gemini 클라이언트 초기화"""
        if not self.api_key:
            print(f"[GeminiProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            from google import genai
            from google.genai import types

            self._genai_client = genai.Client(api_key=self.api_key)
            self._genai_types = types
            self._client = self._genai_client
            print(f"[GeminiProvider] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[GeminiProvider] google-genai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[GeminiProvider] 초기화 실패: {e}")
            return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """Gemini로 메시지 처리"""
        if not self._genai_client:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

        history = history or []
        types = self._genai_types

        # 대화 히스토리 구성
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h["content"])]))

        # 현재 메시지 (이미지 포함 가능)
        current_parts = []
        if images:
            for img in images:
                img_bytes = b64.b64decode(img["base64"])
                current_parts.append(types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=img.get("media_type", "image/png")
                ))
        current_parts.append(types.Part.from_text(text=message))
        contents.append(types.Content(role="user", parts=current_parts))

        # 도구 설정
        gemini_tools = None
        if self.tools:
            gemini_tools = [types.Tool(function_declarations=self._convert_tools())]

        # 설정
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools
        )

        # 요청
        response = self._genai_client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config
        )

        return self._handle_response(response, contents, config, execute_tool)

    def _convert_tools(self) -> List:
        """도구를 Gemini 형식으로 변환"""
        types = self._genai_types
        gemini_functions = []

        for tool in self.tools:
            params = tool.get("input_schema", {"type": "object", "properties": {}})
            converted_params = self._convert_json_schema(params)

            gemini_functions.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=converted_params
                )
            )

        return gemini_functions

    def _convert_json_schema(self, schema: dict) -> Any:
        """JSON Schema를 Gemini Schema로 재귀 변환"""
        types = self._genai_types

        json_type = schema.get("type", "string")
        description = schema.get("description", "")

        type_map = {
            "string": types.Type.STRING,
            "number": types.Type.NUMBER,
            "integer": types.Type.INTEGER,
            "boolean": types.Type.BOOLEAN,
            "array": types.Type.ARRAY,
            "object": types.Type.OBJECT,
        }

        gemini_type = type_map.get(json_type, types.Type.STRING)

        # enum 처리
        if "enum" in schema:
            return types.Schema(
                type=types.Type.STRING,
                description=description,
                enum=schema["enum"]
            )

        # object 타입
        if json_type == "object":
            props = schema.get("properties", {})
            converted_props = {}
            for k, v in props.items():
                converted_props[k] = self._convert_json_schema(v)

            return types.Schema(
                type=types.Type.OBJECT,
                description=description,
                properties=converted_props,
                required=schema.get("required", [])
            )

        # array 타입
        if json_type == "array":
            items = schema.get("items", {"type": "string"})
            return types.Schema(
                type=types.Type.ARRAY,
                description=description,
                items=self._convert_json_schema(items)
            )

        # 기본 타입
        return types.Schema(
            type=gemini_type,
            description=description
        )

    def _handle_response(
        self,
        response,
        contents,
        config,
        execute_tool: Callable,
        depth: int = 0
    ) -> str:
        """응답 처리 (도구 사용 루프)"""
        types = self._genai_types

        if depth > 10:
            return "도구 사용 깊이 제한에 도달했습니다."

        # function_call 수집
        function_calls = []
        collected_text_parts = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        function_calls.append(part.function_call)
                    elif hasattr(part, 'text') and part.text:
                        collected_text_parts.append(part.text)

        # function_call 실행
        if function_calls:
            contents.append(response.candidates[0].content)

            function_response_parts = []
            approval_requested = False
            approval_message = ""

            for fc in function_calls:
                print(f"   [도구 사용] {fc.name}")

                if execute_tool:
                    tool_input = dict(fc.args) if fc.args else {}
                    tool_output = execute_tool(fc.name, tool_input, self.project_path)
                else:
                    tool_output = '{"error": "도구 실행 함수가 없습니다"}'

                # dict/list 결과를 JSON 문자열로 변환
                if isinstance(tool_output, (dict, list)):
                    import json
                    tool_output = json.dumps(tool_output, ensure_ascii=False)

                # 승인 요청 감지
                if tool_output.startswith("[[APPROVAL_REQUESTED]]"):
                    approval_requested = True
                    tool_output = tool_output.replace("[[APPROVAL_REQUESTED]]", "")
                    approval_message = tool_output

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": tool_output}
                    )
                )

            # 승인 요청이 있으면 루프 중단 - 사용자에게 바로 반환
            if approval_requested:
                existing_text = "\n".join(collected_text_parts) if collected_text_parts else ""
                if existing_text:
                    return existing_text + "\n\n" + approval_message
                return approval_message

            contents.append(types.Content(
                role="user",
                parts=function_response_parts
            ))

            # 후속 요청
            followup = self._genai_client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

            return self._handle_response(followup, contents, config, execute_tool, depth + 1)

        # 텍스트 추출
        try:
            return response.text
        except ValueError:
            result_text = ""
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        result_text += part.text
            return result_text if result_text else "요청을 처리했습니다."
