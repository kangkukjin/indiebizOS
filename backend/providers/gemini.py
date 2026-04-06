"""
gemini.py - Google Gemini 프로바이더 (최적화된 도구 호출)
IndieBiz OS Core

개선사항:
- 재귀 호출 제거 → while 루프로 변경
- 병렬 도구 호출 지원 (한 번의 응답에서 여러 도구 실행)
- 도구 호출 횟수 제한으로 무한 루프 방지
- 스트리밍 지원 유지

추가 개선 (v2):
- 성능 메트릭 추적 (토큰 사용량, 지연시간)
- 설정 가능한 강제 프롬프트
- 도구 결과 검증
"""

import re
import json
import time
import threading
import base64 as b64
from typing import List, Dict, Callable, Any, Generator
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini 프로바이더 (최적화된 도구 호출)

    개선 사항:
    - 성능 메트릭 추적
    - 설정 가능한 강제 프롬프트
    - 도구 결과 검증
    """

    # 도구 호출 제한
    MAX_TOOL_ITERATIONS = 70  # 최대 도구 호출 라운드
    MAX_CONSECUTIVE_TOOL_ONLY = 70  # 텍스트 없이 도구만 연속 호출 허용 횟수

    # Gemini 2.5: 1M 토큰 컨텍스트 → 80% = 800K 토큰 → ~3,200,000자
    COMPACTION_CHAR_THRESHOLD = 3200000

    # IBL 텍스트 출력 감지 패턴
    _IBL_TEXT_PATTERN = None  # 지연 컴파일

    # IBL 텍스트 출력 감지 시 교정 프롬프트
    FORCE_EXECUTE_IBL_PROMPT = """당신이 방금 텍스트 응답에 IBL 코드([node:action]{...} 형태)를 포함했습니다. 이것은 실행되지 않습니다.
IBL 코드는 반드시 execute_ibl 도구의 code 파라미터로 호출해야 합니다.
방금 텍스트에 쓴 IBL 코드를 execute_ibl 도구로 다시 실행하세요. 텍스트 응답에는 자연어만 사용하세요."""

    # 강제 프롬프트 (설정 가능)
    FORCE_RESPONSE_PROMPT = "도구 실행 결과를 바탕으로 사용자에게 답변을 작성해주세요."
    FORCE_STATUS_PROMPT = """도구만 연속 호출하고 있습니다. 반드시 멈추고 다음을 텍스트로 작성하세요:
1. 지금까지 알아낸 것 요약
2. 현재 작업의 진행 상황 (완료된 것 / 남은 것)
3. 해결이 안 되는 문제가 있다면 원인 분석
4. 다음 단계 계획 또는 사용자에게 보고할 내용

텍스트 응답 없이 도구만 호출하지 마세요."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._genai_client = None
        self._genai_types = None
        self._compaction_summary = None  # Rolling Compaction 요약 저장
        self._cache_name = None  # Gemini 컨텍스트 캐시 이름
        self._cached_system_prompt = None  # 캐시된 프롬프트 (변경 감지용)
        self._cached_gemini_tools = None  # 변환된 도구 캐시
        self._cache_thread = None  # 백그라운드 캐시 생성 스레드
        self._cache_ready = threading.Event()  # 캐시 준비 완료 시그널
        self._cache_lock = threading.Lock()  # 캐시 생성/삭제 동시성 보호
        self._last_tool_images = []  # 도구 실행 중 수집된 이미지

    @staticmethod
    def _patch_ipv4_preference():
        """IPv6 연결 실패 시 hang 방지 — IPv4 우선 DNS 해석 패치

        일부 네트워크 환경에서 Python이 IPv6를 우선 시도하면
        Google API 서버에 연결이 hang되는 문제를 해결한다.
        socket.getaddrinfo를 패치하여 IPv4 결과를 먼저 반환하도록 한다.
        """
        import socket
        _original_getaddrinfo = socket.getaddrinfo

        def _ipv4_first_getaddrinfo(*args, **kwargs):
            results = _original_getaddrinfo(*args, **kwargs)
            # IPv4(AF_INET)를 앞으로, IPv6(AF_INET6)를 뒤로
            results.sort(key=lambda x: x[0] != socket.AF_INET)
            return results

        if not getattr(socket.getaddrinfo, '_ipv4_patched', False):
            socket.getaddrinfo = _ipv4_first_getaddrinfo
            socket.getaddrinfo._ipv4_patched = True

    def init_client(self) -> bool:
        """Gemini 클라이언트 초기화 + 백그라운드 캐시 생성"""
        if not self.api_key:
            print(f"[GeminiProvider] {self.agent_name}: API 키 없음")
            return False

        try:
            # IPv6 hang 방지 패치 적용
            self._patch_ipv4_preference()

            from google import genai
            from google.genai import types

            self._genai_client = genai.Client(api_key=self.api_key)
            self._genai_types = types
            self._client = self._genai_client

            # 도구 변환 캐싱 (한 번만 수행)
            if self.tools:
                self._cached_gemini_tools = [types.Tool(function_declarations=self._convert_tools())]
            print(f"[GeminiProvider] {self.agent_name}: 초기화 완료 (도구 {len(self.tools)}개)")

            # 백그라운드 캐시 생성 시작 (첫 메시지를 블로킹하지 않음)
            self._start_background_cache()

            return True
        except ImportError:
            print("[GeminiProvider] google-genai 라이브러리 없음")
            return False
        except Exception as e:
            print(f"[GeminiProvider] 초기화 실패: {e}")
            return False

    def _start_background_cache(self):
        """백그라운드 스레드에서 캐시 생성 (논블로킹)"""
        if not self.system_prompt:
            self._cache_ready.set()  # 캐시 불필요 → 즉시 ready
            return

        def _create():
            try:
                self._create_cache_internal()
            except Exception as e:
                print(f"[Gemini Cache] 백그라운드 생성 실패: {e}")
            finally:
                self._cache_ready.set()

        self._cache_thread = threading.Thread(target=_create, daemon=True)
        self._cache_thread.start()
        print(f"[Gemini Cache] {self.agent_name}: 백그라운드 생성 시작")

    # ── 컨텍스트 캐싱 ──────────────────────────────────────

    def _create_cache_internal(self):
        """캐시 실제 생성 로직 (스레드 안전)

        system_instruction + tools를 캐시에 포함.
        Gemini API 규칙: cachedContent 사용 시 요청에
        system_instruction/tools/tool_config를 넣을 수 없음.
        """
        with self._cache_lock:
            if not self._genai_client or not self.system_prompt:
                return

            # 시스템 프롬프트가 변경되지 않았으면 기존 캐시 유지
            if self._cache_name and self._cached_system_prompt == self.system_prompt:
                return

            # 이전 캐시 삭제
            self._delete_cache_internal()

            try:
                t0 = time.time()
                types = self._genai_types
                cache_config = types.CreateCachedContentConfig(
                    displayName=f"indiebiz-{self.agent_name}",
                    systemInstruction=self.system_prompt,
                    tools=self._cached_gemini_tools,
                    ttl="3600s",  # 1시간
                )

                cache = self._genai_client.caches.create(
                    model=self.model,
                    config=cache_config
                )
                self._cache_name = cache.name
                self._cached_system_prompt = self.system_prompt
                elapsed = time.time() - t0
                tool_count = len(self.tools) if self.tools else 0
                prompt_tokens = len(self.system_prompt) // 3
                print(f"[Gemini Cache] 생성 완료: ~{prompt_tokens:,} 토큰 + 도구 {tool_count}개 캐시됨 ({elapsed:.2f}s, TTL=1h)")
            except Exception as e:
                print(f"[Gemini Cache] 생성 실패 (일반 모드로 동작): {e}")
                self._cache_name = None
                self._cached_system_prompt = None

    def _ensure_cache(self):
        """캐시가 준비됐는지 논블로킹 확인. 없으면 그냥 진행."""
        # 시스템 프롬프트 변경 감지 → 캐시 무효화 + 백그라운드 재생성
        if self._cache_name and self._cached_system_prompt != self.system_prompt:
            with self._cache_lock:
                self._delete_cache_internal()
            self._cache_ready.clear()
            self._start_background_cache()

        # 백그라운드 캐시가 준비될 때까지 최대 100ms만 대기
        # 첫 메시지에서 캐시가 아직 안 됐으면 캐시 없이 진행
        self._cache_ready.wait(timeout=3)

    def _delete_cache_internal(self):
        """기존 캐시 삭제 (lock 없이, 호출자가 lock 관리)"""
        if self._cache_name and self._genai_client:
            try:
                self._genai_client.caches.delete(name=self._cache_name)
                print(f"[Gemini Cache] 삭제: {self._cache_name}")
            except Exception:
                pass
        self._cache_name = None
        self._cached_system_prompt = None

    def _build_config(self, gemini_tools):
        """GenerateContentConfig 생성 (캐시 있으면 캐시만, 없으면 전부 직접 전달)"""
        types = self._genai_types

        if self._cache_name:
            # 캐시에 system_instruction + tools 포함됨
            # API 규칙: cachedContent 사용 시 tools/system_instruction 전달 불가
            return types.GenerateContentConfig(
                cachedContent=self._cache_name,
                temperature=0.8
            )
        else:
            return types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                tools=gemini_tools,
                temperature=0.8
            )

    def cleanup(self):
        """프로바이더 정리 (에이전트 종료 시 호출)"""
        # 백그라운드 스레드 대기
        if self._cache_thread and self._cache_thread.is_alive():
            self._cache_ready.wait(timeout=3)
        with self._cache_lock:
            self._delete_cache_internal()

    # ── 메시지 처리 ──────────────────────────────────────

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
        self._last_tool_images = []  # 턴 시작 시 초기화

        # 대화 히스토리 구성
        contents = self._build_contents(message, history, images)

        # 도구 설정 (캐시된 결과 사용)
        gemini_tools = self._cached_gemini_tools

        # 캐시 확인 (논블로킹, 최대 100ms 대기)
        self._ensure_cache()
        config = self._build_config(gemini_tools)

        # cancel_check를 execute_tool에 전달하는 래퍼 (도구 실행 중 중단 지원)
        _original_execute_tool = execute_tool
        if cancel_check and execute_tool:
            def _cancellable_execute_tool(name, inp, path, aid=None):
                return _original_execute_tool(name, inp, path, aid, cancel_check=cancel_check)
            execute_tool = _cancellable_execute_tool

        # 도구 호출 루프 (재귀 대신 while)
        accumulated_text = ""
        iteration = 0
        consecutive_tool_only = 0
        empty_response_retries = 0  # 빈 응답 재시도 횟수
        loop_start_time = time.time()

        while iteration < self.MAX_TOOL_ITERATIONS:
            # 중단 체크
            if cancel_check and cancel_check():
                print(f"[Gemini] 사용자 중단 요청 (iteration={iteration})")
                yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                return

            print(f"[Gemini] 라운드 {iteration + 1}/{self.MAX_TOOL_ITERATIONS} 시작")

            # Rolling Compaction: 컨텍스트가 임계값을 넘으면 요약으로 압축
            if iteration > 0 and self._should_compact(contents, iteration):
                contents = self._compact_gemini(contents, config)

            # Session Pruning: 오래된 도구 결과 마스킹 (iteration > 0일 때만)
            if iteration > 0:
                contents = self._prune_messages_gemini(contents)

            # API 호출 및 스트리밍
            try:
                collected_text, function_calls, response_content = yield from self._stream_single_response(
                    contents, config, cancel_check, iteration
                )
            except Exception as e:
                print(f"[Gemini] 라운드 {iteration+1} API 오류: {type(e).__name__}: {e}")
                yield {"type": "error", "content": str(e)}
                return

            # 텍스트 누적
            accumulated_text += collected_text

            # 도구 호출이 없으면 완료
            if not function_calls:
                # 텍스트도 없고 도구도 없는 빈 응답인 경우, 도구 결과 기반 응답 강제 유도 (최대 2회)
                if not collected_text.strip() and not accumulated_text.strip() and iteration > 0 and empty_response_retries < 2:
                    empty_response_retries += 1
                    print(f"[Gemini] 빈 응답 감지 (iteration={iteration}), 응답 강제 유도 (retry={empty_response_retries})")
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=self.FORCE_RESPONSE_PROMPT)]
                    ))
                    iteration += 1
                    continue

                # IBL 텍스트 출력 감지: 텍스트에 IBL 코드가 포함되어 있으면 execute_ibl 호출 유도 (최대 1회)
                if collected_text.strip() and self._detect_ibl_in_text(collected_text) and empty_response_retries < 1:
                    empty_response_retries += 1
                    print(f"[Gemini] ⚠️ 텍스트에 IBL 코드 감지 (iteration={iteration}), execute_ibl 호출 유도")
                    # 텍스트 응답을 모델 응답으로 추가하고 교정 프롬프트 주입
                    if response_content:
                        contents.append(response_content)
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=self.FORCE_EXECUTE_IBL_PROMPT)]
                    ))
                    # 누적 텍스트에서 잘못된 IBL 코드 제거 (교정 후 다시 생성)
                    accumulated_text = accumulated_text[:-len(collected_text)] if accumulated_text.endswith(collected_text) else accumulated_text
                    iteration += 1
                    continue

                print(f"[Gemini] 도구 호출 없음, 완료 (iteration={iteration})")
                break

            # 연속 도구만 호출 체크
            if collected_text.strip():
                consecutive_tool_only = 0
            else:
                consecutive_tool_only += 1
                if consecutive_tool_only >= self.MAX_CONSECUTIVE_TOOL_ONLY:
                    print(f"[Gemini] 텍스트 없이 도구만 {consecutive_tool_only}번 연속 호출, 상황 판단 강제 유도")
                    # 상황 판단 강제 유도 메시지 추가
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=self.FORCE_STATUS_PROMPT)]
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

            cancelled = False
            for fc in function_calls:
                # [steer] 도구 실행 전 사용자 중단 확인
                if cancel_check and cancel_check():
                    print(f"[Gemini][round={iteration}] 사용자 중단 — 도구 '{fc.name}' 스킵")
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": "[사용자가 중단했습니다]"}
                        )
                    )
                    cancelled = True
                    continue

                yield {"type": "thinking", "content": f"도구 실행 중: {fc.name}"}

                # 도구 실행 (content/details/images 분리 적용)
                tool_output, ui_details, tool_images = self._execute_single_tool(fc, execute_tool, iteration)

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

                # 도구 이미지 수집 (다음 턴 히스토리용)
                if tool_images:
                    self._last_tool_images.extend(tool_images)

                # 이벤트 발생 — UI에는 details가 있으면 details 사용
                tool_input = dict(fc.args) if fc.args else {}
                ui_result = ui_details if ui_details is not None else tool_output
                event = {
                    "type": "tool_result",
                    "name": fc.name,
                    "input": tool_input,
                    "result": ui_result[:3000] + "..." if len(str(ui_result)) > 3000 else ui_result
                }
                if tool_images:
                    event["images"] = tool_images
                yield event

                # 도구 응답 추가 (AI에게는 content만)
                # 파이프라인 결과인 경우 _action_count(병렬 포함 실제 액션 수) × 16KB 허용
                import re as _re
                _max_len = 16000
                _action_match = _re.search(r'"_action_count"\s*:\s*(\d+)', tool_output)
                if _action_match:
                    _actions = int(_action_match.group(1))
                    if _actions > 1:
                        _max_len = _max_len * _actions
                truncated_output = tool_output[:_max_len] if len(tool_output) > _max_len else tool_output
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": truncated_output}
                    )
                )

                # [images] 이미지가 있으면 inline_data Part로 추가 (AI가 볼 수 있도록)
                if tool_images:
                    import base64 as b64_module
                    for img in tool_images:
                        try:
                            img_bytes = b64_module.b64decode(img["base64"])
                            function_response_parts.append(
                                types.Part.from_bytes(
                                    data=img_bytes,
                                    mime_type=img.get("media_type", "image/png")
                                )
                            )
                        except Exception as img_err:
                            print(f"[Gemini] 이미지 Part 생성 실패: {img_err}")

            # [steer] 중단된 경우 즉시 종료
            if cancelled:
                yield {"type": "cancelled", "content": "사용자가 중단했습니다."}
                return

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

        # IBL 잔여물 정리: 텍스트에 남은 [action]{params} 패턴 제거
        # (에이전트가 도구 실행 결과를 텍스트에 포함시키는 경우)
        final_result = self._clean_ibl_from_text(final_result)

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

        # 전체 루프 지연시간 기록
        total_latency_ms = (time.time() - loop_start_time) * 1000
        # Gemini는 토큰 수를 직접 제공하지 않으므로 추정 (4자당 1토큰)
        estimated_output_tokens = len(final_result) // 4
        self.metrics.record_request(total_latency_ms, 0, estimated_output_tokens)

        print(f"[Gemini] 최종 응답 생성 (iteration={iteration}, len={len(final_result)}, latency={total_latency_ms:.0f}ms)")
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
        """스트림 생성 (500 에러 재시도, 캐시 만료 시 자동 복구)"""
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
                elif ("403" in error_str or "PERMISSION_DENIED" in error_str) and "CachedContent" in error_str:
                    # 캐시 만료/삭제 → 캐시 무효화 후 일반 모드로 재시도
                    print(f"[Gemini] 캐시 만료/삭제 감지, 캐시 무효화 후 일반 모드로 재시도")
                    with self._cache_lock:
                        self._cache_name = None
                        self._cached_system_prompt = None
                    config = self._build_config(self._cached_gemini_tools)
                    continue
                else:
                    raise e

        raise last_error if last_error else Exception("스트림 생성 실패")

    def _iterate_stream_with_retry(self, stream, contents: List, config, max_retries: int = 3):
        """스트림 반복 (500 에러 재시도, 캐시 만료 시 자동 복구)"""
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
                elif ("403" in error_str or "PERMISSION_DENIED" in error_str) and "CachedContent" in error_str and retry_count < max_retries:
                    # 캐시 만료/삭제 → 캐시 무효화 후 일반 모드로 재시도
                    retry_count += 1
                    print(f"[Gemini] 스트리밍 중 캐시 만료 감지, 일반 모드로 재시도 {retry_count}/{max_retries}")
                    with self._cache_lock:
                        self._cache_name = None
                        self._cached_system_prompt = None
                    config = self._build_config(self._cached_gemini_tools)
                    stream = self._genai_client.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=config
                    )
                    continue
                else:
                    raise e

    def _execute_single_tool(self, fc, execute_tool: Callable, iteration: int) -> tuple:
        """단일 도구 실행 (검증 및 메트릭 포함)

        Returns:
            (tool_output, ui_details): AI용 결과와 UI용 상세 정보
            - tool_output: AI에게 전달할 문자열
            - ui_details: UI에 표시할 상세 정보 (없으면 tool_output과 동일)
        """
        tool_input = dict(fc.args) if fc.args else {}

        # 로깅
        input_preview = json.dumps(tool_input, ensure_ascii=False)
        if len(input_preview) > 200:
            input_preview = input_preview[:200] + "..."
        print(f"[Gemini][round={iteration}] 도구 호출: {fc.name}")
        print(f"[Gemini][round={iteration}]   입력: {input_preview}")

        # 도구 호출 메트릭 기록
        self.metrics.record_tool_call()

        if not execute_tool:
            return "도구 실행 함수가 제공되지 않았습니다.", None

        try:
            raw_output = execute_tool(fc.name, tool_input, self.project_path, self.agent_id)

            # [content/details 분리] dict 반환 시 AI용과 UI용 분리
            ui_details = None
            tool_images = None  # [images] 도구가 반환한 이미지 데이터
            if isinstance(raw_output, dict) and "content" in raw_output:
                tool_output = raw_output["content"]
                ui_details = raw_output.get("details", tool_output)
                tool_images = raw_output.get("images")  # [{base64, media_type}]
            else:
                tool_output = raw_output

            # None 체크
            if tool_output is None:
                tool_output = "도구가 결과를 반환하지 않았습니다."
                print(f"[Gemini] 도구가 None 반환: {fc.name}")

            # dict/list를 JSON 문자열로 변환
            if isinstance(tool_output, (dict, list)):
                tool_output = json.dumps(tool_output, ensure_ascii=False)

            # 도구 결과 검증
            tool_output, is_error = self._verify_tool_result(fc.name, tool_input, str(tool_output))
            if is_error:
                print(f"[Gemini][round={iteration}] 도구 결과 검증 실패: {fc.name}")

            # 로깅
            output_len = len(str(tool_output))
            output_preview = str(tool_output)[:200] + "..." if output_len > 200 else str(tool_output)
            print(f"[Gemini][round={iteration}]   결과({output_len}자): {output_preview}")

            return tool_output, ui_details, tool_images

        except Exception as tool_err:
            self.metrics.record_error()
            print(f"[Gemini][round={iteration}] 도구 실행 예외: {fc.name} - {tool_err}")
            return f"도구 실행 실패: {fc.name} - {str(tool_err)}. 다른 방법을 시도하거나 사용자에게 알려주세요.", None, None

    def _clean_ibl_from_text(self, text: str) -> str:
        """텍스트 응답에서 실행되지 않은 IBL 코드 잔여물 제거

        에이전트가 execute_ibl로 실행한 후에도 텍스트에 IBL 코드를
        남기는 경우가 있음. 사용자에게 보이지 않도록 정리.
        코드블록(```) 안의 IBL은 유지 (설명 목적).
        """
        if not text:
            return text

        # 코드블록 영역 보존하면서 바깥의 IBL 패턴 제거
        # 코드블록 위치를 기록
        code_blocks = [(m.start(), m.end()) for m in re.finditer(r'```[\s\S]*?```', text)]

        def in_code_block(pos):
            return any(s <= pos < e for s, e in code_blocks)

        # [node:action]{...} 패턴 찾기
        ibl_pattern = re.compile(
            r'\[(?:self|sense|limbs|engines|others):[a-z_]+\]\s*\{[^}]*\}'
        )

        result = text
        for m in reversed(list(ibl_pattern.finditer(text))):
            if not in_code_block(m.start()):
                result = result[:m.start()] + result[m.end():]

        # 빈 줄 정리
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip() if result.strip() else text

    def _detect_ibl_in_text(self, text: str) -> bool:
        """텍스트 응답에 실행되지 않은 IBL 코드가 포함되어 있는지 감지

        [node:action]{params} 패턴이 텍스트에 있으면 True.
        코드블록(```) 안이나 인용("로 감싼) 설명은 제외.
        """
        if not text:
            return False

        # 지연 컴파일
        if self.__class__._IBL_TEXT_PATTERN is None:
            self.__class__._IBL_TEXT_PATTERN = re.compile(
                r'\[(?:self|sense|limbs|engines|others):[a-z_]+\]'
            )

        # 코드블록 제거 (설명/인용 목적의 IBL은 무시)
        cleaned = re.sub(r'```[\s\S]*?```', '', text)
        # 인라인 코드 제거
        cleaned = re.sub(r'`[^`]+`', '', cleaned)

        return bool(self.__class__._IBL_TEXT_PATTERN.search(cleaned))

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

            parts = []
            # 히스토리에 이미지가 있으면 Parts에 추가
            if h.get("images"):
                import base64 as b64_hist
                for img in h["images"]:
                    try:
                        img_bytes = b64_hist.b64decode(img["base64"])
                        parts.append(types.Part.from_bytes(
                            data=img_bytes,
                            mime_type=img.get("media_type", "image/png")
                        ))
                    except Exception:
                        pass
            parts.append(types.Part.from_text(text=tagged_content))
            contents.append(types.Content(role=role, parts=parts))

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

    def _compact_gemini(self, contents: List, config) -> List:
        """Rolling Compaction: 오래된 대화를 AI 요약으로 압축

        1. 오래된 메시지를 텍스트로 추출
        2. AI에게 요약 요청 (비스트리밍)
        3. 요약 메시지 + 최근 메시지로 교체
        """
        types = self._genai_types

        # 최근 메시지 수: KEEP_RECENT_TOOL_ROUNDS * 2 (tool_call + tool_result 쌍)
        keep_recent = self.KEEP_RECENT_TOOL_ROUNDS * 2 + 2  # +2는 여유분

        summary_text, recent_messages = self._extract_text_for_summary(contents, keep_recent)
        if not summary_text:
            return contents

        print(f"[Compaction][Gemini] 요약 시작: {len(summary_text):,}자 → AI 요약 요청")

        # 이전 요약이 있으면 포함
        prev_summary = ""
        if self._compaction_summary:
            prev_summary = f"\n\n[이전 요약]\n{self._compaction_summary}\n\n"

        # 요약 요청 (비스트리밍, 도구 없음)
        try:
            summary_config = types.GenerateContentConfig(
                system_instruction=self.COMPACTION_PROMPT,
                temperature=0.3  # 사실적 요약을 위해 낮은 temperature
            )

            summary_request = f"{prev_summary}[작업 기록]\n{summary_text}"
            # 요약 입력도 너무 길면 자르기
            if len(summary_request) > 100000:
                summary_request = summary_request[:50000] + "\n\n... (중략) ...\n\n" + summary_request[-50000:]

            response = self._genai_client.models.generate_content(
                model=self.model,
                contents=summary_request,
                config=summary_config
            )

            summary = response.text if response.text else ""

            # <summary> 태그 추출
            import re
            summary_match = re.search(r'<summary>(.*?)</summary>', summary, re.DOTALL)
            if summary_match:
                summary = summary_match.group(1).strip()

            if not summary:
                print(f"[Compaction][Gemini] 요약 생성 실패, 프루닝으로 대체")
                return contents

            self._compaction_summary = summary
            print(f"[Compaction][Gemini] 요약 완료: {len(summary):,}자")

            # 새 contents 구성: [요약 메시지] + [최근 메시지들]
            compacted = []

            # 요약을 user 메시지로 삽입 (model이 참조할 수 있도록)
            summary_content = types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text=f"<compaction_summary>\n{summary}\n</compaction_summary>\n\n위 요약은 이전 작업 기록의 압축본입니다. 이 맥락을 유지하면서 작업을 계속하세요."
                )]
            )
            compacted.append(summary_content)

            # model의 확인 응답 (Gemini는 user→model 교차 필수)
            ack_content = types.Content(
                role="model",
                parts=[types.Part.from_text(
                    text="이전 작업 요약을 확인했습니다. 요약된 맥락을 유지하며 작업을 계속하겠습니다."
                )]
            )
            compacted.append(ack_content)

            # 최근 메시지 추가
            compacted.extend(recent_messages)

            before_size = self._estimate_content_size(contents)
            after_size = self._estimate_content_size(compacted)
            print(f"[Compaction][Gemini] 크기 변화: {before_size:,}자 → {after_size:,}자 ({(1 - after_size/before_size)*100:.0f}% 감소)")

            return compacted

        except Exception as e:
            print(f"[Compaction][Gemini] 요약 생성 예외: {e}, 프루닝으로 대체")
            return contents

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
