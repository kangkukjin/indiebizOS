"""
gemini.py - Google Gemini 프로바이더 (스트리밍 지원)
IndieBiz OS Core
"""

import re
import base64 as b64
from typing import List, Dict, Callable, Any, Generator
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini 프로바이더 (스트리밍 지원)"""

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
        """Gemini로 메시지 처리 (동기 모드 - 기존 호환성 유지)"""
        if not self._genai_client:
            return "AI가 초기화되지 않았습니다. API 키를 확인해주세요."

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
        Gemini로 메시지 처리 (스트리밍 모드)

        Yields:
            {"type": "text", "content": "..."} - 텍스트 청크
            {"type": "tool_start", "name": "...", "input": {...}} - 도구 시작
            {"type": "tool_result", "name": "...", "result": "..."} - 도구 결과
            {"type": "thinking", "content": "..."} - AI 사고 과정
            {"type": "final", "content": "..."} - 최종 응답
            {"type": "error", "content": "..."} - 에러
        """
        if not self._genai_client:
            yield {"type": "error", "content": "AI가 초기화되지 않았습니다."}
            return

        history = history or []
        types = self._genai_types

        # 대화 히스토리 구성
        contents = self._build_contents(message, history, images)

        # 도구 설정
        gemini_tools = None
        if self.tools:
            gemini_tools = [types.Tool(function_declarations=self._convert_tools())]

        # 설정
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools
        )

        yield from self._stream_response(contents, config, execute_tool)

    def _build_contents(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List:
        """대화 내용 구성"""
        types = self._genai_types
        contents = []

        # 히스토리 변환
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

        return contents

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

    def _stream_response(
        self,
        contents: List,
        config,
        execute_tool: Callable,
        depth: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 응답 처리 (도구 사용 루프 포함)"""
        types = self._genai_types

        if depth > 10:
            yield {"type": "error", "content": "도구 사용 깊이 제한에 도달했습니다."}
            return

        try:
            # 스트리밍 API 호출
            collected_text = ""
            function_calls = []
            response_content = None

            stream = self._genai_client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config
            )

            for chunk in stream:
                if not hasattr(chunk, 'candidates') or not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not hasattr(candidate, 'content') or not candidate.content:
                    continue

                # 마지막 response_content 저장 (도구 호출 시 필요)
                response_content = candidate.content

                for part in candidate.content.parts:
                    # 텍스트 청크
                    if hasattr(part, 'text') and part.text:
                        collected_text += part.text
                        yield {"type": "text", "content": part.text}

                    # Function call 감지
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        function_calls.append(fc)
                        yield {
                            "type": "tool_start",
                            "name": fc.name,
                            "input": dict(fc.args) if fc.args else {}
                        }

            # 도구 실행이 필요한 경우
            if function_calls:
                # assistant 응답 추가
                if response_content:
                    contents.append(response_content)

                function_response_parts = []
                approval_requested = False
                approval_message = ""

                for fc in function_calls:
                    yield {
                        "type": "thinking",
                        "content": f"도구 실행 중: {fc.name}"
                    }

                    # 도구 실행
                    if execute_tool:
                        tool_input = dict(fc.args) if fc.args else {}
                        tool_output = execute_tool(fc.name, tool_input, self.project_path, self.agent_id)
                    else:
                        tool_output = '{"error": "도구 실행 함수가 없습니다"}'

                    # dict/list 결과를 JSON 문자열로 변환
                    import json
                    if isinstance(tool_output, (dict, list)):
                        tool_output = json.dumps(tool_output, ensure_ascii=False)

                    # 승인 요청 감지
                    if tool_output.startswith("[[APPROVAL_REQUESTED]]"):
                        approval_requested = True
                        tool_output = tool_output.replace("[[APPROVAL_REQUESTED]]", "")
                        approval_message = tool_output

                    # [MAP:...] 태그 추출
                    map_match = re.search(r'\[MAP:(\{.*\})\]\s*$', tool_output, re.DOTALL)
                    if map_match:
                        if not hasattr(self, '_pending_map_tags'):
                            self._pending_map_tags = []
                        self._pending_map_tags.append(map_match.group(0).strip())
                        tool_output = tool_output[:map_match.start()].strip()

                    yield {
                        "type": "tool_result",
                        "name": fc.name,
                        "result": tool_output[:500] + "..." if len(tool_output) > 500 else tool_output
                    }

                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": tool_output}
                        )
                    )

                # 승인 요청 시 루프 중단
                if approval_requested:
                    final = collected_text + "\n\n" + approval_message if collected_text else approval_message
                    yield {"type": "final", "content": final}
                    return

                # 함수 응답 추가
                contents.append(types.Content(
                    role="user",
                    parts=function_response_parts
                ))

                # 재귀 호출로 후속 응답 처리
                yield from self._stream_response(contents, config, execute_tool, depth + 1)
            else:
                # 도구 사용 없이 완료
                final_result = collected_text

                # 저장된 [MAP:...] 태그 추가
                if hasattr(self, '_pending_map_tags') and self._pending_map_tags:
                    final_result += "\n\n" + "\n".join(self._pending_map_tags)
                    self._pending_map_tags = []

                yield {"type": "final", "content": final_result}

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"type": "error", "content": f"API 호출 실패: {str(e)}"}
