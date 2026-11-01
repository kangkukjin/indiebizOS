"""의식의 수신 기록은 완료 전에도 남고, 중단·제공자 오류 뒤에도 회수할 수 있다."""
import json
import time
from types import SimpleNamespace

import pytest

import boot_paths  # noqa: F401
from providers.base import ProviderMetrics
from supervisor_runtime import StreamJournal, invoke
from test_conscious_supervisor import supervisor  # noqa: F401


def rows(supervisor):
    with (supervisor.store.directory / "events.jsonl").open() as stream:
        return [json.loads(line) for line in stream]


def install_agent(monkeypatch, stream):
    class Agent:
        def __init__(self, *args, **kwargs):
            self._provider = SimpleNamespace(metrics=ProviderMetrics())
            self.model, self.provider_name = "test", "test"

        def process_message_stream(self, *args, **kwargs):
            yield from stream()

    monkeypatch.setattr("ai_agent.AIAgent", Agent)
    monkeypatch.setattr("model_resolver.resolve", lambda *a: {})


@pytest.mark.parametrize("phase", ["plan", "plan_completion", "review", "reframe"])
def test_stream_is_recorded_before_completion_without_replacing_final(
        supervisor, monkeypatch, capsys, phase):
    def stream():
        yield {"type": "thinking", "content": "제공된 조건을 확인합니다."}
        live = [r for r in rows(supervisor) if r["kind"] == "model.stream"]
        assert live[-1]["role"] == "consciousness" and live[-1]["phase"] == phase
        assert live[-1]["call_id"]
        assert not any(r["kind"] == "model.finished" for r in rows(supervisor))
        yield {"type": "text", "content": "초안 "}
        yield {"type": "text", "content": "일부"}
        yield {"type": "progress", "stage": "계획 작성", "api_key": "secret-value"}
        yield {"type": "final", "content": '{"task_framing":"최종 규정"}'}

    install_agent(monkeypatch, stream)
    assert invoke(supervisor, "test", phase=phase) == '{"task_framing":"최종 규정"}'
    events = [r for r in rows(supervisor) if r["kind"] == "model.stream"]
    assert [r["event_type"] for r in events] == ["thinking", "text", "text", "progress"]
    contents = [supervisor.store.read_evidence(r["evidence"]["id"])["text"] for r in events]
    assert "".join(contents[1:3]) == "초안 일부"
    assert "secret-value" not in "".join(contents)
    assert "secret-value" not in capsys.readouterr().out
    assert events[-1]["elapsed_s"] >= events[0]["first_elapsed_s"] >= 0


@pytest.mark.parametrize("stop", ["deadline", "exception"])
def test_partial_text_survives_cancel_or_provider_exception(supervisor, monkeypatch, stop):
    from consciousness_agent import FramingContractError

    def stream():
        yield {"type": "text", "content": "받은 "}
        yield {"type": "text", "content": "계획 일부"}
        if stop == "deadline":
            supervisor.call_stop = {"kind": "deadline", "reason": "시간 한도"}
            yield {"type": "error", "content": "시간 한도"}
        else:
            raise RuntimeError("provider disconnected")

    install_agent(monkeypatch, stream)
    with pytest.raises(FramingContractError if stop == "deadline" else RuntimeError):
        invoke(supervisor, "test", phase="plan_completion")
    events = [r for r in rows(supervisor) if r["kind"] == "model.stream"]
    assert "".join(supervisor.store.read_evidence(r["evidence"]["id"])["text"]
                   for r in events) == "받은 계획 일부"
    assert all(r["phase"] == "plan_completion" for r in events)


def test_tiny_text_chunks_are_batched_without_loss(supervisor, monkeypatch):
    started = time.monotonic()
    clock = [started]
    monkeypatch.setattr("supervisor_runtime.time.monotonic", lambda: clock[0])
    journal = StreamJournal(supervisor, started)
    for _ in range(100):
        journal.observe({"type": "text", "content": "가"})
    assert len([r for r in rows(supervisor) if r["kind"] == "model.stream"]) == 1
    clock[0] += 5
    journal.observe({"type": "text", "content": "나"})
    journal.flush()
    events = [r for r in rows(supervisor) if r["kind"] == "model.stream"]
    assert len(events) == 2
    assert sum(r["chunks"] for r in events) == 101
    assert "".join(supervisor.store.read_evidence(r["evidence"]["id"])["text"]
                   for r in events) == "가" * 100 + "나"


@pytest.mark.parametrize("summary", [None, "공개된 진행 요약"])
def test_codex_reasoning_receipt_reaches_consciousness_log(supervisor, monkeypatch, summary):
    from providers import get_provider
    provider = get_provider("codex", api_key="", model="test", system_prompt="test", tools=[])
    item = {"id": "reasoning-1", "type": "reasoning"}
    if summary is not None:
        item["summary"] = [{"text": summary}]

    def stream():
        for event, _ in provider._translate_stream_event(
                {"type": "item.completed", "item": item}, "", time.time()):
            yield event
        yield {"type": "final", "content": "{}"}

    install_agent(monkeypatch, stream)
    assert invoke(supervisor, "test", phase="plan_completion") == "{}"
    event = next(r for r in rows(supervisor) if r["kind"] == "model.stream")
    body = json.loads(supervisor.store.read_evidence(event["evidence"]["id"])["text"])
    if summary is None:
        assert body["type"] == "progress"  # 본문 수신으로 세어 재시도를 막지 않는다.
        assert body["detail"] == "reasoning 항목 수신 — 공개 요약 없음"
        assert body["item_id"] == "reasoning-1"
    else:
        assert body["type"] == "thinking" and body["content"] == summary


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
