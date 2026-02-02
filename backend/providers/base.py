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
