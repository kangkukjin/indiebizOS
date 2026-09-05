"""
openai.py - OpenAI GPT 프로바이더 (스트리밍 지원)
IndieBiz OS Core

OpenAI 공식 베스트 프랙티스 기반 에이전틱 루프 구현:
- finish_reason 기반 도구 사용 판단 ("tool_calls", "stop", "length")
- 병렬 도구 호출 지원 (모든 tool_calls 동시 실행)
- length finish_reason 시 재시도
- role="tool" 형식으로 도구 결과 전달
- strict mode 지원 (스키마 검증)

개선 사항 (v2):
- 성능 메트릭 추적 (토큰 사용량, 지연시간)
- API 호출 재시도 로직 (rate limit, 5xx 에러)
- 빈 응답 복구 처리
- 도구 결과 검증

참고:
- https://cookbook.openai.com/examples/how_to_call_functions_with_chat_models
- https://platform.openai.com/docs/guides/function-calling
"""

import json
import re
import time
from typing import List, Dict, Callable, Generator, Any
from .base import BaseProvider, MAX_TOOL_ROUNDS

# 도구 결과 최대 길이 (컨텍스트 관리) — 파이프라인 시 액션 수 × 배수 적용
MAX_TOOL_RESULT_LENGTH = 16000

# 최대 도구 호출 깊이 — 전 프로바이더 공통값(base.MAX_TOOL_ROUNDS)
MAX_TOOL_DEPTH = MAX_TOOL_ROUNDS


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

    # GPT-4o/DeepSeek: 128K 토큰 컨텍스트 → 80% = 102K 토큰 → ~205,000자 (2자=1토큰 실측)
    COMPACTION_CHAR_THRESHOLD = 205000

    # 에이전틱 루프 기본 출력 예산. 하이브리드 thinking 모델(DeepSeek 등)은
    # 추론+본문이 이 예산을 나눠 쓰므로 해당 프로바이더가 오버라이드로 키운다.
    DEFAULT_MAX_TOKENS = 4096

    # DeepSeek처럼 thinking+tools 후속 요청에 reasoning_content를 요구하는 호환
    # 프로바이더만 켠다. OpenAI 본가 메시지에 미지원 필드를 보내지 않기 위한 방언 훅.
    preserve_reasoning_content = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._compaction_summary = None  # Rolling Compaction 요약 저장
        self._last_tool_images = []  # 도구 실행 중 수집된 이미지

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

    def _thinking_off_params(self) -> Dict[str, Any]:
        """disable_thinking=True일 때 요청 body에 합칠 프로바이더별 파라미터.

        OpenAI 본가는 하이브리드 thinking 기본 모델이 없어 no-op.
        DeepSeek 등 호환 API는 오버라이드로 자기 방언을 반환한다."""
        return {}

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
        execute_tool: Callable = None,
        cancel_check: Callable = None
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
        self._last_tool_images = []  # 턴 시작 시 초기화
        messages = self._build_messages(message, history, images)
        openai_tools = self._convert_tools()

        # cancel_check를 execute_tool에 전달하는 래퍼 (도구 실행 중 중단 지원)
        if cancel_check and execute_tool:
            _original_execute_tool = execute_tool
            def _cancellable_execute_tool(name, inp, path, aid=None):
                return _original_execute_tool(name, inp, path, aid, cancel_check=cancel_check)
            execute_tool = _cancellable_execute_tool

        # 에이전틱 루프 실행
        yield from self._agentic_loop(messages, openai_tools, execute_tool, cancel_check=cancel_check)

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

        # 히스토리 (XML 태그로 구분)
        for h in history:
            role = h["role"]
            content = h["content"]
            if role == "user":
                tagged_content = f"<user_message>\n{content}\n</user_message>"
            else:
                tagged_content = f"<assistant_message>\n{content}\n</assistant_message>"

            # 히스토리에 이미지가 있으면 멀티 콘텐츠로 구성
            if h.get("images"):
                multi_content = []
                for img in h["images"]:
                    multi_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                        }
                    })
                multi_content.append({"type": "text", "text": tagged_content})
                messages.append({"role": role, "content": multi_content})
            else:
                messages.append({"role": role, "content": tagged_content})

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
        """도구 결과 길이 제한 (컨텍스트 관리)
        파이프라인 결과인 경우 액션 수 × 기본 한도 적용 (개별 실행과 동등한 정보량 보장)
        """
        # 파이프라인 결과 감지: _action_count(병렬 포함 실제 액션 수)로 한도 확장
        import re as _re
        action_match = _re.search(r'"_action_count"\s*:\s*(\d+)', result)
        if action_match:
            actions = int(action_match.group(1))
            if actions > 1:
                max_length = max_length * actions

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
        max_tokens: int = None,
        empty_response_retries: int = 0,
        auto_continues: int = 0,
        accumulated_text: str = "",
        zero_output_retries: int = 0,
        force_thinking_off: bool = False,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        OpenAI 공식 에이전틱 루프 패턴

        finish_reason에 따른 처리:
        - "stop": 완료, 최종 응답 반환
        - "tool_calls": 도구 실행 후 결과와 함께 재귀 호출
        - "length": 부분 응답을 이어붙이고 계속 (Auto-Continue)

        개선 사항:
        - 토큰 사용량 추적
        - API 재시도 로직
        - 빈 응답 복구 처리
        - Auto-Continue: length 초과 시 이어쓰기 (토큰 낭비 방지)
        """
        if max_tokens is None:
            max_tokens = self.DEFAULT_MAX_TOKENS

        if depth > MAX_TOOL_DEPTH:
            # 에러로 폐기하지 않는다 — 도구를 뗀 마지막 턴으로 성과·잔여를 받아 착지.
            yield from self._final_turn(messages, max_tokens, MAX_TOOL_DEPTH)
            return

        self._notify_round(depth + 1, MAX_TOOL_DEPTH)

        try:
            # Rolling Compaction: 컨텍스트가 임계값을 넘으면 요약으로 압축
            if depth > 0 and self._should_compact(messages, depth):
                messages = self._compact_openai(messages)

            # Session Pruning: 오래된 도구 결과 마스킹 — ★압력이 있을 때만(최후 수단).
            # 위 compaction 이 이미 요약으로 크기를 낮췄다면 여기는 통과한다.
            if depth > 0 and self._should_prune(messages, depth):
                messages = self._prune_messages_openai(messages)

            # API 호출 파라미터 구성
            create_params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True}  # 토큰 사용량 포함
            }
            if openai_tools:
                create_params["tools"] = openai_tools

            # Reasoning (o1/o3 모델)
            if self.thinking_budget > 0 and self.reasoning_mode != "off":
                model_lower = self.model.lower()
                if "o1" in model_lower or "o3" in model_lower:
                    create_params["reasoning_effort"] = "medium"
                    # o1/o3는 max_tokens 대신 max_completion_tokens 사용
                    create_params.pop("max_tokens", None)
                    create_params["max_completion_tokens"] = max_tokens

            # 원샷 계약(분류·증류 등): 하이브리드 thinking 모델의 추론 모드 차단.
            # 파라미터는 프로바이더별(_thinking_off_params 오버라이드) — 기본은 no-op.
            # force_thinking_off: 추론이 max_tokens를 전부 태워 본문 0자가 났을 때의
            # 재시도 전용 — 이번 호출 한 번만 추론을 끄고 본문을 받아낸다.
            if self.disable_thinking or force_thinking_off or self.reasoning_mode == "off":
                _off = self._thinking_off_params()
                if _off:
                    create_params.setdefault("extra_body", {}).update(_off)

            collected_text = ""
            collected_reasoning = ""
            tool_calls = {}  # id -> {id, name, arguments}
            current_tool_id = None
            finish_reason = None
            usage_info = None
            start_time = time.time()

            # 재시도 로직으로 스트림 생성
            stream = self._create_stream_with_retry(create_params)
            if stream is None:
                yield {"type": "error", "content": "API 호출 실패: 재시도 한도 초과"}
                return

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

                # DeepSeek thinking 스트림의 방언 필드. OpenAI SDK 모델에 정식 필드가
                # 없어도 extra="allow"라 getattr로 읽을 수 있다. UI에는 노출하지 않고
                # 도구 루프의 다음 API 요청에 원문 그대로 되돌려 보내는 용도다.
                reasoning_chunk = getattr(delta, "reasoning_content", None)
                if reasoning_chunk:
                    collected_reasoning += reasoning_chunk

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

                # 토큰 사용량 (스트리밍 마지막 청크에 포함)
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info = chunk.usage

            # 토큰 사용량 추적
            latency_ms = (time.time() - start_time) * 1000
            # 추론 토큰 가시화 — "출력=4096인데 텍스트 0자" 부류(ep889)를 로그에서 즉시 판별
            _det = getattr(usage_info, 'completion_tokens_details', None) if usage_info else None
            _rt = getattr(_det, 'reasoning_tokens', 0) if _det else 0
            # 프리픽스 캐시 적중(DeepSeek prompt_cache_hit_tokens / OpenAI cached_tokens)은
            # base.normalize_usage 가 뽑는다 — 2026-09-02 계측: 이 값 없이는 캐시 적중을 모른다.
            self.metrics.record_usage(latency_ms, usage_info, label="OpenAI",
                                      extra=(f", 추론={_rt}" if _rt else ""))

            # thinking 소진 가드(ep889 부류): length인데 보이는 텍스트·도구 호출이 0
            # — 추론이 max_tokens를 전부 태운 경우. 이어쓰기(Auto-Continue)도 응답
            # 유도(빈 응답 복구)도 무의미하다(이어쓸 본문이 없음). 1회만 재시도 후 포기.
            if finish_reason == "length" and not collected_text.strip() and not tool_calls:
                if zero_output_retries < 1:
                    print(f"[OpenAI] 출력 0자 length 감지 (추론 토큰 소진 추정) — thinking 끄고 1회 재시도")
                    yield from self._agentic_loop(
                        messages, openai_tools, execute_tool, depth, max_tokens,
                        empty_response_retries=empty_response_retries,
                        auto_continues=auto_continues, accumulated_text=accumulated_text,
                        zero_output_retries=zero_output_retries + 1,
                        force_thinking_off=True,
                        cancel_check=cancel_check
                    )
                else:
                    print(f"[OpenAI] 출력 0자 length 재발 — 포기(누적 텍스트만 반환)")
                    yield {"type": "final", "content": accumulated_text}
                return

            # 빈 응답 복구 처리 (도구 결과 후 빈 응답인 경우)
            if not collected_text.strip() and not tool_calls and depth > 0 and empty_response_retries < 2:
                print(f"[OpenAI] 빈 응답 감지 (depth={depth}), 응답 강제 유도 (retry={empty_response_retries + 1})")
                messages.append({
                    "role": "user",
                    "content": "도구 실행 결과를 바탕으로 사용자에게 답변을 작성해주세요."
                })
                yield from self._agentic_loop(
                    messages, openai_tools, execute_tool, depth + 1, max_tokens,
                    empty_response_retries + 1,
                    auto_continues=auto_continues, accumulated_text=accumulated_text,
                    force_thinking_off=force_thinking_off,
                    cancel_check=cancel_check
                )
                return

            # finish_reason에 따른 처리 (OpenAI 공식 패턴 + Auto-Continue)
            if finish_reason == "length":
                if tool_calls:
                    # 도구 호출 JSON이 잘린 경우 → 기존 방식: max_tokens 늘려 재시도
                    yield {"type": "thinking", "content": "도구 호출이 잘려서 다시 시도 중..."}
                    new_max_tokens = min(max_tokens * 2, 16384)
                    if new_max_tokens > max_tokens:
                        yield from self._agentic_loop(
                            messages, openai_tools, execute_tool, depth, new_max_tokens,
                            auto_continues=auto_continues, accumulated_text=accumulated_text,
                            force_thinking_off=force_thinking_off,
                            cancel_check=cancel_check
                        )
                    else:
                        final = accumulated_text + collected_text + "\n\n(응답이 잘렸습니다)"
                        yield {"type": "final", "content": final}
                    return

                # 텍스트만 잘린 경우 → Auto-Continue: 이어쓰기
                if auto_continues < self.MAX_AUTO_CONTINUES:
                    print(f"[OpenAI] Auto-Continue {auto_continues + 1}/{self.MAX_AUTO_CONTINUES} "
                          f"(depth={depth}, 잘린 텍스트 {len(collected_text)}자)")
                    yield {"type": "thinking", "content": f"응답 이어서 생성 중... ({auto_continues + 1}/{self.MAX_AUTO_CONTINUES})"}

                    # 부분 응답을 assistant 메시지로 추가
                    partial_message = {"role": "assistant", "content": collected_text}
                    if self.preserve_reasoning_content and collected_reasoning:
                        partial_message["reasoning_content"] = collected_reasoning
                    messages.append(partial_message)
                    # 이어쓰기 요청
                    messages.append({"role": "user", "content": self.CONTINUATION_PROMPT})

                    new_accumulated = accumulated_text + collected_text
                    yield from self._agentic_loop(
                        messages, openai_tools, execute_tool, depth + 1, max_tokens,
                        auto_continues=auto_continues + 1,
                        accumulated_text=new_accumulated,
                        force_thinking_off=force_thinking_off,
                        cancel_check=cancel_check
                    )
                else:
                    # Auto-Continue 한도 초과 → 현재까지 누적 텍스트 반환
                    final = accumulated_text + collected_text + "\n\n(응답이 최대 연속 길이에 도달했습니다)"
                    yield {"type": "final", "content": final}
                return

            elif finish_reason == "tool_calls" or tool_calls:
                # 도구 실행 필요
                yield from self._execute_tools_and_continue(
                    messages, collected_text, collected_reasoning, tool_calls,
                    openai_tools, execute_tool, depth,
                    force_thinking_off=force_thinking_off,
                    cancel_check=cancel_check
                )
                return

            else:
                # stop 또는 기타 - 완료 (누적 텍스트 + 이번 텍스트)
                final_result = accumulated_text + collected_text

                # 저장된 [MAP:...] 태그 추가
                if hasattr(self, '_pending_map_tags') and self._pending_map_tags:
                    final_result += "\n\n" + "\n".join(self._pending_map_tags)
                    self._pending_map_tags = []

                yield {"type": "final", "content": final_result}

        except Exception as e:
            # DeepSeek의 thinking+tools 이력 규약이 다시 바뀌거나 옛 이력에 추론 필드가
            # 없어도 긴 작업을 통째로 버리지 않는다. 정식 수리는 위의 원문 보존이고,
            # 이것은 정확히 그 400에만 발동해 남은 도구 루프를 non-thinking으로 마친다.
            if (self.preserve_reasoning_content and not force_thinking_off
                    and "reasoning_content" in str(e)
                    and "passed back" in str(e)):
                print("[DeepSeek] reasoning_content 400 — thinking을 끄고 1회 복구")
                yield from self._agentic_loop(
                    messages, openai_tools, execute_tool, depth, max_tokens,
                    empty_response_retries=empty_response_retries,
                    auto_continues=auto_continues,
                    accumulated_text=accumulated_text,
                    zero_output_retries=zero_output_retries,
                    force_thinking_off=True,
                    cancel_check=cancel_check,
                )
                return
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
                return self._client.chat.completions.create(**create_params)
            except Exception as e:
                last_error = e
                self.metrics.record_error()

                if attempt < self.retry_config.max_retries and self.retry_config.is_retryable(e):
                    delay = self.retry_config.get_delay(attempt)
                    self.metrics.record_retry()
                    print(f"[OpenAI] 재시도 {attempt + 1}/{self.retry_config.max_retries} "
                          f"({delay:.1f}s 후): {str(e)[:100]}")
                    time.sleep(delay)
                else:
                    print(f"[OpenAI] API 에러 (재시도 불가): {str(e)[:200]}")
                    raise

        return None

    def _execute_tools_and_continue(
        self,
        messages: List[Dict],
        collected_text: str,
        collected_reasoning: str,
        tool_calls: Dict,
        openai_tools: List[Dict],
        execute_tool: Callable,
        depth: int,
        force_thinking_off: bool = False,
        cancel_check: Callable = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        도구 실행 후 결과와 함께 에이전틱 루프 계속

        OpenAI 공식 패턴:
        - assistant 메시지에 tool_calls 포함
        - 각 tool_call에 대해 role="tool" 메시지로 결과 전달
        - tool_call_id로 매칭

        pi-agent-core 영감:
        - cancel_check: 도구 실행 사이에 사용자 중단 확인 (steer 패턴)
        - content/details 분리: 도구가 dict 반환 시 AI용/UI용 결과 분리
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
        if self.preserve_reasoning_content and collected_reasoning:
            assistant_message["reasoning_content"] = collected_reasoning
        messages.append(assistant_message)

        # 2. 도구 실행 및 결과 메시지 추가
        approval_requested = False
        approval_message = ""
        cancelled = False

        for tc_id, tc_info in tool_calls.items():
            tool_name = tc_info["name"]

            # [steer] 도구 실행 전 사용자 중단 확인
            if cancel_check and cancel_check():
                print(f"[OpenAI][depth={depth}] 사용자 중단 — 도구 '{tool_name}' 스킵")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": "사용자가 작업을 중단했습니다."
                })
                cancelled = True
                continue

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
            ui_details = None  # [content/details] UI용 상세 결과
            if execute_tool and not is_error:
                try:
                    raw_output = execute_tool(tool_name, tool_input, self.project_path, self.agent_id)

                    # [content/details 분리] dict 반환 시 AI용과 UI용 분리
                    tool_images = None  # [images] 도구가 반환한 이미지 데이터
                    if isinstance(raw_output, dict) and "content" in raw_output:
                        tool_output = raw_output["content"]
                        ui_details = raw_output.get("details", tool_output)
                        tool_images = raw_output.get("images")  # [{base64, media_type}]
                    else:
                        tool_output = raw_output

                    # 도구 결과 검증
                    tool_output, is_error = self._verify_tool_result(tool_name, tool_input, tool_output)
                except Exception as e:
                    tool_output = f"도구 실행 오류: {str(e)}"
                    is_error = True
            elif is_error:
                tool_output = f"도구 입력 파싱 오류: {tc_info['arguments']}"
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

            # [content/details] 클라이언트(UI)에 보낼 결과 결정
            ui_result = ui_details if ui_details is not None else truncated_output
            if isinstance(ui_result, (dict, list)):
                ui_result = json.dumps(ui_result, ensure_ascii=False)
            ui_result_preview = str(ui_result)[:3000] + "..." if len(str(ui_result)) > 3000 else ui_result

            # 도구 이미지 수집 (다음 턴 히스토리용)
            if tool_images:
                self._last_tool_images.extend(tool_images)

            # 클라이언트에 도구 결과 전달
            tool_result_event = {
                "type": "tool_result",
                "name": tool_name,
                "input": tool_input,
                "result": ui_result_preview,
                "is_error": is_error
            }
            if tool_images:
                tool_result_event["images"] = tool_images
            yield tool_result_event

            # 3. role="tool" 메시지 추가 (OpenAI 공식 형식) — AI에게는 content만
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": truncated_output
            })

            # [images] 이미지가 있으면 user 메시지로 주입 (OpenAI tool role은 이미지 미지원)
            if tool_images:
                image_content = [{"type": "text", "text": f"[도구 {tool_name}의 스크린샷입니다]"}]
                for img in tool_images:
                    image_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.get('media_type', 'image/png')};base64,{img['base64']}"
                        }
                    })
                messages.append({"role": "user", "content": image_content})

        # [steer] 사용자 중단 시 루프 종료
        if cancelled:
            final = collected_text if collected_text else "사용자가 작업을 중단했습니다."
            yield {"type": "final", "content": final}
            return

        # 승인 요청 시 루프 중단
        if approval_requested:
            final = collected_text + "\n\n" + approval_message if collected_text else approval_message
            yield {"type": "final", "content": final}
            return

        # 재귀 호출로 후속 응답 처리 (도구 실행 후에는 auto-continue 리셋)
        yield from self._agentic_loop(
            messages, openai_tools, execute_tool, depth + 1,
            auto_continues=0, accumulated_text="",
            force_thinking_off=force_thinking_off,
            cancel_check=cancel_check
        )

    def _final_turn_text(self, messages: List[Dict], max_tokens: int) -> str:
        """마지막 턴 1회 호출 — ★tools를 넘기지 않는다(도구 없이 보고만).

        추론은 끈다: 보고는 원샷 계약이라 thinking이 max_tokens를 태우면 본문이 빈다
        (하이브리드 모델에서 실제로 나던 부류 — ep889)."""
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": min(max_tokens or 2048, 4096),
            "stream": False,
        }
        _off = self._thinking_off_params()
        if _off:
            params["extra_body"] = dict(_off)

        response = self._client.chat.completions.create(**params)
        return (response.choices[0].message.content or "") if response.choices else ""

    def _compact_openai(self, messages: List[Dict]) -> List[Dict]:
        """Rolling Compaction — 절차는 base._compact_openai_shape 가 갖는다 (2026-08-19 승격).

        이 클래스가 채우는 것은 '요약 1회 호출'(_summarize_for_compaction) 뿐이다.
        절차를 공유한 이유 = 고아 tool 제거 같은 필수 방어가 배선하는 쪽 손에 달려
        있으면 빠뜨린 프로바이더가 생긴다(http 변종 2종이 실제로 그랬다).
        """
        return self._compact_openai_shape(messages, "OpenAI")

    def _summarize_for_compaction(self, summary_input: str) -> str:
        """OpenAI SDK 로 요약 1회 호출 (비스트리밍). 실패하면 빈 문자열 → 프루닝 폴백."""
        try:

            # ★요약은 원샷 계약 — 추론을 반드시 끈다 (2026-08-17).
            #   하이브리드 thinking 모델(DeepSeek v4 등)은 추론이 max_tokens 를 전부 태워
            #   본문 0자를 돌려준다(ep889 부류). 그러면 요약이 실패하고 *삭제(프루닝)로 폴백*
            #   하므로, 보존 층이 무너지고 러닝머신이 되살아난다 — ep1177 실측: 요약 3회 중
            #   2회 실패 → 라운드 30·76 에서 삭제 → 직후 구간 중복 호출 급등(14회).
            summary_params = {
                "model": self.model,
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": self.COMPACTION_PROMPT},
                    {"role": "user", "content": summary_input}
                ],
                "temperature": 0.3,
            }
            _off = self._thinking_off_params()
            if _off:
                summary_params["extra_body"] = dict(_off)

            response = self._client.chat.completions.create(**summary_params)
            return (response.choices[0].message.content or "") if response.choices else ""

        except Exception as e:
            print(f"[Compaction][OpenAI] 요약 호출 예외: {e}")
            return ""
