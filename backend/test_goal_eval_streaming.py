"""최종 비교는 상태를 먼저 전달하고 한 번 평가한 뒤 원래 결과를 반환한다."""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재

from cognitive_eval import CognitiveEvalMixin


class _FakeAI:
    """재실행 에이전트 대역 — 도구 두 번 쓰고 새 응답을 낸다."""

    def __init__(self):
        self.stream_calls = 0

    def process_message_stream(self, message_content, history=None,
                               images=None, cancel_check=None):
        self.stream_calls += 1
        yield {"type": "text", "content": "다시 보겠습니다."}
        yield {"type": "tool_start", "name": "execute_ibl", "input": {"code": "[self:time]{}"}}
        yield {"type": "tool_result", "name": "execute_ibl", "result": "{}"}
        yield {"type": "final", "content": "보완된 응답"}

    # 옛 폴백이 되살아나면 여기가 불린다 — 되살아났는지 감시용.
    def get_last_tool_calls(self):
        raise AssertionError(
            "get_last_tool_calls 폴백이 되살아났다 — 스트리밍 재실행에서는 "
            "영영 안 채워지는 속성이라 이전 논스트림 호출의 잔여를 오적재한다."
        )


class _Runner(CognitiveEvalMixin):
    """평가자만 대역으로 갈아끼운 최소 러너."""

    def __init__(self, verdicts):
        self.ai = _FakeAI()
        self._verdicts = list(verdicts)  # [(achieved, feedback, severity), ...]
        self.logs = []

    def _log(self, msg):
        self.logs.append(msg)

    def _collect_created_files(self, response, tool_calls=None):
        return ""

    def _collect_visual_artifacts(self, response, tool_calls=None):
        return []

    def _evaluate_achievement(self, *a, **kw):
        return self._verdicts.pop(0)


def _drain(gen):
    """제너레이터를 소진하고 (이벤트들, 반환값)."""
    events = []
    while True:
        try:
            events.append(next(gen))
        except StopIteration as stop:
            return events, stop.value


def _run(runner, max_rounds=3):
    return _drain(runner._run_goal_evaluation_stream(
        user_message="보고서 써줘",
        criteria="보고서 파일이 실제로 생성될 것",
        initial_response="초안",
        history=[],
        consciousness_output={},
        max_rounds=max_rounds,
        tool_results=[],
        tool_calls=[{"name": "Bash", "input": {}, "result": "", "is_error": False}],
    ))


def test_achieved_한번에_통과하면_초안_그대로():
    runner = _Runner([(True, "", 0)])
    events, result = _run(runner)
    assert result == "초안"
    assert runner.ai.stream_calls == 0
    # 평가 자체도 50~90초 블로킹이므로 들어가기 전에 상태를 흘려야 한다
    assert any(e.get("type") == "thinking" for e in events), \
        "평가 진입 전 진행 상태가 없다 — 유휴 타이머가 리셋되지 않는다"


@pytest.mark.parametrize("reply,achieved,severity", [
    ("**ACHIEVED**\n확인", True, 0),
    ("먼저 설명합니다.\n## NOT_ACHIEVED\nSEVERITY: 3", False, 3),
    ("판정하지 못했습니다", None, 0), ("", None, 0),
])
def test_verdict_parser_distinguishes_unknown(reply, achieved, severity):
    from cognitive_eval import parse_eval_verdict
    assert parse_eval_verdict(reply) == (achieved, severity)


@pytest.mark.parametrize("reply", [None, "", "판정하지 못했습니다", RuntimeError("network failure")])
def test_model_failure_is_unknown_and_never_causes_retry_or_success_learning(tmp_path, monkeypatch, reply):
    from thread_context import get_goal_eval_outcome, clear_goal_eval_outcome
    from supervision_store import TurnStore
    import model_result_view
    import consciousness_agent
    store = TurnStore(tmp_path)
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    def model(*args, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(consciousness_agent, "system_ai_call", model)
    runner = _Runner([])
    # 실제 평가 입력·파서·루프를 지나고 네트워크 호출만 대체한다.
    runner._evaluate_achievement = CognitiveEvalMixin._evaluate_achievement.__get__(runner)
    events, result = _run(runner)
    assert runner.ai.stream_calls == 0
    assert result == "초안"
    outcome = get_goal_eval_outcome()
    assert outcome["status"] == "UNKNOWN" and not outcome["achieved"]
    review = json.loads((tmp_path / "review_status.json").read_text())
    assert review["status"] == "UNKNOWN" and review["learning"] == "deferred"
    assert store.read_evidence(review["response"]["id"])["text"] == "초안"
    # 기존 성공 경험 게이트가 UNKNOWN을 소비해 모델 증류 호출 전에 거절한다.
    from ibl_usage_rag import distill_experience
    assert distill_experience("unknown", [{"name": "execute_ibl", "result": "{}"}], 0) is False
    clear_goal_eval_outcome()


def test_evidence_collection_failure_is_unreviewed(tmp_path, monkeypatch):
    import model_result_view
    from supervision_store import TurnStore
    from thread_context import get_goal_eval_outcome, clear_goal_eval_outcome
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: TurnStore(tmp_path))
    runner = _Runner([])
    def broken(*args, **kwargs):
        raise OSError("artifact unavailable")
    monkeypatch.setattr("final_evaluator.Evaluator._collect_visual_artifacts", broken)
    _, result = _run(runner)
    assert result == "초안"
    assert "artifact unavailable" in get_goal_eval_outcome()["reason"]
    assert get_goal_eval_outcome()["status"] == "UNKNOWN"
    assert runner.ai.stream_calls == 0
    clear_goal_eval_outcome()














def test_중단이_평가루프에도_닿는다():
    """cancel_check 배선 — 옛 판은 평가 루프에 들어간 뒤 중단 버튼이 무력했다."""
    runner = _Runner([(True, "", 0)])
    events, result = _drain(runner._run_goal_evaluation_stream(
        user_message="x", criteria="y", initial_response="초안",
        history=[], consciousness_output={}, max_rounds=3,
        tool_results=[], tool_calls=[{"name": "Bash", "input": {}, "result": "", "is_error": False}],
        cancel_check=lambda: True,
    ))
    assert result == "초안"
    assert events == [], "중단 요청에도 평가자를 불렀다"
    assert any("중단" in m for m in runner.logs)


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))


@pytest.mark.parametrize('achieved', [True, False, None])
def test_final_result_comparison_is_one_call_even_with_extra_round_budget(achieved):
    runner = _Runner([(achieved, '판단', 0)])
    events, result = _run(runner, max_rounds=10)
    assert result == '초안' and runner.ai.stream_calls == 0
    assert runner._verdicts == []
    assert [e['type'] for e in events] == ['thinking']
