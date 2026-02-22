"""
base.py - AI 프로바이더 기본 클래스
IndieBiz OS Core

개선 사항:
- 성능 메트릭 추적 (토큰 사용량, 지연시간)
- 재시도 설정
- 에러 복구 기본 로직
"""

import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class ProviderMetrics:
    """프로바이더 성능 메트릭"""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    total_retries: int = 0
    total_errors: int = 0
    total_tool_calls: int = 0
    last_request_latency_ms: float = 0
    avg_request_latency_ms: float = 0
    _latencies: List[float] = field(default_factory=list)

    def record_request(self, latency_ms: float, input_tokens: int = 0, output_tokens: int = 0):
        """요청 메트릭 기록"""
        self.total_requests += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.last_request_latency_ms = latency_ms
        self._latencies.append(latency_ms)
        # 최근 100개만 유지
        if len(self._latencies) > 100:
            self._latencies = self._latencies[-100:]
        self.avg_request_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_retry(self):
        """재시도 기록"""
        self.total_retries += 1

    def record_error(self):
        """에러 기록"""
        self.total_errors += 1

    def record_tool_call(self, count: int = 1):
        """도구 호출 기록"""
        self.total_tool_calls += count

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_requests": self.total_requests,
            "total_retries": self.total_retries,
            "total_errors": self.total_errors,
            "total_tool_calls": self.total_tool_calls,
            "last_request_latency_ms": round(self.last_request_latency_ms, 2),
            "avg_request_latency_ms": round(self.avg_request_latency_ms, 2)
        }


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_backoff: bool = True
    retryable_errors: tuple = (
        "rate_limit", "timeout", "server_error", "500", "502", "503", "504",
        "overloaded", "capacity", "INTERNAL"
    )

    def get_delay(self, attempt: int) -> float:
        """재시도 대기 시간 계산 (exponential backoff)"""
        if self.exponential_backoff:
            delay = self.base_delay_seconds * (2 ** attempt)
        else:
            delay = self.base_delay_seconds
        return min(delay, self.max_delay_seconds)

    def is_retryable(self, error: Exception) -> bool:
        """재시도 가능한 에러인지 확인"""
        error_str = str(error).lower()
        return any(err in error_str for err in self.retryable_errors)


class BaseProvider(ABC):
    """AI 프로바이더 기본 클래스

    개선 사항:
    - 성능 메트릭 추적 (토큰 사용량, 지연시간)
    - 재시도 설정 및 기본 로직
    - 에러 복구 기본 패턴
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        tools: List[Dict] = None,
        project_path: str = ".",
        agent_name: str = "에이전트",
        agent_id: str = None
    ):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.project_path = project_path
        self.agent_name = agent_name
        self.agent_id = agent_id
        self._client = None

        # 성능 메트릭
        self.metrics = ProviderMetrics()

        # 재시도 설정
        self.retry_config = RetryConfig()

        # 내부 상태
        self._pending_map_tags: List[str] = []

    @abstractmethod
    def init_client(self) -> bool:
        """클라이언트 초기화. 성공 시 True 반환"""
        pass

    @abstractmethod
    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None
    ) -> str:
        """
        메시지 처리

        Args:
            message: 사용자 메시지
            history: 대화 히스토리 [{"role": "user/assistant", "content": "..."}]
            images: 이미지 데이터 [{"base64": "...", "media_type": "image/png"}]
            execute_tool: 도구 실행 함수

        Returns:
            AI 응답 텍스트
        """
        pass

    @property
    def is_ready(self) -> bool:
        """클라이언트 준비 상태"""
        return self._client is not None

    def get_metrics(self) -> Dict:
        """성능 메트릭 조회"""
        return self.metrics.to_dict()

    def reset_metrics(self):
        """메트릭 초기화"""
        self.metrics = ProviderMetrics()

    def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """재시도 로직으로 함수 실행

        Args:
            func: 실행할 함수
            *args, **kwargs: 함수 인자

        Returns:
            함수 실행 결과

        Raises:
            마지막 에러 (재시도 모두 실패 시)
        """
        last_error = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(latency_ms)
                return result

            except Exception as e:
                last_error = e
                self.metrics.record_error()

                if attempt < self.retry_config.max_retries and self.retry_config.is_retryable(e):
                    delay = self.retry_config.get_delay(attempt)
                    self.metrics.record_retry()
                    print(f"[{self.__class__.__name__}] 재시도 {attempt + 1}/{self.retry_config.max_retries} "
                          f"({delay:.1f}s 후): {str(e)[:100]}")
                    time.sleep(delay)
                else:
                    raise

        raise last_error if last_error else Exception("Unknown error")

    # ========== Session Pruning (Atomic Message Grouping) ==========
    # 컨텍스트 관리를 위한 설정
    TOOL_RESULT_SOFT_LIMIT = 4000  # 이 이상이면 soft-trim
    TOOL_RESULT_HEAD = 1500  # head 유지 길이
    TOOL_RESULT_TAIL = 1500  # tail 유지 길이
    KEEP_RECENT_TOOL_ROUNDS = 3  # 최근 N 라운드의 도구 호출-결과 쌍을 전체 유지
    KEEP_RECENT_TOOL_RESULTS = KEEP_RECENT_TOOL_ROUNDS  # 하위 호환 alias

    # ========== Rolling Compaction 설정 ==========
    # Claude Code 참고: 컨텍스트의 80%에서 compaction 트리거
    # 글자 수 기반 임계값 (토큰 추정: 한글 2자≈1토큰, 영문 4자≈1토큰)
    # 각 프로바이더에서 모델의 컨텍스트 윈도우에 맞게 오버라이드 가능
    COMPACTION_CHAR_THRESHOLD = 640000  # 기본값: ~160K 토큰 (Claude 200K의 80%)
    COMPACTION_MIN_ROUNDS = 5  # 최소 이 라운드 이후에만 compaction 수행

    COMPACTION_PROMPT = """아래는 사용자의 요청을 처리하기 위해 지금까지 진행한 작업 기록입니다.
이 기록을 요약해주세요. 요약의 목적은 이후 작업을 이어갈 때 핵심 정보를 유지하는 것입니다.

반드시 포함할 내용:
1. 원래 사용자 요청의 핵심
2. 지금까지 완료된 작업 (성공/실패 구분)
3. 현재 페이지/화면의 상태 (URL, 선택된 값, 보이는 요소 등)
4. 중요한 식별자 (ref ID, 요소 이름, 선택한 옵션값 등)
5. 다음에 해야 할 작업
6. 실패한 접근법과 그 이유 (같은 실수 반복 방지)

<summary> 태그로 감싸서 작성하세요."""

    # ========== Auto-Continue 설정 ==========
    MAX_AUTO_CONTINUES = 3  # max_tokens 초과 시 이어쓰기 최대 횟수
    CONTINUATION_PROMPT = "이전 응답이 잘렸습니다. 중단된 곳에서 이어서 작성해주세요."

    def _soft_trim_content(self, content: str) -> str:
        """긴 텍스트를 head + tail로 soft-trim"""
        if len(content) <= self.TOOL_RESULT_SOFT_LIMIT:
            return content

        head = content[:self.TOOL_RESULT_HEAD]
        tail = content[-self.TOOL_RESULT_TAIL:]
        original_len = len(content)
        return f"{head}\n\n... [중략: 원본 {original_len}자] ...\n\n{tail}"

    # ========== Atomic Message Grouping ==========
    # tool_use(assistant) ↔ tool_result(user/tool) 쌍을 원자적 그룹으로 묶어
    # pruning 시 쌍이 깨지지 않도록 보장한다.

    def _build_message_groups_anthropic(self, messages: List[Dict]) -> List[tuple]:
        """Anthropic 형식에서 원자적 메시지 그룹 빌드

        Anthropic 패턴:
          messages[i]   = {"role": "assistant", "content": [...tool_use blocks...]}
          messages[i+1] = {"role": "user", "content": [...tool_result blocks...]}

        Returns:
            [(assistant_idx 또는 None, [result_indices]), ...]
        """
        groups = []
        for j, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            if not any(c.get("type") == "tool_result" for c in content):
                continue

            # tool_result user 메시지 발견 → 이전 assistant의 tool_use 쌍 찾기
            assistant_idx = None
            if j > 0 and messages[j - 1].get("role") == "assistant":
                asst_content = messages[j - 1].get("content", [])
                if isinstance(asst_content, list) and any(
                    c.get("type") == "tool_use" for c in asst_content
                ):
                    assistant_idx = j - 1

            groups.append((assistant_idx, [j]))
        return groups

    def _build_message_groups_openai(self, messages: List[Dict]) -> List[tuple]:
        """OpenAI/Ollama 형식에서 원자적 메시지 그룹 빌드

        OpenAI 패턴:
          messages[i]     = {"role": "assistant", "tool_calls": [...]}
          messages[i+1..] = {"role": "tool", "tool_call_id": "...", "content": "..."}

        Returns:
            [(assistant_idx, [result_indices]), ...]
        """
        groups = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                result_indices = []
                j = i + 1
                while j < len(messages) and messages[j].get("role") == "tool":
                    result_indices.append(j)
                    j += 1
                if result_indices:
                    groups.append((i, result_indices))
                i = j
            else:
                i += 1
        return groups

    def _build_message_groups_gemini(self, contents: List) -> List[tuple]:
        """Gemini 형식에서 원자적 메시지 그룹 빌드

        Gemini 패턴:
          contents[i]   = model Content with functionCall parts
          contents[i+1] = tool Content with functionResponse parts

        Returns:
            [(model_idx 또는 None, [result_indices]), ...]
        """
        groups = []
        for j, msg in enumerate(contents):
            parts = self._gemini_get_parts(msg)
            if not any(self._gemini_has_function_response(p) for p in parts):
                continue

            # functionResponse 메시지 발견 → 이전 model의 functionCall 쌍 찾기
            model_idx = None
            if j > 0:
                prev_parts = self._gemini_get_parts(contents[j - 1])
                if any(self._gemini_has_function_call(p) for p in prev_parts):
                    model_idx = j - 1

            groups.append((model_idx, [j]))
        return groups

    @staticmethod
    def _gemini_get_parts(msg) -> List:
        """Gemini 메시지에서 parts 추출 (dict 또는 Content 객체)"""
        if isinstance(msg, dict):
            return msg.get("parts", [])
        return getattr(msg, "parts", [])

    @staticmethod
    def _gemini_has_function_response(part) -> bool:
        """part에 functionResponse가 있는지 확인"""
        if isinstance(part, dict):
            return "functionResponse" in part
        return getattr(part, "function_response", None) is not None

    @staticmethod
    def _gemini_has_function_call(part) -> bool:
        """part에 functionCall이 있는지 확인"""
        if isinstance(part, dict):
            return "functionCall" in part
        return getattr(part, "function_call", None) is not None

    # ========== Pruning 메서드 (Atomic Grouping 기반) ==========

    def _prune_messages_anthropic(self, messages: List[Dict], keep_recent: int = None) -> List[Dict]:
        """Anthropic 형식 메시지에서 오래된 도구 결과를 원자적 그룹 단위로 마스킹

        원자적 그룹: assistant(tool_use) + user(tool_result) 쌍
        - old 그룹: tool_result 내용을 마스킹 (assistant 구조는 API 호환 위해 보존)
        - recent 그룹: soft-trim 적용
        """
        keep_recent = keep_recent or self.KEEP_RECENT_TOOL_ROUNDS

        groups = self._build_message_groups_anthropic(messages)
        if not groups:
            return messages

        # old/recent 그룹 분리
        if len(groups) <= keep_recent:
            old_groups = []
            recent_groups = groups
        else:
            old_groups = groups[:-keep_recent]
            recent_groups = groups[-keep_recent:]

        # 인덱스 세트 구축
        old_result_indices = set()
        for _, result_indices in old_groups:
            old_result_indices.update(result_indices)

        recent_result_indices = set()
        for _, result_indices in recent_groups:
            recent_result_indices.update(result_indices)

        pruned = []
        for i, msg in enumerate(messages):
            if i in old_result_indices:
                # old 그룹의 tool_result → 마스킹
                new_content = []
                for c in msg.get("content", []):
                    if c.get("type") == "tool_result":
                        # [images] 이미지 포함 tool_result(list)도 텍스트로 대체
                        if isinstance(c.get("content"), list):
                            new_content.append({**c, "content": "[이전 스크린샷 및 도구 결과 생략됨]"})
                        else:
                            new_content.append({**c, "content": "[이전 도구 결과 생략됨]"})
                    else:
                        new_content.append(c)
                pruned.append({"role": msg["role"], "content": new_content})
            elif i in recent_result_indices:
                # recent 그룹의 tool_result → soft-trim
                new_content = []
                for c in msg.get("content", []):
                    if c.get("type") == "tool_result" and isinstance(c.get("content"), str):
                        new_content.append({**c, "content": self._soft_trim_content(c["content"])})
                    elif c.get("type") == "tool_result" and isinstance(c.get("content"), list):
                        # [images] 이미지 포함 최근 tool_result → 이미지 유지, 텍스트만 trim
                        trimmed_content = []
                        for block in c["content"]:
                            if block.get("type") == "text":
                                trimmed_content.append({**block, "text": self._soft_trim_content(block["text"])})
                            else:
                                trimmed_content.append(block)  # 이미지 블록 유지
                        new_content.append({**c, "content": trimmed_content})
                    else:
                        new_content.append(c)
                pruned.append({"role": msg["role"], "content": new_content})
            else:
                # assistant 메시지 및 일반 메시지 → 그대로 보존
                pruned.append(msg)

        return pruned

    def _prune_messages_openai(self, messages: List[Dict], keep_recent: int = None) -> List[Dict]:
        """OpenAI/Ollama 형식 메시지에서 오래된 도구 결과를 원자적 그룹 단위로 마스킹

        원자적 그룹: assistant(tool_calls) + role="tool" 메시지들
        - old 그룹: tool 메시지 내용을 마스킹 (assistant 구조는 보존)
        - recent 그룹: soft-trim 적용
        """
        keep_recent = keep_recent or self.KEEP_RECENT_TOOL_ROUNDS

        groups = self._build_message_groups_openai(messages)
        if not groups:
            return messages

        # old/recent 그룹 분리
        if len(groups) <= keep_recent:
            old_groups = []
            recent_groups = groups
        else:
            old_groups = groups[:-keep_recent]
            recent_groups = groups[-keep_recent:]

        # 인덱스 세트 구축
        old_result_indices = set()
        for _, result_indices in old_groups:
            old_result_indices.update(result_indices)

        recent_result_indices = set()
        for _, result_indices in recent_groups:
            recent_result_indices.update(result_indices)

        pruned = []
        for i, msg in enumerate(messages):
            if i in old_result_indices:
                # old 그룹의 tool → 마스킹
                # [images] 이미지 주입된 user 메시지도 텍스트로 대체
                content = msg.get("content", "")
                if isinstance(content, list):
                    pruned.append({**msg, "content": "[이전 스크린샷 및 도구 결과 생략됨]"})
                else:
                    pruned.append({**msg, "content": "[이전 도구 결과 생략됨]"})
            elif i in recent_result_indices:
                # recent 그룹의 tool → soft-trim
                content = msg.get("content", "")
                if isinstance(content, str):
                    pruned.append({**msg, "content": self._soft_trim_content(content)})
                elif isinstance(content, list):
                    # [images] 이미지 포함 최근 메시지 → 이미지 유지, 텍스트만 trim
                    trimmed = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            trimmed.append({**block, "text": self._soft_trim_content(block["text"])})
                        else:
                            trimmed.append(block)
                    pruned.append({**msg, "content": trimmed})
                else:
                    pruned.append(msg)
            else:
                # assistant 메시지 및 일반 메시지 → 그대로 보존
                pruned.append(msg)

        return pruned

    def _prune_messages_gemini(self, contents: List, keep_recent: int = None) -> List:
        """Gemini 형식 메시지에서 오래된 도구 결과를 원자적 그룹 단위로 마스킹

        원자적 그룹: model(functionCall) + tool(functionResponse) 쌍
        - old 그룹: functionResponse를 마스킹 (dict만, Content 객체는 immutable)
        - recent 그룹: 그대로 보존
        """
        keep_recent = keep_recent or self.KEEP_RECENT_TOOL_ROUNDS

        groups = self._build_message_groups_gemini(contents)
        if not groups:
            return contents

        # old/recent 그룹 분리
        if len(groups) <= keep_recent:
            old_groups = []
        else:
            old_groups = groups[:-keep_recent]

        old_result_indices = set()
        for _, result_indices in old_groups:
            old_result_indices.update(result_indices)

        pruned = []
        for i, msg in enumerate(contents):
            if i in old_result_indices:
                # dict만 마스킹 (Content 객체는 immutable이므로 그대로)
                if isinstance(msg, dict):
                    new_parts = []
                    for p in msg.get("parts", []):
                        if "functionResponse" in p:
                            new_parts.append({
                                "functionResponse": {
                                    "name": p["functionResponse"].get("name", "unknown"),
                                    "response": {"result": "[이전 도구 결과 생략됨]"}
                                }
                            })
                        else:
                            new_parts.append(p)
                    pruned.append({"role": msg.get("role"), "parts": new_parts})
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        return pruned

    def _verify_tool_result(self, tool_name: str, tool_input: Dict, tool_output: str) -> tuple[str, bool]:
        """도구 결과 검증 (기본 구현)

        Args:
            tool_name: 도구 이름
            tool_input: 도구 입력
            tool_output: 도구 출력

        Returns:
            (검증된 출력, 에러 여부)
        """
        # 빈 결과 검증
        if not tool_output or tool_output.strip() == "":
            return f"도구 '{tool_name}'이 빈 결과를 반환했습니다.", True

        # None 결과 검증
        if tool_output == "None":
            return f"도구 '{tool_name}'이 None을 반환했습니다.", True

        # 에러 패턴 검증
        error_patterns = ["error:", "exception:", "failed:", "traceback"]
        output_lower = tool_output.lower()
        is_error = any(pattern in output_lower for pattern in error_patterns)

        return tool_output, is_error

    # ========== Rolling Compaction ==========

    def _estimate_content_size(self, messages_or_contents) -> int:
        """메시지/컨텐츠의 총 글자 수 추정

        Gemini Content 객체, OpenAI dict, Anthropic dict 모두 처리
        """
        import json as _json
        total = 0
        for msg in messages_or_contents:
            if isinstance(msg, dict):
                total += len(_json.dumps(msg, ensure_ascii=False, default=str))
            else:
                # Gemini Content 객체
                parts = getattr(msg, "parts", [])
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        total += len(part.text)
                    elif hasattr(part, "function_call") and part.function_call:
                        total += len(str(part.function_call))
                    elif hasattr(part, "function_response") and part.function_response:
                        total += len(str(part.function_response))
                    else:
                        total += 100  # 이미지 등 기타
        return total

    def _should_compact(self, messages_or_contents, iteration: int) -> bool:
        """Compaction이 필요한지 판단

        조건:
        1. 최소 라운드 이상 진행
        2. 컨텐츠 크기가 임계값 초과
        """
        if iteration < self.COMPACTION_MIN_ROUNDS:
            return False

        content_size = self._estimate_content_size(messages_or_contents)
        should = content_size >= self.COMPACTION_CHAR_THRESHOLD
        if should:
            print(f"[Compaction] 임계값 도달: {content_size:,}자 >= {self.COMPACTION_CHAR_THRESHOLD:,}자 (iteration={iteration})")
        return should

    def _extract_text_for_summary(self, messages_or_contents, keep_recent: int = 3) -> tuple:
        """요약 대상 텍스트 추출 및 최근 메시지 분리

        Returns:
            (summary_text: str, recent_messages: list)
            - summary_text: 오래된 메시지들을 텍스트로 변환한 것
            - recent_messages: 유지할 최근 메시지들
        """
        import json as _json
        total = len(messages_or_contents)

        if total <= keep_recent:
            return "", messages_or_contents

        old_messages = messages_or_contents[:-keep_recent]
        recent_messages = messages_or_contents[-keep_recent:]

        # 오래된 메시지를 텍스트로 변환
        lines = []
        for msg in old_messages:
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Anthropic/OpenAI의 복합 content
                    text_parts = []
                    for c in content:
                        if isinstance(c, dict):
                            if c.get("type") == "text":
                                text_parts.append(c.get("text", ""))
                            elif c.get("type") == "tool_result":
                                tr_content = c.get("content", "")
                                if isinstance(tr_content, str):
                                    text_parts.append(f"[도구결과:{c.get('tool_use_id','')}] {tr_content[:500]}")
                                else:
                                    text_parts.append(f"[도구결과:{c.get('tool_use_id','')}] (복합데이터)")
                            elif c.get("type") == "tool_use":
                                text_parts.append(f"[도구호출:{c.get('name','')}] {_json.dumps(c.get('input',{}), ensure_ascii=False)[:300]}")
                        elif isinstance(c, str):
                            text_parts.append(c)
                    content = "\n".join(text_parts)
                elif isinstance(content, str) and "[이전 도구 결과 생략됨]" in content:
                    content = "(생략됨)"

                # content가 None인 경우 빈 문자열로 처리
                if content is None:
                    content = ""

                # OpenAI tool_calls
                if msg.get("tool_calls"):
                    tc_names = [tc.get("function", {}).get("name", "") for tc in msg["tool_calls"]]
                    content += f" [도구호출: {', '.join(tc_names)}]"

                lines.append(f"[{role}] {content[:1000]}")
            else:
                # Gemini Content 객체
                role = getattr(msg, "role", "unknown")
                parts = getattr(msg, "parts", [])
                part_texts = []
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        part_texts.append(part.text[:1000])
                    elif hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        part_texts.append(f"[도구호출:{getattr(fc, 'name', '')}]")
                    elif hasattr(part, "function_response") and part.function_response:
                        fr = part.function_response
                        result = getattr(fr, "response", {})
                        if isinstance(result, dict):
                            result_text = str(result.get("result", ""))[:500]
                        else:
                            result_text = str(result)[:500]
                        part_texts.append(f"[도구결과:{getattr(fr, 'name', '')}] {result_text}")
                lines.append(f"[{role}] {' | '.join(part_texts)}")

        summary_text = "\n".join(lines)
        return summary_text, recent_messages
