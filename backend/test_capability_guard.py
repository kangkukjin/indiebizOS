"""무능 단정→확인→실행/정직한 종료, 공통 final·기록·예산 경계의 회귀."""
import json
import threading
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import associative_recall
import pytest

import capability_guard as cg
from test_conscious_supervisor import supervisor, verdict  # noqa: F401

EYES = "저는 눈이 없어서 이미지를 볼 수 없습니다."
FFMPEG = "ffmpeg에는 자막 기능이 없습니다."
META = "'이미지를 볼 수 없습니다'라는 응답은 잘못됐습니다."
UNKNOWN = "이 환경에서 자막 기능의 가능 여부는 아직 확인하지 못했습니다."
LIMITED = "이 파일은 현재 계정의 읽기 권한이 없어 열 수 없습니다."


def drain(stream):
    events = []
    while True:
        try:
            events.append(next(stream))
        except StopIteration as stop:
            return events, stop.value


def claim(quote, status="unsupported", evidence_ids=None):
    return {"quote": quote, "status": status, "target": "이미지 열람",
            "lookup_terms": ["이미지", "image"], "evidence_ids": evidence_ids or []}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(cg, "config", lambda: dict(cg.DEFAULTS))
    monkeypatch.setattr(cg, "log", lambda *a, **kw: None)
    monkeypatch.setattr(cg, "evidence_ref", lambda _: {"id": "fixture", "chars": 0})
    monkeypatch.setattr(cg, "judge_once", lambda *a, **kw: pytest.fail("unexpected model call"))
    monkeypatch.setattr(cg, "body_snapshot", lambda *a, **kw: pytest.fail("unexpected lookup"))


def install_judge(monkeypatch, replies):
    inputs = []
    replies = iter(replies)

    def judge(prompt, *args):
        inputs.append(json.loads(prompt))
        result = next(replies)
        if isinstance(result, Exception):
            raise result
        return json.dumps({"claims": result}, ensure_ascii=False)

    monkeypatch.setattr(cg, "judge_once", judge)
    return inputs


def install_lookup(monkeypatch, routes=True):
    queries = []

    def lookup(ai, terms, allowed):
        queries.append((ai, terms, allowed))
        return {"native_tools": [{"name": "read_image"}] if routes else [],
                "scope": "기능 항목만 확인", "absence_is_unknown": True}

    monkeypatch.setattr(cg, "body_snapshot", lookup)
    return queries


@pytest.mark.parametrize("text", [EYES, FFMPEG, META, UNKNOWN, LIMITED,
                                  "I cannot read this file.", "이미지 처리는 지원되지 않습니다."])
def test_candidate_detection(text):
    assert cg.CANDIDATE.search(text)


def test_normal_answer_costs_no_calls():
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    events, response = drain(guard.adopt(NS(), "질문", "정상 응답입니다.", []))
    assert response == "정상 응답입니다." and events == []
    assert guard.judgments == guard.lookups == guard.resumes == 0


@pytest.mark.parametrize("text,status,trace,refs", [
    (META, "meta", [], []), (UNKNOWN, "unknown", [], []),
    (LIMITED, "limited", [{"name": "read", "input": {"path": "/a"},
                           "result": "Permission denied", "is_error": True}], ["e0"]),
])
def test_meta_unknown_and_observed_limit_do_not_resume(monkeypatch, text, status, trace, refs):
    install_judge(monkeypatch, [[claim(text, status, refs)]])
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    _, response = drain(guard.adopt(NS(), "질문", text, trace))
    assert response == text and guard.judgments == 1 and guard.lookups == guard.resumes == 0


def test_no_eyes_checks_body_and_resumes_original_task(monkeypatch):
    install_judge(monkeypatch, [[claim(EYES)]])
    lookups = install_lookup(monkeypatch)
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    ai = NS()

    def resume(snapshot, claims):
        assert snapshot["native_tools"] and claims[0]["quote"] == EYES
        yield {"type": "tool_start", "name": "read_image"}
        return "이미지에는 고양이가 있습니다."

    events, response = drain(guard.adopt(NS(ai=ai), "이미지를 설명해줘", EYES, [], resume=resume))
    assert response == "이미지에는 고양이가 있습니다."
    assert events[-1]["name"] == "read_image" and len(lookups) == 1
    assert guard.judgments == guard.lookups == guard.resumes == 1


def test_ffmpeg_overgeneralization_is_replaced_not_appended(monkeypatch):
    install_judge(monkeypatch, [[claim(FFMPEG)], [claim(UNKNOWN, "unknown")]])
    install_lookup(monkeypatch)
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))

    def resume(*args):
        yield {"type": "thinking", "content": "확인"}
        return UNKNOWN

    _, result = drain(guard.adopt(NS(ai=NS()), "자막을 넣어줘", FFMPEG, [], resume=resume))
    assert result == UNKNOWN and FFMPEG not in result
    assert (guard.judgments, guard.lookups, guard.resumes) == (2, 1, 1)


def test_second_unsupported_response_ends_without_third_model_call(monkeypatch):
    install_judge(monkeypatch, [[claim(EYES)], [claim(EYES)]])
    install_lookup(monkeypatch)
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))

    def resume(*args):
        yield from ()
        return "완료한 부분은 보존합니다.\n" + EYES

    _, result = drain(guard.adopt(NS(ai=NS()), "질문", EYES, [], resume=resume))
    assert EYES not in result and result.startswith("완료한 부분은 보존합니다.")
    assert "확정하지 못했습니다" in result
    assert (guard.judgments, guard.lookups, guard.resumes) == (2, 1, 1)
    assert drain(guard.adopt(NS(), "질문", result, []))[1] == result
    assert guard.judgments == 2


def test_judgment_failure_preserves_original_and_does_not_probe(monkeypatch):
    install_judge(monkeypatch, [TimeoutError()])
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    assert drain(guard.adopt(NS(), "질문", EYES, []))[1] == EYES
    assert guard.lookups == guard.resumes == 0


def test_lookup_failure_does_not_prove_inability(monkeypatch):
    install_judge(monkeypatch, [[claim(EYES)], []])
    monkeypatch.setattr(cg, "body_snapshot", lambda *a: (_ for _ in ()).throw(OSError()))
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    result = drain(guard.adopt(NS(ai=NS()), "질문", EYES, []))[1]
    assert EYES not in result and "확정하지 못했습니다" in result
    assert guard.evidence[0]["is_error"] and guard.resumes == 0


def test_cancelled_turn_never_calls_model():
    guard = cg.CapabilityGuard(limits=dict(cg.DEFAULTS))
    assert drain(guard.adopt(NS(), "질문", EYES, [], cancel_check=lambda: True))[1] == EYES
    assert guard.judgments == 0


def test_long_response_tail_is_examined_with_bounded_input():
    text = "완료 내용\n" * 9000 + EYES
    data = cg.packet("질문", text, [], cg.DEFAULTS)
    assert EYES in data["response"] and data["response_excerpt"]
    assert len((json.dumps(data, ensure_ascii=False) + cg.POLICY).encode()) <= cg.DEFAULTS["input_bytes"]


@pytest.mark.parametrize("rows", [[claim("원문에 없는 문장")], [claim(EYES, "limited", ["fake"])],
                                 [claim(EYES, "limited")]])
def test_fabricated_span_or_receipt_is_not_a_valid_verdict(rows):
    with pytest.raises(ValueError):
        cg.parse(json.dumps({"claims": rows}), EYES, [])


def test_bounded_read_times_out_and_releases_capacity_after_completion():
    from capability_guard_runtime import bounded_read
    done = threading.Event()
    try:
        with pytest.raises(TimeoutError):
            bounded_read(lambda: done.wait(2), 0.02)
    finally:
        done.set()
    assert bounded_read(lambda: "ok", 1) == "ok"


def test_body_snapshot_reads_only_current_allowed_registry(monkeypatch):
    from capability_guard_runtime import body_snapshot
    monkeypatch.setattr("ibl_registry.load_nodes_installed", lambda: {"nodes": {
        "sense": {"actions": {"image": {"description": "이미지 읽기"}}},
        "private": {"actions": {"image": {"description": "비공개 이미지"}}}}})
    monkeypatch.setattr("ibl_registry.self_can_run", lambda *a: True)
    ai = NS(_provider=NS(tools=[{"name": "read_image", "description": "이미지 읽기"}]))
    result = body_snapshot(ai, ["이미지"], {"sense"})
    assert [r["name"] for r in result["dictionary_routes"]] == ["sense:image"]
    assert result["absence_is_unknown"] and result["native_tools"]


@pytest.mark.parametrize("route", ["execute", "clarify", "criteria", "no_criteria", "legacy"])
def test_pipeline_adopts_one_final_and_saves_same_body(supervisor, monkeypatch, route):
    from agent_pipeline import CognitivePipelineMixin
    saved, requests, traces = [], [], []
    corrected = "이미지를 확인했습니다. 고양이가 있습니다."
    install_judge(monkeypatch, [[claim(EYES)]])
    install_lookup(monkeypatch)

    class Runner(CognitivePipelineMixin):
        config = {"name": "worker"}
        project_path = supervisor.project_path
        _associate = associative_recall.stub()
        _decide_request_type = lambda *a: ("EXECUTE" if route == "execute" else "THINK", None)
        _run_consciousness_or_reuse = lambda *a, **kw: {"task_framing": "이미지 확인",
            **({"achievement_criteria": "이미지 설명"} if route in {"criteria", "legacy"} else {})}
        _consciousness_needs_repair = lambda *a: False
        _consciousness_clarification = lambda *a: EYES if route == "clarify" else None
        _extract_achievement_criteria = lambda *a: "이미지 설명" if route in {"criteria", "legacy"} else ""
        _refresh_execution_prompt = lambda *a, **kw: "이미지를 설명해줘"
        _apply_consciousness_to_history = lambda self, h, c: h
        _after_response_async = lambda self, message, response, **kw: saved.append(response)

        def _run_goal_evaluation_stream(self, **kwargs):
            yield {"type": "final", "content": EYES}
            return EYES

    runner = Runner()

    def execute(**kwargs):
        requests.append(kwargs)
        resuming = "current_capabilities" in kwargs["message_content"]
        text = corrected if resuming else ("평가 전 정상 본문" if route == "legacy" else EYES)
        yield {"type": "text", "content": text}
        if resuming:
            yield {"type": "tool_start", "id": "image", "name": "read_image", "input": {"path": "fixture"}}
            yield {"type": "tool_result", "id": "image", "name": "read_image", "result": "고양이"}
        yield {"type": "final", "content": text}

    runner.ai = NS(_provider=None, process_message_stream=execute)
    supervisor.runner = runner
    monkeypatch.setattr("supervision_bus.current", lambda: None if route == "legacy" else supervisor)
    monkeypatch.setattr("pursuit_bind.prepare", lambda: ("", False))
    monkeypatch.setattr("pursuit_bind.refresh_memory", lambda mem: mem)
    monkeypatch.setattr("pursuit_bind.finish", lambda *a, **kw: None)
    monkeypatch.setattr("reframe.open_turn", lambda *a, **kw: None)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c))
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda k, d: traces.append((k, d)))
    if route == "legacy":
        install_judge(monkeypatch, [[claim(EYES)], []])
    events = list(runner._cognitive_stream_body("이미지를 설명해줘", []))
    assert not [e for e in events if e["type"] == "error"], events
    finals = [e["content"] for e in events if e["type"] == "final"]
    assert len(finals) == 1 and finals == saved
    assert EYES not in finals[0]
    if route != "legacy":
        assert finals == [corrected]
        assert sum("current_capabilities" in r["message_content"] for r in requests) == 1
        meta = next(e for e in events if e["type"] == "_turn_meta")
        assert any(t["tool_name"] == "read_image" and t["success"] for t in meta["tool_calls"])
    else:
        assert len(requests) == 1  # 평가 승인/보완 뒤에는 새 원작업 실행 금지


def test_final_filter_closes_child_when_consumer_cancels():
    closed = []

    def child():
        try:
            yield {"type": "thinking", "content": "진행"}
            yield {"type": "final", "content": EYES}
        finally:
            closed.append(True)

    inner = child()
    outer = cg.defer_final(inner)
    assert next(outer)["type"] == "thinking"
    outer.close()
    assert closed == [True]


def test_judge_api_enforces_one_call_output_timeout_and_same_turn_usage(monkeypatch):
    import copy
    from capability_guard_runtime import judge_once
    from providers.base import ProviderMetrics, turn_token_scope, read_turn_tokens
    calls = []

    class Client:
        def __init__(self):
            self.chat = NS(completions=NS(create=self.create))

        def with_options(self, **kw):
            calls.append(("options", kw))
            return self

        def create(self, **kw):
            calls.append(("create", kw))
            return NS(choices=[NS(message=NS(content='{"claims":[]}'))],
                      usage=NS(prompt_tokens=4, completion_tokens=5))

    provider = NS(model="fixture", _client=Client(), metrics=ProviderMetrics(),
                  _thinking_off_params=lambda: {"thinking": {"type": "disabled"}},
                  _notify_round=lambda *a: None)
    provider.oneshot_view = lambda: copy.copy(provider)
    monkeypatch.setattr("consciousness_agent._resolve_oneshot_provider", lambda role: provider)
    with turn_token_scope("fixture", "capability-usage"):
        assert judge_once("{}", "判定", cg.DEFAULTS) == '{"claims":[]}'
        assert read_turn_tokens() == 9
    assert calls[0] == ("options", {"timeout": 15.0, "max_retries": 0})
    assert len(calls) == 2
    params = calls[1][1]
    assert params["max_tokens"] == 1600 and "tools" not in params and "stream" not in params


def test_oversized_judge_input_is_rejected_before_provider_selection(monkeypatch):
    from capability_guard_runtime import judge_once
    monkeypatch.setattr("consciousness_agent._resolve_oneshot_provider", lambda role: pytest.fail("provider selected"))
    with pytest.raises(ValueError, match="input limit"):
        judge_once("가" * cg.DEFAULTS["input_bytes"], cg.POLICY, cg.DEFAULTS)


def test_websocket_saves_and_sends_the_adopted_body(monkeypatch):
    import asyncio
    import chat_runs
    import chat_streams as streams
    import episode_logger as episodes
    import system_ai_core as core
    import system_ai_memory as memory
    from chat_runs import ChatRuns
    from websocket_manager import WebSocketManager
    from execution_workers import create_executor
    install_judge(monkeypatch, [[claim(EYES)], []])
    install_lookup(monkeypatch, routes=False)
    sent, saved = [], []
    manager = WebSocketManager()

    async def send(client, payload):
        sent.append(payload)

    runner = NS(ai=NS())

    def stream(*args, **kwargs):
        yield {"type": "text", "content": EYES}
        result = yield from cg.CapabilityGuard(limits=dict(cg.DEFAULTS)).adopt(
            runner, "이미지 설명", EYES, [], cancel_check=kwargs["cancel_check"])
        yield {"type": "final", "content": result}

    runner.cognitive_stream = stream
    monkeypatch.setattr(chat_runs, "registry", ChatRuns())
    monkeypatch.setattr(streams, "manager", manager)
    monkeypatch.setattr(manager, "send_message", send)
    monkeypatch.setattr(episodes.EpisodeLogger, "start_episode", lambda *a, **kw: None)
    monkeypatch.setattr(episodes.EpisodeLogger, "end_episode", lambda: None)
    monkeypatch.setattr("model_resolver.resolve", lambda role: {"provider": "ollama", "model": "fixture", "api_key": ""})
    monkeypatch.setattr(core, "get_system_ai_runner", lambda: runner)
    monkeypatch.setattr(memory, "create_task", lambda **kw: None)
    monkeypatch.setattr(memory, "delete_task", lambda *a: None)
    monkeypatch.setattr(memory, "get_task", lambda *a: None)
    monkeypatch.setattr(memory, "save_conversation", lambda *a, **kw: saved.append(a))
    monkeypatch.setattr(memory, "get_history_for_ai", lambda **kw: [])
    with create_executor("test-capability-chat", max_workers=1) as pool:
        monkeypatch.setattr(streams, "executor", pool)
        asyncio.run(streams.handle_system_ai_chat_stream("fixture", {"message": "이미지 설명"}))
    adopted = next(m["content"] for m in sent if m["type"] == "response")
    assert EYES not in adopted and "확정하지 못했습니다" in adopted
    assert ("assistant", adopted) in saved
    assert sent[-1]["type"] == "end"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
