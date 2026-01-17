"""
openai.py - OpenAI GPT 프로바이더 (스트리밍 지원)
IndieBiz OS Core

OpenAI 공식 베스트 프랙티스 기반 에이전틱 루프 구현:
- finish_reason 기반 도구 사용 판단 ("tool_calls", "stop", "length")
- 병렬 도구 호출 지원 (모든 tool_calls 동시 실행)
- length finish_reason 시 재시도
- role="tool" 형식으로 도구 결과 전달
- strict mode 지원 (스키마 검증)

참고:
- https://cookbook.openai.com/examples/how_to_call_functions_with_chat_models
- https://platform.openai.com/docs/guides/function-calling
"""

import json
import re
from typing import List, Dict, Callable, Generator, Any
from .base import BaseProvider

# 도구 결과 최대 길이 (컨텍스트 관리)
MAX_TOOL_RESULT_LENGTH = 8000

# 최대 도구 호출 깊이
MAX_TOOL_DEPTH = 15


class OpenAIProvider(BaseProvider):
    """OpenAI GPT 프로바이더 (스트리밍 지원)

    OpenAI 공식 에이전틱 루프 패턴 구현:
    1. 메시지 전송 → 응답 수신
    2. finish_reason 확인:
       - "stop": 완료
       - "tool_calls": 도구 실행 후 결과와 함께 재요청
       - "length": 더 큰 max_tokens로 재시도
    3. 도구 결과는 role="tool"로 전달
    """

    def init_client(self) -> bool:
        """OpenAI 클라이언트 초기화"""
        if not self.api_key:
            print(f"[OpenAIProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
            print(f"[OpenAIProvider] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
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
        """GPT로 메시지 처리 (동기 모드 - 기존 호환성 유지)"""
        if not self._client:
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
        GPT로 메시지 처리 (스트리밍 모드)

        Yields:
            {"type": "text", "content": "..."} - 텍스트 청크
            {"type": "tool_start", "name": "...", "input": {...}} - 도구 시작
            {"type": "tool_result", "name": "...", "result": "...", "is_error": bool} - 도구 결과
            {"type": "thinking", "content": "..."} - AI 사고 과정
            {"type": "final", "content": "..."} - 최종 응답
            {"type": "error", "content": "..."} - 에러
        """
        if not self._client:
            yield {"type": "error", "content": "AI가 초기화되지 않았습니다."}
            return

        history = history or []
        messages = self._build_messages(message, history, images)
        openai_tools = self._convert_tools()

        # 에이전틱 루프 실행
        yield from self._agentic_loop(messages, openai_tools, execute_tool)

    def _build_messages(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List[Dict]:
        """메시지 목록 구성"""
        messages = []

        # 시스템 프롬프트
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 히스토리
        for h in history:
            messages.append({
                "role": h["role"],
                "content": h["content"]
            })

        # 현재 메시지 (이미지 포함 가능) - 태그로 명확히 구분
        tagged_message = f"<current_user_request>\n{message}\n</current_user_request>"
        if images:
            content = []
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                    }
                })
            content.append({"type": "text", "text": tagged_message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": tagged_message})

        return messages

    def _convert_tools(self, strict: bool = False) -> List[Dict]:
        """도구를 OpenAI 형식으로 변환

        Args:
            strict: True면 strict mode 활성화 (스키마 검증)
        """
        if not self.tools:
            return []

        openai_tools = []
        for tool in self.tools:
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            }

            # strict mode 활성화 시 추가 설정
            if strict:
                tool_def["function"]["strict"] = True
                # strict mode에서는 additionalProperties: false 필요
                if "additionalProperties" not in tool_def["function"]["parameters"]:
                    tool_def["function"]["parameters"]["additionalProperties"] = False

            openai_tools.append(tool_def)

        return openai_tools

    def _truncate_tool_result(self, result: str, max_length: int = MAX_TOOL_RESULT_LENGTH) -> str:
        """도구 결과 길이 제한 (컨텍스트 관리)"""
        if len(result) <= max_length:
            return result

        # 앞뒤 일부를 유지하고 중간 생략
        keep_start = max_length * 2 // 3
        keep_end = max_length // 3 - 50
        return result[:keep_start] + f"\n\n... (중략: {len(result) - max_length}자 생략) ...\n\n" + result[-keep_end:]

    def _agentic_loop(
        self,
        messages: List[Dict],
        openai_tools: List[Dict],
        execute_tool: Callable,
        depth: int = 0,
        max_tokens: int = 4096
    ) -> Generator[Dict[str, Any], None, None]:
        """
        OpenAI 공식 에이전틱 루프 패턴

        finish_reason에 따른 처리:
        - "stop": 완료, 최종 응답 반환
        - "tool_calls": 도구 실행 후 결과와 함께 재귀 호출
        - "length": 더 큰 max_tokens로 재시도
        """
        if depth > MAX_TOOL_DEPTH:
            yield {"type": "error", "content": f"도구 사용 깊이 제한({MAX_TOOL_DEPTH})에 도달했습니다."}
            return

        try:
            # API 호출 파라미터 구성
            create_params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True
            }
            if openai_tools:
                create_params["tools"] = openai_tools

            collected_text = ""
            tool_calls = {}  # id -> {id, name, arguments}
            current_tool_id = None
            finish_reason = None

            # 스트리밍 응답 수신
            stream = self._client.chat.completions.create(**create_params)

            for chunk in stream:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # finish_reason 캡처
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                if not delta:
                    continue

                # 텍스트 청크
                if delta.content:
                    collected_text += delta.content
                    yield {"type": "text", "content": delta.content}

                # 도구 호출 청크
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.id:
                            current_tool_id = tc.id
                            tool_calls[current_tool_id] = {
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                            if tc.function and tc.function.name:
                                yield {
                                    "type": "tool_start",
                                    "name": tc.function.name,
                                    "input": {}
                                }
                        if tc.function and tc.function.arguments:
                            if current_tool_id and current_tool_id in tool_calls:
                                tool_calls[current_tool_id]["arguments"] += tc.function.arguments

            # finish_reason에 따른 처리 (OpenAI 공식 패턴)
            if finish_reason == "length":
                # length 초과 - 더 큰 값으로 재시도
                yield {"type": "thinking", "content": "응답이 길어 재시도 중..."}
                new_max_tokens = min(max_tokens * 2, 16384)
                if new_max_tokens > max_tokens:
                    yield from self._agentic_loop(messages, openai_tools, execute_tool, depth, new_max_tokens)
                else:
                    # 이미 최대치 - 현재까지의 결과 반환
                    yield {"type": "final", "content": collected_text + "\n\n(응답이 잘렸습니다)"}
                return

            elif finish_reason == "tool_calls" or tool_calls:
                # 도구 실행 필요
                yield from self._execute_tools_and_continue(
                    messages, collected_text, tool_calls, openai_tools, execute_tool, depth
                )
                return

            else:
                # stop 또는 기타 - 완료
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

    def _execute_tools_and_continue(
        self,
        messages: List[Dict],
        collected_text: str,
        tool_calls: Dict,
        openai_tools: List[Dict],
        execute_tool: Callable,
        depth: int
    ) -> Generator[Dict[str, Any], None, None]:
        """
        도구 실행 후 결과와 함께 에이전틱 루프 계속

        OpenAI 공식 패턴:
        - assistant 메시지에 tool_calls 포함
        - 각 tool_call에 대해 role="tool" 메시지로 결과 전달
        - tool_call_id로 매칭
        """
        # 1. assistant 메시지 구성 (tool_calls 포함)
        tool_calls_list = []
        for tc_id, tc_info in tool_calls.items():
            tool_calls_list.append({
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": tc_info["name"],
                    "arguments": tc_info["arguments"]
                }
            })

        assistant_message = {
            "role": "assistant",
            "content": collected_text if collected_text else None,
            "tool_calls": tool_calls_list
        }
        messages.append(assistant_message)

        # 2. 도구 실행 및 결과 메시지 추가
        approval_requested = False
        approval_message = ""

        for tc_id, tc_info in tool_calls.items():
            tool_name = tc_info["name"]
            yield {
                "type": "thinking",
                "content": f"도구 실행 중: {tool_name}"
            }

            # 도구 입력 파싱
            is_error = False
            try:
                tool_input = json.loads(tc_info["arguments"]) if tc_info["arguments"] else {}
            except json.JSONDecodeError:
                tool_input = {"_raw": tc_info["arguments"]}
                is_error = True

            # 도구 실행
            if execute_tool and not is_error:
                try:
                    tool_output = execute_tool(tool_name, tool_input, self.project_path, self.agent_id)
                except Exception as e:
                    tool_output = f"도구 실행 오류: {str(e)}"
                    is_error = True
            elif is_error:
                tool_output = f"도구 입력 파싱 오류: {tc_info['arguments']}"
            else:
                tool_output = '{"error": "도구 실행 함수가 없습니다"}'
                is_error = True

            # 승인 요청 감지
            if tool_output.startswith("[[APPROVAL_REQUESTED]]"):
                approval_requested = True
                tool_output = tool_output.replace("[[APPROVAL_REQUESTED]]", "")
                approval_message = tool_output

            # [MAP:...] 태그 추출 (최종 응답에 추가)
            map_match = re.search(r'\[MAP:(\{.*\})\]\s*$', tool_output, re.DOTALL)
            if map_match:
                if not hasattr(self, '_pending_map_tags'):
                    self._pending_map_tags = []
                self._pending_map_tags.append(map_match.group(0).strip())
                tool_output = tool_output[:map_match.start()].strip()

            # 도구 결과 길이 제한
            truncated_output = self._truncate_tool_result(tool_output)

            # 클라이언트에 도구 결과 전달
            yield {
                "type": "tool_result",
                "name": tool_name,
                "input": tool_input,
                "result": truncated_output[:3000] + "..." if len(truncated_output) > 3000 else truncated_output,
                "is_error": is_error
            }

            # 3. role="tool" 메시지 추가 (OpenAI 공식 형식)
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": truncated_output
            })

        # 승인 요청 시 루프 중단
        if approval_requested:
            final = collected_text + "\n\n" + approval_message if collected_text else approval_message
            yield {"type": "final", "content": final}
            return

        # 재귀 호출로 후속 응답 처리
        yield from self._agentic_loop(messages, openai_tools, execute_tool, depth + 1)
