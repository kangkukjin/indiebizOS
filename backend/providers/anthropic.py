"""
anthropic.py - Anthropic Claude 프로바이더 (스트리밍 지원)
IndieBiz OS Core
"""

import re
from typing import List, Dict, Callable, Generator, Any
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic Claude 프로바이더 (스트리밍 지원)"""

    def init_client(self) -> bool:
        """Anthropic 클라이언트 초기화"""
        if not self.api_key:
            print(f"[AnthropicProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
            print(f"[AnthropicProvider] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")
            return True
        except ImportError:
            print("[AnthropicProvider] anthropic 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[AnthropicProvider] 초기화 실패: {e}")
            return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """Claude로 메시지 처리 (동기 모드 - 기존 호환성 유지)"""
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
        Claude로 메시지 처리 (스트리밍 모드)

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

        # 스트리밍 응답 처리
        yield from self._stream_response(messages, execute_tool)

    def _build_messages(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List[Dict]:
        """메시지 목록 구성"""
        messages = []

        # 히스토리 변환
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
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["base64"]
                    }
                })
            content.append({"type": "text", "text": message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})

        return messages

    def _stream_response(
        self,
        messages: List[Dict],
        execute_tool: Callable,
        depth: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """스트리밍 응답 처리 (도구 사용 루프 포함)"""
        if depth > 10:
            yield {"type": "error", "content": "도구 사용 깊이 제한에 도달했습니다."}
            return

        # 스트리밍 API 호출
        try:
            create_params = {
                "model": self.model,
                "max_tokens": 4096,
                "system": self.system_prompt,
                "messages": messages,
                "stream": True
            }
            if self.tools:
                create_params["tools"] = self.tools

            collected_text = ""
            tool_uses = []
            current_tool = None
            current_tool_input = ""

            with self._client.messages.stream(**create_params) as stream:
                for event in stream:
                    event_type = event.type

                    if event_type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool = {
                                "id": block.id,
                                "name": block.name,
                                "input": {}
                            }
                            current_tool_input = ""
                            yield {
                                "type": "tool_start",
                                "name": block.name,
                                "input": {}
                            }

                    elif event_type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            text = delta.text
                            collected_text += text
                            yield {"type": "text", "content": text}
                        elif delta.type == "input_json_delta":
                            # 도구 입력 JSON 누적
                            current_tool_input += delta.partial_json

                    elif event_type == "content_block_stop":
                        if current_tool:
                            # 도구 입력 파싱
                            try:
                                import json
                                current_tool["input"] = json.loads(current_tool_input) if current_tool_input else {}
                            except:
                                current_tool["input"] = {}
                            tool_uses.append(current_tool)
                            current_tool = None
                            current_tool_input = ""

            # 도구 실행이 필요한 경우
            if tool_uses:
                tool_results = []
                approval_requested = False
                approval_message = ""

                for tool in tool_uses:
                    yield {
                        "type": "thinking",
                        "content": f"도구 실행 중: {tool['name']}"
                    }

                    # 도구 실행
                    if execute_tool:
                        tool_output = execute_tool(tool["name"], tool["input"], self.project_path, self.agent_id)
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
                        "name": tool["name"],
                        "result": tool_output[:500] + "..." if len(tool_output) > 500 else tool_output
                    }

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool["id"],
                        "content": tool_output
                    })

                # 승인 요청 시 루프 중단
                if approval_requested:
                    final = collected_text + "\n\n" + approval_message if collected_text else approval_message
                    yield {"type": "final", "content": final}
                    return

                # 메시지 히스토리 업데이트
                # assistant 응답 추가 (tool_use 블록 포함)
                assistant_content = []
                if collected_text:
                    assistant_content.append({"type": "text", "text": collected_text})
                for tool in tool_uses:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool["id"],
                        "name": tool["name"],
                        "input": tool["input"]
                    })

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

                # 재귀 호출로 후속 응답 처리
                yield from self._stream_response(messages, execute_tool, depth + 1)
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
