"""
anthropic.py - Anthropic Claude 프로바이더 (스트리밍 지원 + 프롬프트 캐싱)
IndieBiz OS Core

Anthropic 공식 베스트 프랙티스 기반 에이전틱 루프 구현:
- stop_reason 기반 도구 사용 판단
- 병렬 도구 호출 지원 (단일 user 메시지에 모든 tool_result 포함)
- max_tokens 초과 시 재시도
- is_error 플래그를 통한 도구 에러 처리
- 프롬프트 캐싱 (5분 TTL, 최소 1024 토큰)

개선 사항:
- 성능 메트릭 추적 (토큰 사용량, 지연시간)
- API 호출 재시도 로직 (rate limit, 5xx 에러)
- 빈 응답 복구 처리
- 도구 결과 검증

참고: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
"""

import json
import re
import time
from typing import List, Dict, Callable, Generator, Any, Optional
from .base import BaseProvider

# 프롬프트 캐싱 최소 토큰 수 (Anthropic 제한: Sonnet/Opus는 1024)
MIN_CACHE_TOKENS = 1024

# 도구 결과 최대 길이 (컨텍스트 관리)
MAX_TOOL_RESULT_LENGTH = 8000

# 최대 도구 호출 깊이
MAX_TOOL_DEPTH = 30


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
        execute_tool: Callable = None,
        cancel_check: Callable = None
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
        yield from self._agentic_loop(messages, execute_tool, cancel_check=cancel_check)

    def _build_messages(
        self,
        message: str,
        history: List[Dict],
        images: List[Dict] = None
    ) -> List[Dict]:
        """메시지 목록 구성"""
        messages = []

        # 히스토리 변환 (XML 태그로 구분)
        for h in history:
            role = h["role"]
            content = h["content"]
            if role == "user":
                tagged_content = f"<user_message>\n{content}\n</user_message>"
            else:
                tagged_content = f"<assistant_message>\n{content}\n</assistant_message>"
            messages.append({
                "role": role,
                "content": tagged_content
            })

        # 현재 메시지 (이미지 포함 가능) - 태그로 명확히 구분
        tagged_message = f"<current_user_request>\n{message}\n</current_user_request>"
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
            content.append({"type": "text", "text": tagged_message})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": tagged_message})

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
        max_tokens: int = 4096,
        empty_response_retries: int = 0,
        auto_continues: int = 0,
        accumulated_text: str = "",
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Anthropic 공식 에이전틱 루프 패턴

        stop_reason에 따른 처리:
        - "end_turn": 완료, 최종 응답 반환
        - "tool_use": 도구 실행 후 결과와 함께 재귀 호출
        - "max_tokens": 부분 응답을 이어붙이고 계속 (Auto-Continue)

        개선 사항:
        - 토큰 사용량 추적
        - API 재시도 로직
        - 빈 응답 복구 처리
        - Auto-Continue: max_tokens 초과 시 이어쓰기 (토큰 낭비 방지)
        """
        if depth > MAX_TOOL_DEPTH:
            yield {"type": "error", "content": f"도구 사용 깊이 제한({MAX_TOOL_DEPTH})에 도달했습니다."}
            return

        print(f"[Anthropic] 라운드 {depth + 1}/{MAX_TOOL_DEPTH} 시작")

        try:
            # 시스템 프롬프트 캐싱 적용
            system_with_cache = self._build_system_with_cache()

            # Session Pruning: 오래된 도구 결과 마스킹 (depth > 0일 때만)
            if depth > 0:
                messages = self._prune_messages_anthropic(messages)

            create_params = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system_with_cache,
                "messages": messages
            }
            if self.tools:
                create_params["tools"] = self.tools

            collected_text = ""
            tool_uses = []
            current_tool = None
            current_tool_input = ""
            stop_reason = None
            start_time = time.time()

            # 재시도 로직으로 스트림 생성
            stream = self._create_stream_with_retry(create_params)
            if stream is None:
                yield {"type": "error", "content": "API 호출 실패: 재시도 한도 초과"}
                return

            # 스트리밍 응답 수신
            with stream as event_stream:
                for event in event_stream:
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
                final_message = event_stream.get_final_message()
                stop_reason = final_message.stop_reason

                # 토큰 사용량 추적
                if hasattr(final_message, 'usage') and final_message.usage:
                    latency_ms = (time.time() - start_time) * 1000
                    input_tokens = getattr(final_message.usage, 'input_tokens', 0)
                    output_tokens = getattr(final_message.usage, 'output_tokens', 0)
                    self.metrics.record_request(latency_ms, input_tokens, output_tokens)
                    print(f"[Anthropic] 토큰: 입력={input_tokens}, 출력={output_tokens}, 지연={latency_ms:.0f}ms")

            # 빈 응답 복구 처리 (도구 결과 후 빈 응답인 경우)
            if not collected_text.strip() and not tool_uses and depth > 0 and empty_response_retries < 2:
                print(f"[Anthropic] 빈 응답 감지 (depth={depth}), 응답 강제 유도 (retry={empty_response_retries + 1})")
                messages.append({
                    "role": "user",
                    "content": "도구 실행 결과를 바탕으로 사용자에게 답변을 작성해주세요."
                })
                yield from self._agentic_loop(
                    messages, execute_tool, depth + 1, max_tokens, empty_response_retries + 1,
                    auto_continues=auto_continues, accumulated_text=accumulated_text,
                    cancel_check=cancel_check
                )
                return

            # stop_reason에 따른 처리 (Anthropic 공식 패턴 + Auto-Continue)
            if stop_reason == "max_tokens":
                if tool_uses:
                    # 도구 호출 JSON이 잘린 경우 → 기존 방식: max_tokens 늘려 재시도
                    yield {"type": "thinking", "content": "도구 호출이 잘려서 다시 시도 중..."}
                    new_max_tokens = min(max_tokens * 2, 8192)
                    if new_max_tokens > max_tokens:
                        yield from self._agentic_loop(
                            messages, execute_tool, depth, new_max_tokens,
                            auto_continues=auto_continues, accumulated_text=accumulated_text,
                            cancel_check=cancel_check
                        )
                    else:
                        final = accumulated_text + collected_text + "\n\n(응답이 잘렸습니다)"
                        yield {"type": "final", "content": final}
                    return

                # 텍스트만 잘린 경우 → Auto-Continue: 이어쓰기
                if auto_continues < self.MAX_AUTO_CONTINUES:
                    print(f"[Anthropic] Auto-Continue {auto_continues + 1}/{self.MAX_AUTO_CONTINUES} "
                          f"(depth={depth}, 잘린 텍스트 {len(collected_text)}자)")
                    yield {"type": "thinking", "content": f"응답 이어서 생성 중... ({auto_continues + 1}/{self.MAX_AUTO_CONTINUES})"}

                    # 부분 응답을 assistant 메시지로 추가
                    messages.append({"role": "assistant", "content": collected_text})
                    # 이어쓰기 요청
                    messages.append({"role": "user", "content": self.CONTINUATION_PROMPT})

                    new_accumulated = accumulated_text + collected_text
                    yield from self._agentic_loop(
                        messages, execute_tool, depth + 1, max_tokens,
                        auto_continues=auto_continues + 1,
                        accumulated_text=new_accumulated,
                        cancel_check=cancel_check
                    )
                else:
                    # Auto-Continue 한도 초과 → 현재까지 누적 텍스트 반환
                    final = accumulated_text + collected_text + "\n\n(응답이 최대 연속 길이에 도달했습니다)"
                    yield {"type": "final", "content": final}
                return

            elif stop_reason == "tool_use" or tool_uses:
                # 도구 실행 필요 - 중간 텍스트는 버리고 다음 루프로 진행
                # (Claude Desktop처럼 최종 응답만 final로 전달)
                yield from self._execute_tools_and_continue(
                    messages, collected_text, tool_uses, execute_tool, depth,
                    cancel_check=cancel_check
                )
                return

            else:
                # end_turn 또는 기타 - 완료 (누적 텍스트 + 이번 텍스트)
                final_result = accumulated_text + collected_text

                # 저장된 [MAP:...] 태그 추가
                if hasattr(self, '_pending_map_tags') and self._pending_map_tags:
                    final_result += "\n\n" + "\n".join(self._pending_map_tags)
                    self._pending_map_tags = []

                total_latency_ms = (time.time() - start_time) * 1000
                print(f"[Anthropic] 최종 응답 생성 (depth={depth}, len={len(final_result)}, latency={total_latency_ms:.0f}ms)")

                yield {"type": "final", "content": final_result}

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"type": "error", "content": f"API 호출 실패: {str(e)}"}

    def _create_stream_with_retry(self, create_params: Dict):
        """재시도 로직으로 스트림 생성

        Rate limit, 5xx 에러 시 exponential backoff로 재시도
        """
        last_error = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return self._client.messages.stream(**create_params)
            except Exception as e:
                last_error = e
                self.metrics.record_error()

                if attempt < self.retry_config.max_retries and self.retry_config.is_retryable(e):
                    delay = self.retry_config.get_delay(attempt)
                    self.metrics.record_retry()
                    print(f"[Anthropic] 재시도 {attempt + 1}/{self.retry_config.max_retries} "
                          f"({delay:.1f}s 후): {str(e)[:100]}")
                    import time
                    time.sleep(delay)
                else:
                    print(f"[Anthropic] API 에러 (재시도 불가): {str(e)[:200]}")
                    raise

        return None

    def _execute_tools_and_continue(
        self,
        messages: List[Dict],
        collected_text: str,
        tool_uses: List[Dict],
        execute_tool: Callable,
        depth: int,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        도구 실행 후 결과와 함께 에이전틱 루프 계속

        Anthropic 공식 패턴:
        - 모든 도구 결과를 단일 user 메시지에 포함 (병렬 도구 지원)
        - tool_result가 content 배열의 첫 번째에 위치
        - is_error 플래그로 에러 상태 전달

        pi-agent-core 영감:
        - cancel_check: 도구 실행 사이에 사용자 중단 확인 (steer 패턴)
        - content/details 분리: 도구가 dict 반환 시 AI용/UI용 결과 분리
        """
        tool_results = []
        approval_requested = False
        approval_message = ""
        cancelled = False

        # 모든 도구 실행 (병렬 도구 호출 대응)
        print(f"[Anthropic] {len(tool_uses)}개 도구 실행 중...")

        for tool in tool_uses:
            # [steer] 도구 실행 전 사용자 중단 확인
            if cancel_check and cancel_check():
                print(f"[Anthropic][depth={depth}] 사용자 중단 — 도구 '{tool['name']}' 스킵")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool["id"],
                    "content": "사용자가 작업을 중단했습니다.",
                    "is_error": True
                })
                cancelled = True
                continue

            # 도구 호출 로그
            input_preview = str(tool["input"])[:100] + "..." if len(str(tool["input"])) > 100 else str(tool["input"])
            print(f"[Anthropic][depth={depth}] 도구 호출: {tool['name']}")
            print(f"[Anthropic][depth={depth}]   입력: {input_preview}")

            yield {
                "type": "thinking",
                "content": f"도구 실행 중: {tool['name']}"
            }

            # 도구 실행
            is_error = False
            ui_details = None  # [content/details] UI용 상세 결과
            if execute_tool:
                try:
                    raw_output = execute_tool(tool["name"], tool["input"], self.project_path, self.agent_id)

                    # [content/details 분리] dict 반환 시 AI용과 UI용 분리
                    tool_images = None  # [images] 도구가 반환한 이미지 데이터
                    if isinstance(raw_output, dict) and "content" in raw_output:
                        tool_output = raw_output["content"]
                        ui_details = raw_output.get("details", tool_output)
                        tool_images = raw_output.get("images")  # [{base64, media_type}]
                    else:
                        tool_output = raw_output

                    # 도구 결과 검증
                    tool_output, is_error = self._verify_tool_result(tool["name"], tool["input"], tool_output)
                except Exception as e:
                    tool_output = f"도구 실행 오류: {str(e)}"
                    is_error = True
            else:
                tool_output = '{"error": "도구 실행 함수가 없습니다"}'
                is_error = True

            # 도구 호출 메트릭 기록
            self.metrics.record_tool_call()

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

            # 도구 결과 길이 제한 (AI에게 보내는 content)
            truncated_output = self._truncate_tool_result(tool_output)

            # 도구 결과 로그
            output_len = len(truncated_output)
            output_preview = truncated_output[:100] + "..." if output_len > 100 else truncated_output
            print(f"[Anthropic][depth={depth}]   결과({output_len}자): {output_preview}")

            # [content/details] 클라이언트(UI)에 보낼 결과 결정
            ui_result = ui_details if ui_details is not None else truncated_output
            if isinstance(ui_result, (dict, list)):
                import json as _json
                ui_result = _json.dumps(ui_result, ensure_ascii=False)
            ui_result_preview = ui_result[:3000] + "..." if len(str(ui_result)) > 3000 else ui_result

            # 클라이언트에 도구 결과 전달
            yield {
                "type": "tool_result",
                "name": tool["name"],
                "input": tool["input"],
                "result": ui_result_preview,
                "is_error": is_error
            }

            # API에 보낼 tool_result 구성 (Anthropic 형식) — AI에게는 content만
            # [images] 이미지가 있으면 멀티 콘텐츠 블록으로 구성
            if tool_images:
                tool_result_content = []
                for img in tool_images:
                    tool_result_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/png"),
                            "data": img["base64"]
                        }
                    })
                tool_result_content.append({"type": "text", "text": truncated_output})
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool["id"],
                    "content": tool_result_content
                }
            else:
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool["id"],
                    "content": truncated_output
                }
            if is_error:
                tool_result_block["is_error"] = True

            tool_results.append(tool_result_block)

        # [steer] 사용자 중단 시 루프 종료
        if cancelled:
            # 스킵된 도구 결과도 포함해서 AI에게 전달 (API 형식 유지)
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
            final = collected_text if collected_text else "사용자가 작업을 중단했습니다."
            yield {"type": "final", "content": final}
            return

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

        # 재귀 호출로 후속 응답 처리 (도구 실행 후에는 auto-continue 리셋)
        yield from self._agentic_loop(
            messages, execute_tool, depth + 1, max_tokens=4096,
            auto_continues=0, accumulated_text="",
            cancel_check=cancel_check
        )
