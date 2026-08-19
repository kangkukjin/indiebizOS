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


# ============ 도구 루프 상한 (전 프로바이더 공통) ============
#
# 프로바이더마다 따로 자란 상수(anthropic·openai·ollama=30 / gemini 계열=70)를
# 2026-08-17 하나로 통일. 같은 시스템에서 어느 모델을 타느냐로 상한이 두 배 갈리던
# 것은 설계가 아니라 드리프트였다.
MAX_TOOL_ROUNDS = 100

# 상한 도달 시 '마지막 턴'에 주입하는 지시.
# ★상한 도달을 에러로 처리하지 않는다 — 하드 에러는 그때까지의 작업을 통째로 버린다.
#   대신 도구 없이 한 번 더 불러 "여기까지 했고 남은 건 이것"을 받아낸다.
FINAL_TURN_INSTRUCTION = """[시스템] 도구 사용 라운드 상한({limit}회)에 도달했다. 이번 턴에는 도구를 쓸 수 없다.

지금까지 실제로 한 일만 가지고 사용자에게 보고하라:
1. 완료한 것 — 파일 경로·변경 내용·산출물을 구체적으로
2. 착수했으나 끝내지 못한 것
3. 남은 일과, 이어서 하려면 무엇부터 하면 되는지

확인하지 못한 것을 완료했다고 쓰지 마라. 도구로 검증하지 못한 부분은 검증하지 못했다고 적어라."""

# 마지막 턴 호출마저 실패했을 때의 폴백 — 그래도 에러보다는 낫다.
FINAL_TURN_FALLBACK = (
    "(도구 사용 라운드 상한({limit}회)에 도달해 작업을 중단했습니다. "
    "마무리 보고 생성에도 실패해 진행 상황을 요약하지 못했습니다. "
    "직전까지의 도구 호출 기록을 확인해 주세요.)"
)


def build_final_turn_messages(messages: List[Dict], limit: int) -> List[Dict]:
    """마지막 턴용 메시지 = 지금까지의 대화 + 보고 지시 (OpenAI/Ollama/Anthropic 공용 형식)

    ★마지막이 이미 user면 새 메시지를 덧붙이지 않고 그 안에 이어 쓴다 — 상한에 걸리는
    시점의 마지막 메시지는 보통 tool_result(user 역할)이고, Anthropic은 연속 user
    메시지를 거절한다."""
    instruction = FINAL_TURN_INSTRUCTION.format(limit=limit)
    out = list(messages)

    if out and out[-1].get("role") == "user":
        last = dict(out[-1])
        content = last.get("content")
        if isinstance(content, list):
            last["content"] = list(content) + [{"type": "text", "text": instruction}]
        else:
            last["content"] = f"{content}\n\n{instruction}"
        out[-1] = last
        return out

    out.append({"role": "user", "content": instruction})
    return out


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
        agent_id: str = None,
        thinking_budget: int = 0
    ):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.project_path = project_path
        self.agent_name = agent_name
        self.agent_id = agent_id
        self._client = None

        # Extended Thinking: 0이면 비활성, 양수면 해당 토큰 수만큼 thinking 예산
        self.thinking_budget = thinking_budget

        # 성능 메트릭
        self.metrics = ProviderMetrics()

        # 재시도 설정
        self.retry_config = RetryConfig()

        # 내부 상태
        self._pending_map_tags: List[str] = []

    def _notify_round(self, round_no: int, budget: int):
        """도구 루프 라운드 시작 1건 — 구조화 스텝 원장 기록 + 사람용 마커 print.

        (2026-08-14) execution_rounds 관측이 `[Gemini] 라운드` 정규식에 결박돼 프로바이더
        전환만으로 조용히 끊겼던 결함의 수리 — 모든 프로바이더 루프가 이 한 줄을 부른다.
        episode_logger 부재(비정상 환경)면 print 폴백으로 강등(라운드 표시는 항상 남음)."""
        name = type(self).__name__.replace("Provider", "")
        try:
            from episode_logger import notify_round
            notify_round(name, getattr(self, "model", "?"), round_no, budget)
        except Exception:
            print(f"[{name}] 라운드 {round_no}/{budget} 시작")

    def _final_turn(self, messages: List[Dict], max_tokens: int = 2048,
                    limit: int = MAX_TOOL_ROUNDS):
        """도구 루프 상한 착지 — 도구 없이 한 번 더 불러 성과·잔여를 받아낸다.

        상한 도달을 에러로 끝내면 그때까지의 라운드가 통째로 버려진다(사용자에게는
        "제한에 도달했습니다" 한 줄만 남는다). 여기서는 도구를 뗀 채 한 번 더 불러
        보고를 받아 정상 응답(final)으로 착지시킨다.

        프로바이더는 `_final_turn_text`만 구현하면 된다."""
        name = type(self).__name__.replace("Provider", "")
        print(f"[{name}] 도구 라운드 상한({limit}회) 도달 — 마무리 보고 턴 실행")

        text = ""
        try:
            text = (self._final_turn_text(
                build_final_turn_messages(messages, limit), max_tokens
            ) or "").strip()
        except Exception as e:
            print(f"[{name}] 마무리 보고 턴 실패: {str(e)[:200]}")

        if text:
            text += f"\n\n(도구 사용 라운드 상한 {limit}회에 도달해 여기서 중단했습니다.)"
        else:
            text = FINAL_TURN_FALLBACK.format(limit=limit)

        yield {"type": "final", "content": text}

    def _final_turn_wrap(self, text: str, limit: int) -> str:
        """마지막 턴 결과 → 사용자 응답 (문자열 반환 프로바이더용 공통 마무리)"""
        text = (text or "").strip()
        if text:
            return f"{text}\n\n(도구 사용 라운드 상한 {limit}회에 도달해 여기서 중단했습니다.)"
        return FINAL_TURN_FALLBACK.format(limit=limit)

    def _final_turn_text(self, messages: List[Dict], max_tokens: int) -> str:
        """마지막 턴 1회 비스트리밍 호출(★도구 없이). 프로바이더가 오버라이드한다.

        미구현 프로바이더는 빈 문자열 → `_final_turn`이 폴백 문구로 착지."""
        return ""

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
    #
    # ★프루닝은 '컨텍스트 압력이 있을 때만' 돈다 (2026-08-17).
    #   그 전까지는 매 라운드 무조건 돌면서 최근 3라운드 밖의 도구 결과를 통째로 지웠다.
    #   컨텍스트가 35K/200K 로 텅 비어 있어도 지웠고, 지운 결과를 다음 라운드로 그대로
    #   넘기므로 소실은 영구적이었다 → 에이전트가 읽은 파일을 3라운드마다 잃고 다시 읽는
    #   러닝머신(ep1173: 30라운드 중 마지막 10라운드가 같은 파일 재-cat, 쓰기 0건).
    #   게다가 프루닝이 먼저 크기를 깎아버려 *요약해서 보존하는* compaction 이 임계값에
    #   영원히 못 닿았다(864,612자 → 9,591자, compaction 임계 410,000자 = 발동 0회).
    #   두 층의 목적은 같다("컨텍스트 초과 방지") — 그렇다면 조건도 같아야 하고,
    #   순서는 '보존(요약)이 먼저, 삭제는 최후'여야 한다.
    TOOL_RESULT_SOFT_LIMIT = 4000  # 이 이상이면 soft-trim
    TOOL_RESULT_HEAD = 1500  # head 유지 길이
    TOOL_RESULT_TAIL = 1500  # tail 유지 길이
    KEEP_RECENT_TOOL_ROUNDS = 3  # 최근 N 라운드의 도구 호출-결과 쌍을 전체 유지
    KEEP_RECENT_TOOL_RESULTS = KEEP_RECENT_TOOL_ROUNDS  # 하위 호환 alias

    # ========== Rolling Compaction 설정 ==========
    # Claude Code 참고: 컨텍스트의 80%에서 compaction 트리거
    #
    # ★자↔토큰 환산은 **2자 = 1토큰** (2026-08-17 실측으로 교정).
    #   옛 임계값들은 영문 기준 4자=1토큰으로 잡혀 있었으나, 이 시스템이 실제로 나르는
    #   내용(한국어 문서·한글 주석 섞인 코드)을 재보니 한국어 1.97자/토큰·파이썬 2.63자/토큰
    #   이었다 = 임계값이 약 2배 헐거웠다. 프루닝이 매 라운드 무조건 돌던 시절엔 페이로드가
    #   임계값 근처에도 못 가서 이 오차가 드러나지 않았지만, 프루닝을 압력 게이트 뒤로
    #   옮긴 지금은 이 숫자가 곧 컨텍스트 초과 방어선이다 → 전 프로바이더 절반으로 교정.
    COMPACTION_CHAR_THRESHOLD = 320000  # 기본값: ~160K 토큰 (Claude 200K의 80%)
    COMPACTION_MIN_ROUNDS = 5  # 최소 이 라운드 이후에만 compaction 수행

    # 프루닝(삭제) 임계값 — None 이면 COMPACTION_CHAR_THRESHOLD 를 따른다.
    # 같은 값을 쓰므로 순서가 곧 정책이 된다: 압력이 오면 compaction 이 먼저 요약해
    # 크기를 낮추고, 그래도 임계값 위면(요약 실패 등) 그때 프루닝이 최후 수단으로 지운다.
    PRUNE_CHAR_THRESHOLD = None

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

    # 원샷(분류·평가·증류·번역) 계약용 — True면 하이브리드 thinking 모델의 추론 모드를 끈다.
    # 지원 프로바이더만 해석(DeepSeek/Gemini/OpenRouter 등), 나머지는 무시. ep889: thinking이
    # max_tokens를 전부 태워 텍스트 0자 → Auto-Continue/빈응답 재시도 연쇄로 증류 1건에 7콜 4.5분.
    disable_thinking = False
    # thinking 차단 파라미터를 400 거부하는 모델(gemini flash-latest 부류) 자가치유 표식 —
    # 한 번 거부되면 그 프로바이더 인스턴스(=모델별 캐시)에선 차단 시도를 접는다.
    _thinking_off_unsupported = False

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

    # ── 공유 compaction 절차 (프로바이더는 '요약 1회 호출'만 채운다) ──────
    # ★2026-08-19: 요약→교체 절차는 프로바이더마다 같고, 다른 건 요약을 부르는 방법뿐이다.
    #   그래서 절차를 여기 한 벌 두고 프로바이더는 _summarize_for_compaction 만 구현한다.
    #   그전엔 절차가 openai/gemini/anthropic 에 복제돼 있었고, http 변종 2종은 복제조차
    #   못 받아 COMPACTION_CHAR_THRESHOLD 만 선언한 채 부르는 쪽이 없었다(선언-호출 분리 드리프트).

    def _summarize_for_compaction(self, summary_input: str) -> str:
        """요약 1회 호출 — 프로바이더가 구현한다. 빈 문자열이면 compaction 포기(프루닝 폴백).

        ★원샷 계약이므로 추론을 반드시 꺼야 한다: 하이브리드 thinking 모델은 추론이
          max_tokens 를 전부 태워 본문 0자를 돌려주고, 그러면 보존 층이 무너진다(ep1177).
        기본 구현은 빈 문자열 = 미구현 프로바이더는 지금까지처럼 프루닝만 한다."""
        return ""

    def _compaction_summary_input(self, summary_text: str) -> str:
        """이전 요약 + 이번 작업 기록을 합쳐 요약 입력을 만든다(과길면 양끝 보존 중략)."""
        prev = getattr(self, "_compaction_summary", None)
        prev_summary = f"\n\n[이전 요약]\n{prev}\n\n" if prev else ""
        summary_input = f"{prev_summary}[작업 기록]\n{summary_text}"
        if len(summary_input) > 100000:
            summary_input = summary_input[:50000] + "\n\n... (중략) ...\n\n" + summary_input[-50000:]
        return summary_input

    @staticmethod
    def _unwrap_summary_tag(summary: str) -> str:
        """<summary>...</summary> 로 감싸 왔으면 벗긴다."""
        import re as _re
        m = _re.search(r'<summary>(.*?)</summary>', summary or "", _re.DOTALL)
        return m.group(1).strip() if m else (summary or "").strip()

    def _compaction_preamble_text(self, summary: str) -> str:
        return (f"<compaction_summary>\n{summary}\n</compaction_summary>\n\n"
                "위 요약은 이전 작업 기록의 압축본입니다. 이 맥락을 유지하면서 작업을 계속하세요.")

    _COMPACTION_ACK = "이전 작업 요약을 확인했습니다. 요약된 맥락을 유지하며 작업을 계속하겠습니다."

    def _log_compaction_size(self, label: str, before, after) -> None:
        before_size = self._estimate_content_size(before)
        after_size = self._estimate_content_size(after)
        if before_size:
            pct = (1 - after_size / before_size) * 100
            print(f"[Compaction][{label}] 크기 변화: {before_size:,}자 → {after_size:,}자 ({pct:.0f}% 감소)")

    def _compact_openai_shape(self, messages: List[Dict], label: str) -> List[Dict]:
        """OpenAI 형식(role/content/tool_calls) 메시지의 rolling compaction — 공유 구현.

        openai.py 와 deepseek_http.py 가 함께 쓴다. ★고아 tool 메시지 제거가 이 안에 있으므로
        이 함수를 쓰는 쪽은 400("Messages with role 'tool' must be a response to a preceding
        message with 'tool_calls'", ep1176)을 자동으로 면한다 — 배선하는 쪽이 잊을 수 없게."""
        keep_recent = self.KEEP_RECENT_TOOL_ROUNDS * 2 + 2
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        summary_text, recent_messages = self._extract_text_for_summary(non_system, keep_recent)
        if not summary_text:
            return messages

        print(f"[Compaction][{label}] 요약 시작: {len(summary_text):,}자 → AI 요약 요청")
        try:
            summary = self._unwrap_summary_tag(
                self._summarize_for_compaction(self._compaction_summary_input(summary_text)))
            if not summary:
                print(f"[Compaction][{label}] 요약 생성 실패, 프루닝으로 대체")
                return messages

            self._compaction_summary = summary
            print(f"[Compaction][{label}] 요약 완료: {len(summary):,}자")

            compacted = list(system_messages)
            compacted.append({"role": "user",
                              "content": self._compaction_preamble_text(summary)})
            compacted.append({"role": "assistant", "content": self._COMPACTION_ACK})
            # 최근 메시지 추가 (+ 고아 tool 메시지 최후 방어선 — 남으면 400 으로 작업이 죽는다)
            compacted.extend(recent_messages)
            compacted = self._drop_orphan_tool_messages(compacted)

            self._log_compaction_size(label, messages, compacted)
            return compacted
        except Exception as e:
            print(f"[Compaction][{label}] 요약 생성 예외: {e}, 프루닝으로 대체")
            return messages

    def _compact_gemini_http_shape(self, contents: List, label: str) -> List:
        """Gemini REST 형식({role, parts}) 컨텐츠의 rolling compaction — gemini_http 전용.

        SDK 판(gemini.py)은 Content 객체를 다뤄 자기 구현을 쓴다. 여기선 dict 만 만든다.
        고아 방어는 _extract_text_for_summary 의 경계 스냅이 담당한다
        (functionResponse 로 시작하는 자리는 스냅이 앞으로 밀어 잘리지 않는다)."""
        keep_recent = self.KEEP_RECENT_TOOL_ROUNDS * 2 + 2
        summary_text, recent_contents = self._extract_text_for_summary(contents, keep_recent)
        if not summary_text:
            return contents

        print(f"[Compaction][{label}] 요약 시작: {len(summary_text):,}자 → AI 요약 요청")
        try:
            summary = self._unwrap_summary_tag(
                self._summarize_for_compaction(self._compaction_summary_input(summary_text)))
            if not summary:
                print(f"[Compaction][{label}] 요약 생성 실패, 프루닝으로 대체")
                return contents

            self._compaction_summary = summary
            print(f"[Compaction][{label}] 요약 완료: {len(summary):,}자")

            compacted = [
                {"role": "user",
                 "parts": [{"text": self._compaction_preamble_text(summary)}]},
                {"role": "model", "parts": [{"text": self._COMPACTION_ACK}]},
            ]
            compacted.extend(recent_contents)

            self._log_compaction_size(label, contents, compacted)
            return compacted
        except Exception as e:
            print(f"[Compaction][{label}] 요약 생성 예외: {e}, 프루닝으로 대체")
            return contents

    def _should_prune(self, messages_or_contents, iteration: int = None) -> bool:
        """프루닝(삭제)이 필요한지 판단 — 컨텍스트 압력이 있을 때만 True.

        압력이 없으면 지우지 않는다. 도구 결과는 이미 실행 시점에
        MAX_TOOL_RESULT_LENGTH 로 한 번 잘려 들어오므로, 압력 전까지는
        '읽은 것을 그대로 들고 있는' 편이 항상 낫다.

        ★COMPACTION_MIN_ROUNDS 전에는 지우지 않는다: 그 구간은 compaction 이
        자격 미달이라, 여기서 지우면 '보존(요약)이 먼저'라는 순서가 깨진다
        (ep1176 실측 — 라운드 5 에서 프루닝이 먼저 삭제했고 요약은 9라운드에야 돌았다)."""
        if iteration is not None and iteration < self.COMPACTION_MIN_ROUNDS:
            return False
        threshold = self.PRUNE_CHAR_THRESHOLD or self.COMPACTION_CHAR_THRESHOLD
        content_size = self._estimate_content_size(messages_or_contents)
        should = content_size >= threshold
        if should:
            print(f"[Pruning] 압력 도달: {content_size:,}자 >= {threshold:,}자 → 오래된 도구 결과 마스킹")
        return should

    @staticmethod
    def _is_dependent_continuation(msg) -> bool:
        """앞 메시지(도구 호출)에 딸린 '응답' 메시지인가 — 여기서 잘리면 고아가 된다.

        세 형식을 모두 본다:
        - OpenAI/Ollama: role == "tool"
        - Anthropic: role == "user" + content 안에 tool_result 블록
        - Gemini: parts 안에 functionResponse (dict) / function_response (Content 객체)
        """
        if isinstance(msg, dict):
            if msg.get("role") == "tool":
                return True
            content = msg.get("content")
            if msg.get("role") == "user" and isinstance(content, list):
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    return True
            parts = msg.get("parts")
            if isinstance(parts, list):
                if any(isinstance(p, dict) and "functionResponse" in p for p in parts):
                    return True
            return False

        # Gemini types.Content 객체
        parts = getattr(msg, "parts", None)
        if isinstance(parts, list):
            return any(getattr(p, "function_response", None) is not None for p in parts)
        return False

    def _drop_orphan_tool_messages(self, messages: List[Dict]) -> List[Dict]:
        """앞선 tool_calls 를 잃은 고아 tool 메시지 제거 (OpenAI/Ollama 형식, 최후 방어선).

        경계 스냅이 제대로 되면 여기서 걸릴 게 없다. 그래도 두는 이유 = 이 부류의 실패가
        400 으로 *작업 전체*를 죽이기 때문. 조용히 버리지 않고 무엇을 버렸는지 남긴다."""
        pending = set()
        out = []
        for msg in messages:
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                pending = {tc.get("id") for tc in msg["tool_calls"] if isinstance(tc, dict)}
                out.append(msg)
                continue
            if role == "tool":
                if msg.get("tool_call_id") in pending:
                    out.append(msg)
                else:
                    print(f"[Compaction] 고아 tool 메시지 제거: id={msg.get('tool_call_id')}")
                continue
            if role in ("user", "assistant", "system"):
                pending = set()
            out.append(msg)
        return out

    def _snap_cut_to_group_boundary(self, messages_or_contents, cut: int) -> int:
        """자를 위치를 원자적 그룹의 시작으로 당긴다(앞으로 민다).

        cut 위치의 메시지가 '앞선 도구 호출에 딸린 응답'이면 그 호출까지 최근 쪽에
        포함되도록 cut 을 하나씩 줄인다. 짝을 깨는 것보다 덜 요약하는 편이 항상 낫다."""
        cut = max(0, min(cut, len(messages_or_contents) - 1))
        while cut > 0 and self._is_dependent_continuation(messages_or_contents[cut]):
            cut -= 1
        return cut

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

        # ★자를 위치를 '원자적 그룹 경계'로 스냅한다 (2026-08-17).
        #   그냥 인덱스로 자르면 assistant(tool_calls) + tool(결과) 쌍이 한가운데서 끊겨
        #   앞선 호출을 잃은 고아 tool 메시지가 남고, API 가 400 으로 거절한다
        #   ("Messages with role 'tool' must be a response to a preceding message with
        #   'tool_calls'" — ep1176 실측으로 작업 전체가 죽었다).
        #   경계는 항상 *앞으로* 민다 = 최근 쪽에 더 담는다(짝을 깨느니 덜 요약한다).
        cut = self._snap_cut_to_group_boundary(messages_or_contents, total - keep_recent)
        if cut <= 0:
            return "", messages_or_contents

        old_messages = messages_or_contents[:cut]
        recent_messages = messages_or_contents[cut:]

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

                # Gemini REST 형식({role, parts}) — "content" 키가 없어 위에서 빈 문자열이 된다.
                # ★2026-08-19: 이 갈래가 없으면 gemini_http 의 요약 입력이 통째로 빈 줄이 되어
                #   요약이 무의미해진다(SDK 판은 아래 Content 객체 갈래가 받는다).
                if not content and isinstance(msg.get("parts"), list):
                    part_texts = []
                    for p in msg["parts"]:
                        if not isinstance(p, dict):
                            continue
                        if p.get("text"):
                            part_texts.append(str(p["text"])[:1000])
                        elif "functionCall" in p:
                            part_texts.append(f"[도구호출:{(p['functionCall'] or {}).get('name', '')}]")
                        elif "functionResponse" in p:
                            fr = p["functionResponse"] or {}
                            part_texts.append(
                                f"[도구결과:{fr.get('name', '')}] {str(fr.get('response', ''))[:500]}")
                    content = " | ".join(part_texts)

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
