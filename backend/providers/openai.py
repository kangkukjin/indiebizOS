"""
openai.py - OpenAI GPT 프로바이더 (스트리밍 지원)
IndieBiz OS Core
"""

import json
import re
from typing import List, Dict, Callable, Generator, Any
from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI GPT 프로바이더 (스트리밍 지원)"""

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
            {"type": "tool_result", "name": "...", "result": "..."} - 도구 결과
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

        yield from self._stream_response(messages, openai_tools, execute_tool)

    def _build_messages(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List[Dict]:
        """메시지 목록 구성"""
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

        return messages

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

    def _stream_response(
        self,
        messages: List[Dict],
        openai_tools: List[Dict],
        execute_tool: Callable,
        depth: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 응답 처리 (도구 사용 루프 포함)"""
        if depth > 10:
            yield {"type": "error", "content": "도구 사용 깊이 제한에 도달했습니다."}
            return

        try:
            # 스트리밍 API 호출
            create_params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 4096,
                "stream": True
            }
            if openai_tools:
                create_params["tools"] = openai_tools

            collected_text = ""
            tool_calls = {}  # id -> {name, arguments}
            current_tool_id = None

            stream = self._client.chat.completions.create(**create_params)

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
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

            # 도구 실행이 필요한 경우
            if tool_calls:
                # assistant 메시지 구성
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
                    "content": collected_text or None,
                    "tool_calls": tool_calls_list
                }
                messages.append(assistant_message)

                tool_results = []
                approval_requested = False
                approval_message = ""

                for tc_id, tc_info in tool_calls.items():
                    tool_name = tc_info["name"]
                    yield {
                        "type": "thinking",
                        "content": f"도구 실행 중: {tool_name}"
                    }

                    # 도구 실행
                    if execute_tool:
                        try:
                            tool_input = json.loads(tc_info["arguments"]) if tc_info["arguments"] else {}
                        except:
                            tool_input = {}
                        tool_output = execute_tool(tool_name, tool_input, self.project_path, self.agent_id)
                    else:
                        tool_output = '{"error": "도구 실행 함수가 없습니다"}'

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
                        "name": tool_name,
                        "result": tool_output[:500] + "..." if len(tool_output) > 500 else tool_output
                    }

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": tool_output
                    })

                # 승인 요청 시 루프 중단
                if approval_requested:
                    final = collected_text + "\n\n" + approval_message if collected_text else approval_message
                    yield {"type": "final", "content": final}
                    return

                # 재귀 호출로 후속 응답 처리
                yield from self._stream_response(messages, openai_tools, execute_tool, depth + 1)
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
