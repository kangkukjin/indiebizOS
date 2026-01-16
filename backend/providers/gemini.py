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
        execute_tool: Callable = None,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Gemini로 메시지 처리 (스트리밍 모드)

        Args:
            cancel_check: 중단 여부를 확인하는 콜백 함수 (True 반환 시 중단)

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

        # 설정 (Gemini 3 권장: temperature=1.0으로 유지)
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=gemini_tools,
            temperature=1.0  # Gemini 3에서 변경 시 루프/성능 저하 발생 가능
        )

        yield from self._stream_response(contents, config, execute_tool, cancel_check=cancel_check)

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
        depth: int = 0,
        accumulated_text: str = "",
        cancel_check: Callable = None,
        consecutive_tool_only: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 응답 처리 (도구 사용 루프 포함)

        Args:
            accumulated_text: 이전 재귀 호출에서 누적된 텍스트 (final에 포함)
            cancel_check: 중단 여부를 확인하는 콜백 함수
            consecutive_tool_only: 텍스트 없이 도구만 연속 호출된 횟수
        """
        types = self._genai_types

        print(f"[Gemini] _stream_response 시작 (depth={depth}, accumulated_len={len(accumulated_text)})")

        # 중단 체크
        if cancel_check and cancel_check():
            print(f"[Gemini] 사용자 중단 요청 (depth={depth})")
            yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
            return

        if depth > 15:
            yield {"type": "error", "content": "도구 사용 깊이 제한(15)에 도달했습니다. 요청을 단순화해주세요."}
            return

        # 텍스트 없이 도구만 15번 연속 호출되면 강제 종료
        if consecutive_tool_only >= 15:
            print(f"[Gemini] 경고: 텍스트 없이 도구만 {consecutive_tool_only}번 연속 호출됨, 강제 종료")
            yield {"type": "error", "content": "도구만 연속으로 호출되어 응답을 중단합니다. 요청을 다시 시도해주세요."}
            return

        try:
            # 스트리밍 API 호출 (재시도 로직 포함)
            collected_text = ""
            function_calls = []
            response_content = None

            # 500 에러 재시도
            import time
            max_retries = 3
            stream = None
            last_error = None

            for attempt in range(max_retries):
                try:
                    stream = self._genai_client.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=config
                    )
                    break  # 성공하면 루프 탈출
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    if "500" in error_str or "INTERNAL" in error_str:
                        print(f"[Gemini] 500 에러, 재시도 {attempt + 1}/{max_retries}...")
                        time.sleep(1 * (attempt + 1))  # 점진적 대기
                        continue
                    else:
                        raise e

            if stream is None:
                raise last_error if last_error else Exception("스트림 생성 실패")

            # 전체 응답 parts 수집 (thought signature 보존을 위해)
            all_response_parts = []

            for chunk in stream:
                # 스트리밍 중 중단 체크
                if cancel_check and cancel_check():
                    print(f"[Gemini] 스트리밍 중 중단 (depth={depth})")
                    yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                    return
                if not hasattr(chunk, 'candidates') or not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not hasattr(candidate, 'content') or not candidate.content:
                    continue

                for part in candidate.content.parts:
                    # 모든 part 수집 (thought_signature 포함)
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

            # 전체 응답을 Content로 구성 (thought signature 보존)
            if all_response_parts:
                response_content = types.Content(role="model", parts=all_response_parts)
            else:
                response_content = None

            # 스트림 완료 후 상태 로깅
            print(f"[Gemini][depth={depth}] 스트림 완료:")
            print(f"[Gemini][depth={depth}]   생성된 텍스트: {len(collected_text)}자")
            if collected_text:
                text_preview = collected_text[:150].replace('\n', ' ')
                print(f"[Gemini][depth={depth}]   텍스트 미리보기: {text_preview}...")
            print(f"[Gemini][depth={depth}]   호출할 도구 수: {len(function_calls)}")
            if function_calls:
                tool_names = [fc.name for fc in function_calls]
                print(f"[Gemini][depth={depth}]   도구 목록: {tool_names}")

            # 도구 실행이 필요한 경우
            if function_calls:
                # assistant 응답 추가
                if response_content:
                    contents.append(response_content)

                function_response_parts = []
                approval_requested = False
                approval_message = ""

                for fc in function_calls:
                    # 도구 실행 전 중단 체크
                    if cancel_check and cancel_check():
                        print(f"[Gemini] 도구 실행 전 중단 (depth={depth})")
                        yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                        return

                    yield {
                        "type": "thinking",
                        "content": f"도구 실행 중: {fc.name}"
                    }

                    # 도구 실행
                    if execute_tool:
                        tool_input = dict(fc.args) if fc.args else {}
                        # 상세 로깅: 도구 입력값
                        import json as _json
                        input_preview = _json.dumps(tool_input, ensure_ascii=False)
                        if len(input_preview) > 200:
                            input_preview = input_preview[:200] + "..."
                        print(f"[Gemini][depth={depth}] 도구 호출: {fc.name}")
                        print(f"[Gemini][depth={depth}]   입력: {input_preview}")

                        try:
                            tool_output = execute_tool(fc.name, tool_input, self.project_path, self.agent_id)
                            # 상세 로깅: 도구 결과 요약
                            output_len = len(str(tool_output)) if tool_output else 0
                            output_preview = str(tool_output)[:200] + "..." if output_len > 200 else str(tool_output)
                            print(f"[Gemini][depth={depth}]   결과({output_len}자): {output_preview}")
                        except Exception as tool_err:
                            # 에러를 자연어로 전달 (Gemini가 더 잘 이해함)
                            tool_output = f"도구 실행 실패: {fc.name} - {str(tool_err)}. 다른 방법을 시도하거나 사용자에게 알려주세요."
                            print(f"[Gemini][depth={depth}] 도구 실행 예외: {fc.name} - {tool_err}")
                    else:
                        tool_output = "도구 실행 함수가 제공되지 않았습니다. 사용자에게 이 기능을 사용할 수 없음을 알려주세요."

                    # None 체크
                    if tool_output is None:
                        tool_output = "도구가 결과를 반환하지 않았습니다. 다른 방법을 시도해주세요."
                        print(f"[Gemini] 도구가 None 반환: {fc.name}")

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
                        "input": tool_input,
                        "result": tool_output[:3000] + "..." if len(tool_output) > 3000 else tool_output
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

                # 함수 응답 추가 (role="tool" - Gemini API 권장 방식)
                contents.append(types.Content(
                    role="tool",
                    parts=function_response_parts
                ))

                # 재귀 호출로 후속 응답 처리 (누적 텍스트 전달)
                total_accumulated = accumulated_text + collected_text
                # 텍스트 없이 도구만 호출된 경우 카운터 증가
                next_consecutive = 0 if collected_text.strip() else consecutive_tool_only + 1

                # 응답 강제 유도: consecutive가 10에 도달하면 응답 요청 메시지 추가
                if next_consecutive >= 10:
                    print(f"[Gemini] 응답 강제 유도 (consecutive_tool_only={next_consecutive})")
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            text="지금까지 수집한 정보를 바탕으로 사용자의 질문에 답변해주세요. 추가 도구 호출 없이 응답을 생성해주세요."
                        )]
                    ))

                print(f"[Gemini] 도구 실행 완료, 재귀 호출 (depth={depth} -> {depth+1}, accumulated_len={len(total_accumulated)}, consecutive_tool_only={next_consecutive})")
                yield from self._stream_response(contents, config, execute_tool, depth + 1, total_accumulated, cancel_check, next_consecutive)
            else:
                # 도구 사용 없이 완료 - 누적 텍스트 + 현재 텍스트
                final_result = accumulated_text + collected_text

                # 저장된 [MAP:...] 태그 추가
                if hasattr(self, '_pending_map_tags') and self._pending_map_tags:
                    final_result += "\n\n" + "\n".join(self._pending_map_tags)
                    self._pending_map_tags = []

                # 빈 응답인 경우 디버그 정보 추가
                if not final_result.strip():
                    print(f"[Gemini] 경고: 빈 응답 (depth={depth}, accumulated_len={len(accumulated_text)}, collected_len={len(collected_text)})")
                    # 빈 응답이면 AI가 뭔가 응답하도록 유도하는 메시지 추가
                    final_result = "(AI가 응답을 생성하지 않았습니다. 요청을 다시 시도하거나 더 구체적으로 질문해주세요.)"

                print(f"[Gemini] final 이벤트 yield (depth={depth}, len={len(final_result)})")
                yield {"type": "final", "content": final_result}

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_str = str(e)
            # 500 에러에 대한 친절한 메시지
            if "500" in error_str or "INTERNAL" in error_str:
                yield {"type": "error", "content": f"Gemini API 서버 오류가 발생했습니다 (500 INTERNAL). 잠시 후 다시 시도해주세요.\n\n상세: {error_str[:200]}"}
            else:
                yield {"type": "error", "content": f"API 호출 실패: {error_str}"}
