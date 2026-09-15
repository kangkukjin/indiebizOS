"""능력 주장 확인의 읽기 전용 원자. 모델 도구·재시도·세션 재개는 없다."""
import json
import queue
import re
import threading
import time

from execution_workers import bind_context

# 시간 초과 뒤 남은 네트워크 요청도 출력 상한을 가지며, 동시 요청 수는 유한하다.
_slots = threading.BoundedSemaphore(4)


def bounded_read(fn, timeout_s, cancel_check=None):
    """부작용 없는 조회만 실행한다. 대기 취소가 다른 턴의 공유 클라이언트를 닫지 않는다."""
    if not _slots.acquire(blocking=False):
        raise TimeoutError("capability check capacity")
    result = queue.Queue(maxsize=1)

    def run():
        try:
            result.put((True, fn()))
        except Exception as exc:
            result.put((False, exc))
        finally:
            _slots.release()

    threading.Thread(target=bind_context(run), name="capability-read", daemon=True).start()
    deadline = time.monotonic() + timeout_s
    while True:
        if cancel_check and cancel_check():
            raise TimeoutError("capability check cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("capability check deadline")
        try:
            ok, value = result.get(timeout=min(remaining, 0.1))
        except queue.Empty:
            continue
        if not ok:
            raise value
        return value


def judge_once(prompt, system_prompt, limits, cancel_check=None):
    """설정된 classify 모델로 API 요청 하나. 지원되지 않는 전송은 명시 실패로 통과시킨다."""
    if len((prompt + system_prompt).encode("utf-8")) > limits["input_bytes"]:
        raise ValueError("capability judgment input limit")

    def call():
        from consciousness_agent import _resolve_oneshot_provider
        from episode_logger import _current_role
        from model_call_context import call_scope, observe_input, set_purpose, reset_purpose
        provider = _resolve_oneshot_provider("classify")
        if provider is None:
            raise RuntimeError("capability classifier unavailable")
        provider = provider.oneshot_view()
        provider.system_prompt = system_prompt
        provider.agent_role = "oneshot:classify"
        role = _current_role.set("oneshot:classify")
        purpose = set_purpose("capability_guard")
        try:
            with call_scope(provider):
                observe_input(provider, {"message": prompt, "history": []})
                provider._notify_round(1, 1)
                started = time.monotonic()
                text, usage = _request(provider, prompt, system_prompt, limits)
                provider.metrics.record_usage((time.monotonic() - started) * 1000, usage,
                                              label=type(provider).__name__)
                return text
        finally:
            reset_purpose(purpose)
            _current_role.reset(role)

    return bounded_read(call, limits["judge_timeout_s"], cancel_check)


def _request(provider, prompt, system, limits):
    """일반 agentic loop를 부르지 않는다: 빈 출력/길이 초과도 두 번째 API 호출 금지."""
    timeout, maximum = limits["judge_timeout_s"], limits["output_tokens"]
    client = getattr(provider, "_client", None)
    if getattr(provider, "_genai_client", None) is not None:
        types = provider._genai_types
        config = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=maximum,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            http_options=types.HttpOptions(timeout=int(timeout * 1000),
                                           retry_options=types.HttpRetryOptions(attempts=1)))
        response = provider._genai_client.models.generate_content(
            model=provider.model, contents=prompt, config=config)
        return response.text, response.usage_metadata
    if hasattr(client, "chat") and hasattr(client, "with_options"):
        params = {"model": provider.model, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": maximum}
        off = getattr(provider, "_thinking_off_params", lambda: {})()
        if off:
            params["extra_body"] = off
        response = client.with_options(timeout=timeout, max_retries=0).chat.completions.create(**params)
        return response.choices[0].message.content, response.usage
    if hasattr(client, "messages") and hasattr(client, "with_options"):
        response = client.with_options(timeout=timeout, max_retries=0).messages.create(
            model=provider.model, max_tokens=maximum, system=system,
            messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in response.content), response.usage
    # 네이티브 CLI 등의 무제한 생성으로 폴백하지 않는다. 실행 모델은 그대로다.
    raise RuntimeError("capability classifier has no bounded API transport")


def body_snapshot(ai, queries, allowed_set=None):
    """현재 실행자의 도구와 활성 사전 한 번 조회. 무검색 결과는 능력 부재의 증거가 아니다.

    모델이 생성한 셸·IBL·경로를 실행하지 않는다. 세계의 명사는 질의 데이터로만 받는다.
    """
    from ibl_registry import load_nodes_installed, self_can_run
    from ibl_access import check_node_access
    from common.value_semantics import text_match
    terms = {t for q in queries for t in re.findall(r"[\w-]{2,}", q)}
    provider = getattr(ai, "_provider", None)
    tools = getattr(provider, "tools", None)
    if tools is None:
        tools = getattr(ai, "tools", [])
    native = [{"name": t.get("name", ""), "description": str(t.get("description", ""))[:700]}
              for t in tools or [] if isinstance(t, dict)]
    entries = []
    # 사전은 실제 실행 도구(IBL 브리지)와 별개다. 항목 존재를 권한/접근 성공으로 승격하지 않는다.
    for node, config in (load_nodes_installed() or {}).get("nodes", {}).items():
        if not check_node_access(node, allowed_set):
            continue
        for action, cfg in (config.get("actions") or {}).items():
            if self_can_run(node, action, cfg):
                entries.append({"name": f"{node}:{action}",
                                "description": str(cfg.get("description", ""))[:700]})

    def relevant(rows):
        scored = [(sum(text_match("contains", json.dumps(r, ensure_ascii=False), t) for t in terms), r)
                  for r in rows]
        return [r for score, r in sorted(scored, key=lambda pair: -pair[0]) if score > 0][:8]

    return {"source": "current_executor_and_active_registry", "observed_at": time.time(),
            "native_tools": relevant(native), "dictionary_routes": relevant(entries),
            "native_tool_names": [r["name"] for r in native][:80],
            "scope": "기능 항목의 존재만 확인. 특정 파일·URL 접근, 실행 성공, 외부 프로그램 옵션은 미확인.",
            "absence_is_unknown": True}
