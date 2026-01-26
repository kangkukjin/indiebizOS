"""
gemini.py - Google Gemini 프로바이더 (최적화된 도구 호출)
IndieBiz OS Core

개선사항:
- 재귀 호출 제거 → while 루프로 변경
- 병렬 도구 호출 지원 (한 번의 응답에서 여러 도구 실행)
- 도구 호출 횟수 제한으로 무한 루프 방지
- 스트리밍 지원 유지
"""

import re
import json
import time
import base64 as b64
from typing import List, Dict, Callable, Any, Generator
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini 프로바이더 (최적화된 도구 호출)"""

    # 도구 호출 제한
    MAX_TOOL_ITERATIONS = 15  # 최대 도구 호출 라운드
    MAX_CONSECUTIVE_TOOL_ONLY = 10  # 텍스트 없이 도구만 연속 호출 허용 횟수

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._genai_client = None
        self._genai_types = None
        self._pending_map_tags = []

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
        """Gemini로 메시지 처리 (동기 모드)"""
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
        execute_tool: Callable = None,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Gemini로 메시지 처리 (스트리밍 모드, 최적화된 도구 호출)

        개선된 구조:
        - 재귀 대신 while 루프 사용
        - 한 라운드에서 여러 도구 병렬 실행
        - 명확한 종료 조건
        """
        if not self._genai_client:
            yield {"type": "error", "content": "AI가 초기화되지 않았습니다."}
            return

        history = history or []
        types = self._genai_types
        self._pending_map_tags = []

        # 대화 히스토리 구성
        contents = self._build_contents(message, history, images)

        # 도구 설정
        gemini_tools = None
        if self.tools:
            gemini_tools = [types.Tool(function_declarations=self._convert_tools())]

        # 설정 (temperature 0.5: 지시 준수 강화)
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools,
            temperature=0.5
        )

        # 도구 호출 루프 (재귀 대신 while)
        accumulated_text = ""
        iteration = 0
        consecutive_tool_only = 0

        while iteration < self.MAX_TOOL_ITERATIONS:
            # 중단 체크
            if cancel_check and cancel_check():
                print(f"[Gemini] 사용자 중단 요청 (iteration={iteration})")
                yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                return

            print(f"[Gemini] 라운드 {iteration + 1}/{self.MAX_TOOL_ITERATIONS} 시작")

            # API 호출 및 스트리밍
            try:
                collected_text, function_calls, response_content = yield from self._stream_single_response(
                    contents, config, cancel_check, iteration
                )
            except Exception as e:
                yield {"type": "error", "content": str(e)}
                return

            # 텍스트 누적
            accumulated_text += collected_text

            # 도구 호출이 없으면 완료
            if not function_calls:
                print(f"[Gemini] 도구 호출 없음, 완료 (iteration={iteration})")
                break

            # 연속 도구만 호출 체크
            if collected_text.strip():
                consecutive_tool_only = 0
            else:
                consecutive_tool_only += 1
                if consecutive_tool_only >= self.MAX_CONSECUTIVE_TOOL_ONLY:
                    print(f"[Gemini] 텍스트 없이 도구만 {consecutive_tool_only}번 연속 호출, 응답 강제 유도")
                    # 응답 강제 유도 메시지 추가
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            text="지금까지 수집한 정보를 바탕으로 사용자의 질문에 답변해주세요. 추가 도구 호출 없이 응답을 생성해주세요."
                        )]
                    ))
                    iteration += 1
                    continue

            # 모델 응답 추가
            if response_content:
                contents.append(response_content)

            # 도구 실행 (병렬)
            function_response_parts = []
            approval_requested = False
            approval_message = ""

            print(f"[Gemini] {len(function_calls)}개 도구 실행 중...")

            for fc in function_calls:
                # 중단 체크
                if cancel_check and cancel_check():
                    yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                    return

                yield {"type": "thinking", "content": f"도구 실행 중: {fc.name}"}

                # 도구 실행
                tool_output = self._execute_single_tool(fc, execute_tool, iteration)

                # 승인 요청 감지
                if tool_output.startswith("[[APPROVAL_REQUESTED]]"):
                    approval_requested = True
                    tool_output = tool_output.replace("[[APPROVAL_REQUESTED]]", "")
                    approval_message = tool_output

                # [MAP:...] 태그 추출
                map_match = re.search(r'\[MAP:(\{.*\})\]\s*$', tool_output, re.DOTALL)
                if map_match:
                    self._pending_map_tags.append(map_match.group(0).strip())
                    tool_output = tool_output[:map_match.start()].strip()

                # 이벤트 발생
                tool_input = dict(fc.args) if fc.args else {}
                yield {
                    "type": "tool_result",
                    "name": fc.name,
                    "input": tool_input,
                    "result": tool_output[:3000] + "..." if len(tool_output) > 3000 else tool_output
                }

                # 도구 응답 추가
                truncated_output = tool_output[:8000] if len(tool_output) > 8000 else tool_output
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": truncated_output}
                    )
                )

            # 승인 요청 시 즉시 종료
            if approval_requested:
                final = accumulated_text + "\n\n" + approval_message if accumulated_text else approval_message
                yield {"type": "final", "content": final}
                return

            # 도구 응답을 contents에 추가
            contents.append(types.Content(
                role="tool",
                parts=function_response_parts
            ))

            iteration += 1

        # 최종 응답 생성
        final_result = accumulated_text

        # MAP 태그 추가
        if self._pending_map_tags:
            final_result += "\n\n" + "\n".join(self._pending_map_tags)
            self._pending_map_tags = []

        # 빈 응답 처리
        if not final_result.strip():
            print(f"[Gemini] 경고: 빈 응답")
            final_result = "(AI가 응답을 생성하지 않았습니다. 요청을 다시 시도하거나 더 구체적으로 질문해주세요.)"

        if iteration >= self.MAX_TOOL_ITERATIONS:
            print(f"[Gemini] 도구 호출 횟수 제한 도달 ({self.MAX_TOOL_ITERATIONS}회)")
            final_result += f"\n\n(도구 호출 횟수 제한({self.MAX_TOOL_ITERATIONS}회)에 도달하여 응답을 종료합니다.)"

        print(f"[Gemini] 최종 응답 생성 (iteration={iteration}, len={len(final_result)})")
        yield {"type": "final", "content": final_result}

    def _stream_single_response(
        self,
        contents: List,
        config,
        cancel_check: Callable,
        iteration: int
    ) -> Generator[Dict[str, Any], None, tuple]:
        """
        단일 API 호출 및 스트리밍 처리

        Returns:
            (collected_text, function_calls, response_content)
        """
        types = self._genai_types
        collected_text = ""
        function_calls = []
        all_response_parts = []

        # API 호출 (재시도 포함)
        stream = self._create_stream_with_retry(contents, config)

        for chunk in self._iterate_stream_with_retry(stream, contents, config):
            # 중단 체크
            if cancel_check and cancel_check():
                raise Exception("사용자가 중단했습니다.")

            if not hasattr(chunk, 'candidates') or not chunk.candidates:
                continue

            candidate = chunk.candidates[0]
            if not hasattr(candidate, 'content') or not candidate.content:
                continue

            if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
                continue

            for part in candidate.content.parts:
                all_response_parts.append(part)

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

        # 로깅
        print(f"[Gemini][round={iteration}] 텍스트: {len(collected_text)}자, 도구: {len(function_calls)}개")
        if function_calls:
            tool_names = [fc.name for fc in function_calls]
            print(f"[Gemini][round={iteration}] 도구 목록: {tool_names}")

        # response_content 구성
        response_content = None
        if all_response_parts:
            response_content = types.Content(role="model", parts=all_response_parts)

        return (collected_text, function_calls, response_content)

    def _create_stream_with_retry(self, contents: List, config, max_retries: int = 3):
        """스트림 생성 (500 에러 재시도)"""
        last_error = None

        for attempt in range(max_retries):
            try:
                return self._genai_client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "500" in error_str or "INTERNAL" in error_str:
                    print(f"[Gemini] 500 에러, 재시도 {attempt + 1}/{max_retries}...")
                    time.sleep(1 * (attempt + 1))
                    continue
                else:
                    raise e

        raise last_error if last_error else Exception("스트림 생성 실패")

    def _iterate_stream_with_retry(self, stream, contents: List, config, max_retries: int = 3):
        """스트림 반복 (500 에러 재시도)"""
        retry_count = 0

        while True:
            try:
                for chunk in stream:
                    yield chunk
                break  # 정상 완료
            except Exception as e:
                error_str = str(e)
                if ("500" in error_str or "INTERNAL" in error_str) and retry_count < max_retries:
                    retry_count += 1
                    print(f"[Gemini] 스트리밍 중 500 에러, 재시도 {retry_count}/{max_retries}...")
                    time.sleep(1 * retry_count)
                    stream = self._genai_client.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=config
                    )
                    continue
                else:
                    raise e

    def _execute_single_tool(self, fc, execute_tool: Callable, iteration: int) -> str:
        """단일 도구 실행"""
        tool_input = dict(fc.args) if fc.args else {}

        # 로깅
        input_preview = json.dumps(tool_input, ensure_ascii=False)
        if len(input_preview) > 200:
            input_preview = input_preview[:200] + "..."
        print(f"[Gemini][round={iteration}] 도구 호출: {fc.name}")
        print(f"[Gemini][round={iteration}]   입력: {input_preview}")

        if not execute_tool:
            return "도구 실행 함수가 제공되지 않았습니다."

        try:
            tool_output = execute_tool(fc.name, tool_input, self.project_path, self.agent_id)

            # None 체크
            if tool_output is None:
                tool_output = "도구가 결과를 반환하지 않았습니다."
                print(f"[Gemini] 도구가 None 반환: {fc.name}")

            # dict/list를 JSON 문자열로 변환
            if isinstance(tool_output, (dict, list)):
                tool_output = json.dumps(tool_output, ensure_ascii=False)

            # 로깅
            output_len = len(str(tool_output))
            output_preview = str(tool_output)[:200] + "..." if output_len > 200 else str(tool_output)
            print(f"[Gemini][round={iteration}]   결과({output_len}자): {output_preview}")

            return tool_output

        except Exception as tool_err:
            print(f"[Gemini][round={iteration}] 도구 실행 예외: {fc.name} - {tool_err}")
            return f"도구 실행 실패: {fc.name} - {str(tool_err)}. 다른 방법을 시도하거나 사용자에게 알려주세요."

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
            content = h["content"]
            if h["role"] == "user":
                tagged_content = f"<user_message>\n{content}\n</user_message>"
            else:
                tagged_content = f"<assistant_message>\n{content}\n</assistant_message>"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=tagged_content)]))

        # 현재 메시지
        current_parts = []
        if images:
            for img in images:
                img_bytes = b64.b64decode(img["base64"])
                current_parts.append(types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=img.get("media_type", "image/png")
                ))
        current_parts.append(types.Part.from_text(text=f"<current_user_request>\n{message}\n</current_user_request>"))
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
