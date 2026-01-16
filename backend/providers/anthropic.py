"""
anthropic.py - Anthropic Claude 프로바이더 (스트리밍 지원 + 프롬프트 캐싱)
IndieBiz OS Core

Anthropic 공식 베스트 프랙티스 기반 에이전틱 루프 구현:
- stop_reason 기반 도구 사용 판단
- 병렬 도구 호출 지원 (단일 user 메시지에 모든 tool_result 포함)
- max_tokens 초과 시 재시도
- is_error 플래그를 통한 도구 에러 처리
- 프롬프트 캐싱 (5분 TTL, 최소 1024 토큰)

참고: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
"""

import json
import re
from typing import List, Dict, Callable, Generator, Any, Optional
from .base import BaseProvider

# 프롬프트 캐싱 최소 토큰 수 (Anthropic 제한: Sonnet/Opus는 1024)
MIN_CACHE_TOKENS = 1024

# 도구 결과 최대 길이 (컨텍스트 관리)
MAX_TOOL_RESULT_LENGTH = 8000

# 최대 도구 호출 깊이
MAX_TOOL_DEPTH = 15


class AnthropicProvider(BaseProvider):
    """Anthropic Claude 프로바이더 (스트리밍 지원)

    Anthropic 공식 에이전틱 루프 패턴 구현:
    1. 메시지 전송 → 응답 수신
    2. stop_reason 확인:
       - "end_turn": 완료
       - "tool_use": 도구 실행 후 결과와 함께 재요청
       - "max_tokens": 더 큰 max_tokens로 재시도
    3. 도구 결과는 단일 user 메시지에 모두 포함 (병렬 처리 지원)
    """

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

        # 스트리밍 응답 처리 (에이전틱 루프)
        yield from self._agentic_loop(messages, execute_tool)

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

    def _estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (대략 4자당 1토큰)"""
        return len(text) // 4

    def _build_system_with_cache(self) -> list | str:
        """시스템 프롬프트를 캐싱 가능한 형식으로 변환

        Returns:
            - 캐싱 가능: [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]
            - 캐싱 불가 (토큰 부족): 원본 문자열
        """
        if not self.system_prompt:
            return self.system_prompt

        estimated_tokens = self._estimate_tokens(self.system_prompt)

        if estimated_tokens >= MIN_CACHE_TOKENS:
            # 캐싱 적용
            return [
                {
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        else:
            # 토큰 수 부족 - 캐싱 미적용
            return self.system_prompt

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
        execute_tool: Callable,
        depth: int = 0,
        max_tokens: int = 4096
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Anthropic 공식 에이전틱 루프 패턴

        stop_reason에 따른 처리:
        - "end_turn": 완료, 최종 응답 반환
        - "tool_use": 도구 실행 후 결과와 함께 재귀 호출
        - "max_tokens": 더 큰 max_tokens로 재시도
        """
        if depth > MAX_TOOL_DEPTH:
            yield {"type": "error", "content": f"도구 사용 깊이 제한({MAX_TOOL_DEPTH})에 도달했습니다."}
            return

        try:
            # 시스템 프롬프트 캐싱 적용
            system_with_cache = self._build_system_with_cache()

            create_params = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system_with_cache,
                "messages": messages,
                "stream": True
            }
            if self.tools:
                create_params["tools"] = self.tools

            collected_text = ""
            tool_uses = []
            current_tool = None
            current_tool_input = ""
            stop_reason = None

            # 스트리밍 응답 수신
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
                                current_tool["input"] = json.loads(current_tool_input) if current_tool_input else {}
                            except json.JSONDecodeError:
                                current_tool["input"] = {"_raw": current_tool_input}
                            tool_uses.append(current_tool)
                            current_tool = None
                            current_tool_input = ""

                    elif event_type == "message_stop":
                        # 최종 메시지에서 stop_reason 추출
                        pass

                # 스트림 완료 후 최종 메시지 정보 가져오기
                final_message = stream.get_final_message()
                stop_reason = final_message.stop_reason

            # stop_reason에 따른 처리 (Anthropic 공식 패턴)
            if stop_reason == "max_tokens":
                # max_tokens 초과 - 더 큰 값으로 재시도
                yield {"type": "thinking", "content": "응답이 길어 재시도 중..."}
                new_max_tokens = min(max_tokens * 2, 8192)
                if new_max_tokens > max_tokens:
                    yield from self._agentic_loop(messages, execute_tool, depth, new_max_tokens)
                else:
                    # 이미 최대치 - 현재까지의 결과 반환
                    yield {"type": "final", "content": collected_text + "\n\n(응답이 잘렸습니다)"}
                return

            elif stop_reason == "tool_use" or tool_uses:
                # 도구 실행 필요
                yield from self._execute_tools_and_continue(
                    messages, collected_text, tool_uses, execute_tool, depth
                )
                return

            else:
                # end_turn 또는 기타 - 완료
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
        tool_uses: List[Dict],
        execute_tool: Callable,
        depth: int
    ) -> Generator[Dict[str, Any], None, None]:
        """
        도구 실행 후 결과와 함께 에이전틱 루프 계속

        Anthropic 공식 패턴:
        - 모든 도구 결과를 단일 user 메시지에 포함 (병렬 도구 지원)
        - tool_result가 content 배열의 첫 번째에 위치
        - is_error 플래그로 에러 상태 전달
        """
        tool_results = []
        approval_requested = False
        approval_message = ""

        # 모든 도구 실행 (병렬 도구 호출 대응)
        for tool in tool_uses:
            yield {
                "type": "thinking",
                "content": f"도구 실행 중: {tool['name']}"
            }

            # 도구 실행
            is_error = False
            if execute_tool:
                try:
                    tool_output = execute_tool(tool["name"], tool["input"], self.project_path, self.agent_id)
                except Exception as e:
                    tool_output = f"도구 실행 오류: {str(e)}"
                    is_error = True
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
                "name": tool["name"],
                "input": tool["input"],
                "result": truncated_output[:3000] + "..." if len(truncated_output) > 3000 else truncated_output,
                "is_error": is_error
            }

            # API에 보낼 tool_result 구성 (Anthropic 형식)
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": tool["id"],
                "content": truncated_output
            }
            if is_error:
                tool_result_block["is_error"] = True

            tool_results.append(tool_result_block)

        # 승인 요청 시 루프 중단
        if approval_requested:
            final = collected_text + "\n\n" + approval_message if collected_text else approval_message
            yield {"type": "final", "content": final}
            return

        # 메시지 히스토리 업데이트 (Anthropic 공식 형식)
        # 1. assistant 응답 추가 (text + tool_use 블록)
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

        # 2. user 메시지에 모든 tool_result 포함 (병렬 도구 지원의 핵심!)
        # 중요: tool_result가 content 배열의 첫 번째에 위치해야 함
        messages.append({"role": "user", "content": tool_results})

        # 재귀 호출로 후속 응답 처리
        yield from self._agentic_loop(messages, execute_tool, depth + 1)
