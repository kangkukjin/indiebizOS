"""목표평가(GoalEval) 재실행 구간 스트리밍 회귀 시험

사건(2026-08-22, 상상훈련 22회차 턴): 1라운드 응답이 화면에 나온 뒤 파이프라인이
`_run_goal_evaluation_loop` 블로킹 함수로 들어가 **10분간 이벤트 0** 을 냈다.
평가자 호출 91초 + 전면 재실행 595,995ms(도구 30여 회)가 전부 스트림 밖이라
화면에는 영원히 도는 스피너로 보였고, 그 침묵이 WS 유휴 타임아웃(600초)보다 길어
긴 턴은 NOT_ACHIEVED 를 받는 순간 타임아웃이 구조적으로 확정이었다.

여기서 단언하는 것은 "재실행이 도는 동안 무언가 흐른다"는 계약이다 —
봉투(반환값)만 보는 시험은 옛 판도 통과했다.

실행: cd indiebizOS && .venv/bin/python -m pytest backend/test_goal_eval_streaming.py
"""

import os
import sys

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


def test_재실행_구간이_침묵하지_않는다():
    """★본체: NOT_ACHIEVED → 재실행 동안 에이전트 이벤트가 그대로 흘러야 한다."""
    runner = _Runner([(False, "파일이 없다", 1), (True, "", 0)])
    events, result = _run(runner)

    assert result == "보완된 응답", "재실행 결과가 반환값으로 채택되지 않았다"
    assert runner.ai.stream_calls == 1

    types = [e.get("type") for e in events]
    assert "tool_start" in types and "tool_result" in types, \
        f"재실행의 도구 이벤트가 스트림 밖으로 샜다 — 화면은 멈춘 것처럼 보인다: {types}"
    assert "text" in types, "재실행 본문이 한 글자도 안 흘렀다"

    # 재실행 표식이 사용자에게 보여야 한다(왜 답이 바뀌는지의 설명)
    assert any(e.get("type") == "text" and "재실행" in e.get("content", "")
               for e in events), "재실행 표식이 없다"

    # 재실행의 final 은 반환값으로 회수 — 이중 final 로 흘리지 않는다
    assert "final" not in types, \
        "재실행 final 을 그대로 흘리면 파이프라인의 최종 final 과 이중 적재된다"


def test_침묵_구간이_유휴_타임아웃_안에_들어온다():
    """이벤트 사이 간격을 '한 블로킹 단위'로 세어, 어떤 구간도 두 단위를 넘지 않는지.

    옛 판은 평가+재실행 전체가 이벤트 0 이라 이 시험이 곧장 깨진다.
    """
    runner = _Runner([(False, "부족", 2), (False, "아직", 1), (True, "", 0)])
    events, _ = _run(runner)
    # 라운드 3회 = 평가 3 + 재실행 2. 각 라운드가 최소 1개의 표지를 내야 한다.
    thinking = [e for e in events if e.get("type") == "thinking"]
    assert len(thinking) >= 3, \
        f"라운드마다 진행 표지가 필요하다 (받은 표지 {len(thinking)}개)"
    assert runner.ai.stream_calls == 2


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
