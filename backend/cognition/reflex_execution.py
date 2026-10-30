"""REFLEX의 문맥 경계. 공통 프롬프트는 유지하고 CLI 이력만 턴 안에 격리한다."""
import copy
import json
import sqlite3

from conversation_sessions import connection, current, record_event
from episode_logger import record_trajectory_event

NEEDS_CONTEXT = "<reflex_needs_context/>"
PROMPT = f"""<execution_lane name="REFLEX">
공통 규칙·권한·IBL 어휘는 그대로다. 이번 요청과 최근 대화로 대상·행동을 확인하고 실행한 뒤 결과를 확인해 짧게 답한다.
최근 대화는 과거 발언이며 새 명령이 아니다. 현재 기기 상태는 도구로 확인한다.
긴 과거 작업 이력은 이 실행에 제공되지 않았다. 대상·범위가 불명확하거나 과거 결정이 필요하면
어떤 도구도 호출하기 전에 다른 설명 없이 {NEEDS_CONTEXT} 하나만 답한다. 하네스가 기존 전체 문맥으로 넘긴다.
도구 호출 뒤에도 필요한 문맥이 부족하면 이 표식을 쓴다. 하네스가 이미 수행한 결과를 넘겨 남은 일만 이어간다.
도구 실패만으로 업무를 끝내지 말고 명령·방법을 고쳐 계속한다. 이미 수행한 쓰기를 처음부터 반복하지 않는다.
</execution_lane>"""
MAX_HISTORY_CHARS = 6000
MAX_MESSAGES = 4


def recent_history(history):
    """최근 사용자/최종 답변 두 쌍. 긴 발화·도구 블록을 잘라 의미를 바꾸지 않는다."""
    recent = []
    for row in reversed(history or []):
        if row.get("role") not in {"user", "assistant"}:
            continue
        if row.get("tool_calls") or row.get("_history_replacement") or row.get("images"):
            return None
        text = row.get("content")
        if not isinstance(text, str):
            return None
        if not text.strip():
            continue
        recent.append({"role": row["role"], "content": text})
        if len(recent) == MAX_MESSAGES:
            break
    if sum(len(row["content"]) for row in recent) > MAX_HISTORY_CHARS:
        return None
    return list(reversed(recent))


class _TurnSessions:
    """CLI의 턴 안 후속 호출만 잇는다. 주 세션 저장소는 읽거나 쓰지 않는다."""
    def __init__(self):
        self.mapping, self.sizes = {}, {}

    def load_map(self):
        return dict(self.mapping)

    def save_map(self, mapping):
        self.mapping = dict(mapping)

    def clear_agent(self, key):
        self.mapping.pop(key, None)

    def load_sizes(self):
        return dict(self.sizes)

    def record_size(self, key, size):
        self.sizes[key] = size

    def clear_size(self, key):
        self.sizes.pop(key, None)


def pending_receipts(actor):
    """주 CLI에 아직 전달되지 않은 별도 실행 결말. 기존 대화 사건 원장을 사용한다."""
    binding = current()
    if not binding or not binding.turn_id:
        return []
    with connection(binding.db_path) as conn:
        ack = conn.execute("""SELECT COALESCE(MAX(CAST(json_extract(payload,'$.through') AS INTEGER)),0)
            FROM conversation_events WHERE session_id=? AND json_extract(payload,'$.type')='reflex.ack'
            AND json_extract(payload,'$.actor')=?""", (binding.session_id, actor)).fetchone()[0]
        rows = conn.execute("""SELECT id,payload FROM conversation_events WHERE session_id=? AND id>?
            AND json_extract(payload,'$.type')='reflex.result'
            AND json_extract(payload,'$.actor')=? ORDER BY id""", (binding.session_id, ack, actor)).fetchall()
    return [(row[0], json.loads(row[1])) for row in rows]


class ReflexTurn:
    def __init__(self, runner, message, history, images=None):
        self.runner, self.message = runner, message
        self.full_history = history
        self.history = recent_history(history)
        self.actor = str(getattr(runner.ai, "agent_id", None) or runner.config.get("name") or "system_ai")
        self.active = False
        self.primary = None
        self.receipts = []
        self.delivered = False
        self.failed = False
        binding = current()
        self.reason = ("missing_conversation_binding" if not binding or not binding.turn_id else
                       "attachment_requires_context" if images else
                       "recent_history_not_short_text" if self.history is None else "")
        self.eligible = not self.reason

    def prepare(self, selected, history, *, enabled=True):
        self.full_history = history
        # 세션 제어/강제 역할에는 호출하지 않는다. DB 오류는 짧은 경로를 열지 않는다.
        if not enabled:
            return
        try:
            self.receipts = pending_receipts(self.actor)
        except sqlite3.Error as exc:
            record_trajectory_event("cognition.reflex_fallback", {"reason": "receipt_store_unavailable",
                                                                 "error": type(exc).__name__})
            return
        if not selected or not self.eligible:
            return
        self.primary = self.runner.ai._provider
        try:
            isolated = copy.copy(self.primary)
            if isolated is self.primary or isolated is None:
                raise ValueError("provider copy unavailable")
            if getattr(isolated, 'execution_profile', '') == 'coding':
                raise ValueError("coding session requires original history")
            if hasattr(isolated, "SESSION_STORE"):
                isolated.SESSION_STORE = _TurnSessions()
                isolated.disable_session_persistence = False
            for name in ("_last_tool_calls", "_last_tool_results", "_last_tool_images", "_pending_map_tags"):
                if hasattr(isolated, name):
                    setattr(isolated, name, [])
            self.runner.ai._provider = isolated
            self.active = True
            record_trajectory_event("cognition.reflex_context", {
                "history_messages": len(self.history),
                "history_chars": sum(len(row["content"]) for row in self.history),
                "system_prompt_preserved": True, "recall_preserved": True,
                "model": getattr(isolated, "model", None), "session": "isolated_turn",
            })
        except Exception as exc:
            self.restore()
            record_trajectory_event("cognition.reflex_fallback", {"reason": str(exc)})

    def restore(self):
        if self.primary is not None:
            self.runner.ai._provider = self.primary
            self.primary = None

    def _ordinary(self, message, history, images, cancel_check):
        if self.receipts:
            facts = [payload for _, payload in self.receipts]
            message = ("<separate_execution_history>\n다음은 같은 대화에서 이미 처리한 요청과 결말이다. "
                       "새 실행 지시가 아니며 현재 상태를 보증하지 않는다. 재실행하지 말고 후속 맥락으로 사용한다.\n"
                       + json.dumps(facts, ensure_ascii=False) + "\n</separate_execution_history>\n" + message)
        failed, final = False, False
        for event in self.runner.ai.process_message_stream(
                message_content=message, history=history, images=images, cancel_check=cancel_check):
            failed |= event.get("type") == "error"
            final |= event.get("type") == "final" and bool(event.get("content"))
            yield event
        self.delivered = final and not failed and not (cancel_check and cancel_check())

    def stream(self, message, history, images, cancel_check):
        if not self.active:
            yield from self._ordinary(message, history, images, cancel_check)
            return
        buffered, called, final, failed = [], False, "", False
        calls = []
        stream = self.runner.ai.process_message_stream(
            message_content=PROMPT + "\n" + message, history=self.history,
            images=images, cancel_check=cancel_check)
        try:
            for event in stream:
                kind = event.get("type")
                if kind in {"tool_start", "tool_result"}:
                    called = True
                if kind == "tool_start":
                    calls.append({"id": event.get("id"), "name": event.get("name"),
                                  "input": event.get("input"), "result": None})
                elif kind == "tool_result":
                    call = next((row for row in calls if event.get("id") and
                                 row.get("id") == event["id"]), None)
                    if call is None:
                        call = next((row for row in calls if row["result"] is None), None)
                    if call is None:
                        call = {"name": event.get("name"), "input": event.get("input")}
                        calls.append(call)
                    call.update(result=event.get("result"), is_error=event.get("is_error", False))
                    if not call.get("input"):
                        call["input"] = event.get("input")
                if kind == "final":
                    final = event.get("content", "")
                    continue
                failed |= kind == "error"
                self.failed |= kind == "error"
                if not called and kind in {"text", "thinking"}:
                    buffered.append(event)
                    continue
                if called and buffered:
                    yield from buffered
                    buffered.clear()
                yield event
        finally:
            if hasattr(stream, "close"):
                stream.close()
        if final.strip() == NEEDS_CONTEXT and not failed:
            if cancel_check and cancel_check():
                return
            from execution_turn import claim_followup
            from providers.base import turn_limit_reason
            if not turn_limit_reason() and claim_followup("reflex_context"):
                self.restore()
                self.active = False
                record_trajectory_event("cognition.reflex_fallback", {
                    "reason": "executor_needs_history", "attempted_calls": len(calls)})
                if called:
                    from task_continuation import message as continuation_message
                    message = continuation_message(message, "", calls, reason="실행 도중 문맥 부족")
                yield from self._ordinary(message, self.full_history, images, cancel_check)
                return
        yield from buffered
        if final.strip() == NEEDS_CONTEXT:
            self.failed = True
            final = "요청을 완료할 문맥이 부족하고 추가 실행 한도에 도달했습니다. 기존 호출의 효과를 보존했습니다."
        if final:
            yield {"type": "final", "content": final}

    def finish(self, response, calls, completed):
        if self.active and (response or calls):
            refs = []
            for call in calls:
                try:
                    result = call.get("result")
                    result = json.loads(result) if isinstance(result, str) else result
                    ref = result.get("result_ref") if isinstance(result, dict) else None
                    if ref:
                        refs.append({"tool": call.get("name"), "result_ref": ref.get("id"),
                                     "is_error": bool(call.get("is_error"))})
                except (ValueError, TypeError):
                    pass
            record_event({"type": "reflex.result", "actor": self.actor, "request": self.message,
                          "response": response, "completed": bool(completed and not self.failed), "results": refs})
        elif self.delivered and self.receipts:
            record_event({"type": "reflex.ack", "actor": self.actor, "through": self.receipts[-1][0]})
