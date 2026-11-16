"""심층실행 — 단계의 출처, 실행자가 돌아오는 되돌아보기, 작업 메모, 돌아오지 않을 때의 상한, 끝내기 전 확인."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

import boot_paths  # noqa: F401
import deep_execution as de
import thread_context as tc
from conscious_supervisor import Supervisor
from supervision_bus import wrap

FAST = {"ceilings": [2, 2, 2], "grace": 2, "hold_s": 2}
SWITCH = ("1. 합성음을 다듬는 길이다\n2. 음원 후보 조사: 얻는 것 실제 음악 / 드는 것 호출 5회 / 뒤집을 관측 접근 제한\n"
          "3. 없음\nNEXT: 후보 두 개의 이용 조건을 확인하면 돌아온다\nVERDICT: SWITCH — 음원부터 찾아본다")
KEEP = "1. 같은 길이다\n2. 없음\n3. 없음\nNEXT: 초안이 나오면 돌아온다\nVERDICT: KEEP — 그대로 간다"


@pytest.fixture(autouse=True)
def no_live_config(monkeypatch):
    """운영 설정 파일의 값이 시험 결과를 바꾸지 않게 한다."""
    monkeypatch.setattr(de, "_file_settings", lambda: {})


@pytest.fixture
def scope():
    previous = tc.snapshot()
    made = []
    yield made
    for controller in made:
        controller.close()
    tc.restore(previous)


def make(tmp_path, monkeypatch, scope, deep=FAST, framing=None, stream=None):
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: pytest.fail("시험의 실제 모델 호출 금지"))
    tc.set_current_agent_id("worker")
    tc.set_current_task_id("task-deep-test")
    calls = []

    def execute(name, payload, **kwargs):
        calls.append((name, payload))
        return {"success": True, "value": payload}

    ai = SimpleNamespace(agent_id="worker", project_path=str(tmp_path),
                         tools=[{"name": "inspect", "input_schema": {"type": "object"}}],
                         _custom_execute_tool=execute,
                         process_message_stream=stream or (lambda **kw: iter(())))
    runner = SimpleNamespace(ai=ai)
    controller = Supervisor(runner, "목표 원문", [], "worker", "task-deep-test",
                            {"tick_s": 1000, "deep_execution": deep}, directory=tmp_path / "store")
    controller.configure(framing or {"task_framing": "문제", "first_step": "먼저 현황을 본다"})
    controller.calls = calls
    scope.append(controller)
    return runner, controller


def script(monkeypatch, replies):
    """phase 별로 준비한 응답을 차례로 돌려주고, 불린 phase 와 지문을 기록한다."""
    seen = []

    def fake(controller, prompt, **kw):
        seen.append((kw.get("phase"), prompt))
        queue = replies.get(kw.get("phase"), [])
        return queue.pop(0) if queue else ""
    monkeypatch.setattr("supervisor_runtime.invoke", fake)
    return seen


def work(controller, start, count):
    execute = wrap(controller._execute)
    return [execute("inspect", {"n": index}) for index in range(start, start + count)]


def test_depth_comes_only_from_route_default_and_user_order():
    cfg = de.settings({})
    assert cfg["enabled"] is True                                             # THINK 는 말이 없어도 1단계다
    assert de.depth_of({"task_framing": "x"}, cfg) == 1
    assert de.depth_of({"task_framing": "x", "deep_execution": 3}, cfg) == 3  # 사용자가 시킨 단계
    assert de.depth_of({"task_framing": "x", "deep_execution": "2"}, cfg) == 2
    assert de.depth_of({"task_framing": "x", "deep_execution": 9}, cfg) == 5  # 상한
    assert de.depth_of({"task_framing": "x", "deep_execution": 0}, cfg) == 0  # 하지 말라는 주문
    assert de.depth_of({"task_framing": "x", "deep_execution": None}, cfg) == 1
    assert de.depth_of({"task_framing": "x", "deep_execution": True}, cfg) == 1  # 참/거짓은 주문이 아니다
    assert de.depth_of({"task_framing": "x", "deep_research": True}, cfg) == 0   # 심층연구는 그대로
    assert de.depth_of({"task_framing": "x", "deep_research": True, "deep_execution": 2}, cfg) == 2
    assert de.depth_of({"task_framing": "x", "needs_clarification": True}, cfg) == 0
    assert de.depth_of({"task_framing": "x", "_framing_source": "repair_execution"}, cfg) == 0
    assert de.depth_of({}, cfg) == 0                                          # 의식 규정이 없으면(EXECUTE) 없다
    off = de.settings({"deep_execution": {"enabled": False}})
    assert de.depth_of({"task_framing": "x", "deep_execution": 3}, off) == 0  # 끄면 언제나 0


def test_switched_off_leaves_the_turn_as_before(tmp_path, monkeypatch, scope):
    monkeypatch.setattr(de, "settings", lambda config=None: {**de.DEFAULTS, "enabled": False})
    assert de.execution_block({"task_framing": "x", "deep_execution": 3, "first_step": "y"}) == ""
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {})
    work(controller, 1, 10)
    controller.tick()
    assert seen == [] and controller.pending is None
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "알게 된 것"}))
    assert told["checkpoint"] is False and seen == []
    steps = de.final_check(runner, controller, "목표 원문", "초안", [], collect=lambda e: None)
    with pytest.raises(StopIteration) as done:
        next(steps)
    assert done.value.value == "초안" and seen == []


def test_executor_is_told_the_first_step_and_how_to_come_back():
    block = de.execution_block({"task_framing": "x", "deep_execution": 2, "first_step": "현황부터 본다"})
    assert "심층실행 2단계" in block and "현황부터 본다" in block
    assert 'kind="checkpoint"' in block and "evidence" in block and "progress" in block
    # 준비만 마치고 돌아오면 의식이 다시 볼 것이 없다(에피소드 6115·6117·6119). 첫 걸음의 끝은 첫 결과다.
    assert "준비만 마친 때는 아직 돌아갈 때가 아니다" in block and "첫 결과" in block
    assert de.execution_block({"task_framing": "x", "deep_research": True}) == ""
    assert de.execution_block({}) == ""


def test_executor_comes_back_and_gets_direction_before_continuing(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {"reflect": ["1. 없음\n2. 음원을 찾는다 / 합성음을 다듬는다\n3. 음원 후보", SWITCH]})
    work(controller, 1, 1)
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "음원 파일이 없다는 것을 확인했다",
                                          "progress": "합성음을 더 다듬으려 한다"}))
    assert [phase for phase, _ in seen] == ["reflect", "reflect"]     # 알게 된 것은 실행자가 적었다
    first, second = seen[0][1], seen[1][1]
    assert "음원 파일이 없다는 것을 확인했다" in first and "먼저 현황을 본다" in first
    assert "inspect" not in first                                     # 한 일은 아직 보지 않는다
    assert "inspect" in second and "합성음을 더 다듬으려 한다" in second
    assert told["checkpoint"] is True and told["round"] == "1/1" and told["verdict"] == "SWITCH"
    assert "음원 후보 조사" in told["content"] and "VERDICT" not in told["content"]
    assert "되돌아보기를 모두 마쳤다" in told["content"]
    memo = (controller.store.directory / "deep_memo.md").read_text(encoding="utf-8")
    assert "먼저 현황을 본다" in memo and "실행자가 적음" in memo and "판정: SWITCH" in memo
    again = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "더 알게 된 것"}))
    assert again["checkpoint"] is False and len(seen) == 2            # 주문한 횟수를 넘겨 부르지 않는다
    work(controller, 2, 6)
    controller.tick()
    assert len(seen) == 2 and controller.pending is None              # 다 썼으면 하네스도 끼어들지 않는다


def test_three_rounds_accumulate_one_memo_and_set_the_next_point(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope, framing={"task_framing": "문제", "deep_execution": 3})
    seen = script(monkeypatch, {"reflect": ["길 하나", KEEP, "길 둘", SWITCH, "길 셋", KEEP]})
    work(controller, 1, 1)
    one = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "첫 번째로 알게 된 것"}))
    assert one["round"] == "1/3" and one["verdict"] == "KEEP"
    assert "초안이 나오면 돌아온다" in one["content"] and "남은 되돌아보기 2번" in one["content"]
    work(controller, 2, 1)
    two = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "두 번째로 알게 된 것"}))
    assert two["round"] == "2/3" and "남은 되돌아보기 1번" in two["content"]
    assert "첫 번째로 알게 된 것" in seen[2][1] and "판정: KEEP" in seen[2][1]   # 지난 되돌아보기를 메모에서 읽는다
    three = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "세 번째로 알게 된 것"}))
    assert three["round"] == "3/3" and "되돌아보기를 모두 마쳤다" in three["content"]
    assert len(seen) == 6 and len(controller._deep["memo"]) == 3


def test_harness_first_asks_then_steps_in_only_if_executor_still_does_not_come_back(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope, framing={"task_framing": "문제", "deep_execution": 2})
    seen = script(monkeypatch, {"reflect": ["- 확인된 것: 음원 파일이 없다", "길", SWITCH]})
    work(controller, 1, 1)
    controller.tick()
    assert seen == [] and controller.pending is None                  # 상한(2회) 전에는 아무 일도 없다
    work(controller, 2, 1)
    controller.tick()
    assert seen == []                                                 # 상한에 닿으면 먼저 청한다. 모델은 부르지 않는다
    asked = json.loads(wrap(controller._execute)("inspect", {"n": 3}))
    assert asked["not_executed"] is True
    assert "돌아올 지점을 지났다" in asked["supervisor_instruction"]["instruction"]
    assert 'kind="checkpoint"' in asked["supervisor_instruction"]["instruction"]
    work(controller, 4, 1)
    controller.tick()
    assert seen == []                                                 # 청한 뒤 기다리는 폭(2회) 안
    work(controller, 5, 1)
    controller.tick()
    assert [phase for phase, _ in seen] == ["reflect"] * 3            # 그래도 오지 않아 하네스가 대신 적고 되돌아봤다
    assert "돌아오지 않았다" in seen[0][1] and "- 확인된 것: 음원 파일이 없다" in seen[1][1]
    blocked = json.loads(wrap(controller._execute)("inspect", {"n": 6}))
    instruction = blocked["supervisor_instruction"]["instruction"]
    assert blocked["not_executed"] is True and "돌아오지 않아" in instruction and "음원 후보 조사" in instruction
    assert "남은 되돌아보기 1번" in instruction
    assert "하네스가 적음" in (controller.store.directory / "deep_memo.md").read_text(encoding="utf-8")
    assert len(controller.calls) == 4                                 # 청과 판단을 받은 두 호출은 실행되지 않았다


def test_executor_returning_after_being_asked_uses_its_own_note(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {"reflect": ["길", KEEP]})
    work(controller, 1, 2)
    controller.tick()
    assert de._own_pending(controller) == "nudge"
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "공식 안내와 포스터를 확인했다"}))
    assert told["checkpoint"] is True and told["round"] == "1/1"
    assert [phase for phase, _ in seen] == ["reflect", "reflect"]     # 실행자가 적었으므로 대신 적는 호출이 없다
    assert "공식 안내와 포스터를 확인했다" in seen[0][1]
    assert controller.pending is None                                 # 청은 걷혔다
    assert work(controller, 3, 1)[0]["success"] is True               # 다음 호출은 막히지 않는다


def test_executor_arriving_after_harness_substitute_gets_that_judgment(tmp_path, monkeypatch, scope):
    """에피소드 6110: 하네스가 먼저 대신 되돌아본 뒤 실행자가 스스로 돌아왔다. 거절하지 않고 그 판단을 답으로 준다."""
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {"reflect": ["알게 된 것", "길", KEEP]})
    work(controller, 1, 2)
    assert de.reflect(controller, de._state(controller)) is True      # 한 번뿐인 되돌아보기를 하네스가 썼다
    assert controller.pending is None                                 # 마지막 차례의 '계속'은 따로 전달하지 않는다
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "공식 안내와 포스터를 확인했다"}))
    assert told["checkpoint"] is True and told["round"] == "1/1" and told["verdict"] == "KEEP"
    assert "지금 길로 계속한다" in told["content"] and len(seen) == 3  # 모델을 다시 부르지 않는다
    again = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "더 알게 된 것"}))
    assert again["checkpoint"] is False and "모두 마쳤다" in again["directive"]

def test_keep_at_the_last_round_stays_silent(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {"reflect": ["알게 된 것", "길", KEEP]})
    work(controller, 1, 2)
    assert de.reflect(controller, de._state(controller)) is True
    assert len(seen) == 3 and controller.pending is None
    assert work(controller, 3, 1)[0]["success"] is True

def test_no_stop_directive_exists():
    assert de.parse_verdict("VERDICT: CUT — 이 갈래를 그만둔다") == ("KEEP", "")
    assert de.parse_verdict("본문\nVERDICT: **WRAP** — 충분하다") == ("WRAP", "충분하다")
    assert de.parse_verdict("판정 없음") == ("KEEP", "")
    assert de.parse_next("본문\nNEXT: 표를 채우면 돌아온다\nVERDICT: KEEP — x") == "표를 채우면 돌아온다"
    assert "그만두라고 지시하지 않는다" in de.R2 and "CUT" not in de.R2


def test_failed_reflection_never_stops_the_turn(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope, framing={"task_framing": "문제", "deep_execution": 2})

    def broken(*a, **kw):
        raise RuntimeError("모델 장애")
    monkeypatch.setattr("supervisor_runtime.invoke", broken)
    work(controller, 1, 2)
    assert de.reflect(controller, de._state(controller)) is True      # 예외가 밖으로 나오지 않는다
    assert controller.pending is None and controller.phase == "execute"
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "알게 된 것"}))
    assert told["checkpoint"] is False and "하던 방향으로 진행" in told["directive"]
    assert controller.executor_paused is False and not controller._deep["busy"].is_set()
    assert work(controller, 3, 1)[0]["success"] is True
    controller.tick()                                                 # 감시 주기도 그대로 돈다

def test_checkpoint_needs_what_was_learned_and_reframe_still_needs_its_premise(tmp_path, monkeypatch, scope):
    from reframe import TOOL_SCHEMA, execute_reframe
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {})
    empty = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "  "}))
    assert empty["checkpoint"] is False and "evidence" in empty["reason"] and seen == []
    plain = json.loads(controller.reframe({"kind": "other", "evidence": "근거만 있다"}))
    assert plain["revised"] is False and seen == []                   # 재규정은 여전히 깨진 전제가 있어야 한다
    assert "checkpoint" in TOOL_SCHEMA["input_schema"]["properties"]["kind"]["enum"]
    assert TOOL_SCHEMA["input_schema"]["required"] == ["evidence"]
    routed = json.loads(execute_reframe({"kind": "checkpoint", "evidence": ""}, "worker", "task-deep-test"))
    assert routed["checkpoint"] is False and "evidence" in routed["reason"]   # 감독이 있으면 감독에게 간다
    alone = json.loads(execute_reframe({"kind": "checkpoint", "evidence": "x"}, "nobody", "no-task"))
    assert alone["checkpoint"] is False and "되돌아보기가 없다" in alone["directive"]


def test_hold_waits_only_while_reflecting(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope)
    de.hold(controller)                                               # 상태가 없으면 바로 돌아온다
    state = de._state(controller)
    state["busy"].set()
    threading.Timer(0.4, state["busy"].clear).start()
    started = time.monotonic()
    de.hold(controller)
    assert 0.3 <= time.monotonic() - started < 1.9                    # 끝나면 풀리고, 상한(2초) 전에 돌아온다


def test_final_check_resumes_executor_once_and_takes_rewritten_response(tmp_path, monkeypatch, scope):
    resumed = []

    def stream(**kw):
        resumed.append(kw["message_content"])
        yield {"type": "tool_start", "id": "t1", "name": "Bash", "input": {"command": "true"}}
        yield {"type": "tool_result", "id": "t1", "result": "ok"}
        yield {"type": "final", "content": "고친 응답"}
    runner, controller = make(tmp_path, monkeypatch, scope, stream=stream)
    seen = script(monkeypatch, {"reflect": ["길", KEEP], "review": [json.dumps({
        "status": "REWORK", "reason": "찾아보지 않고 없다고 했다",
        "findings": [{"reason": "음원 조사가 없다", "instruction": "후보를 확인하라", "scope": "goal"}]})]})
    work(controller, 1, 1)
    controller.reframe({"kind": "checkpoint", "evidence": "알게 된 것"})
    collected, events = [], []
    steps = de.final_check(runner, controller, "목표 원문", "초안", [], collect=collected.append)
    with pytest.raises(StopIteration) as done:
        while True:
            events.append(next(steps))
    assert done.value.value == "고친 응답"
    review = [prompt for phase, prompt in seen if phase == "review"]
    assert len(review) == 1 and "response_draft" in review[0] and "초안" in review[0]
    assert "작업 메모" in review[0]                                   # 끝내기 전 확인이 메모를 읽는다
    assert len(resumed) == 1 and "후보를 확인하라" in resumed[0] and "끝내기 전 확인" in resumed[0]
    assert [e["type"] for e in events] == ["tool_start", "tool_result"]  # 초안 글은 흘리지 않는다
    assert any(e.get("type") == "final" for e in collected)
    again = de.final_check(runner, controller, "목표 원문", "고친 응답", [], collect=collected.append)
    with pytest.raises(StopIteration) as second:
        next(again)
    assert second.value.value == "고친 응답" and len(resumed) == 1    # 다시 검토하지 않는다


def test_final_check_without_findings_or_without_work_passes_through(tmp_path, monkeypatch, scope):
    runner, controller = make(tmp_path, monkeypatch, scope)
    seen = script(monkeypatch, {"review": [json.dumps({"status": "CONTINUE", "reason": "요청과 맞는다"})]})
    quiet = de.final_check(runner, controller, "목표 원문", "초안", [], collect=lambda e: None)
    with pytest.raises(StopIteration) as done:
        next(quiet)
    assert done.value.value == "초안" and seen == []                  # 도구를 한 번도 안 쓴 답에는 확인이 없다
    work(controller, 1, 1)
    controller._deep["final_done"] = False
    checked = de.final_check(runner, controller, "목표 원문", "초안", [], collect=lambda e: None)
    with pytest.raises(StopIteration) as done:
        next(checked)
    assert done.value.value == "초안" and [phase for phase, _ in seen] == ["review"]


def test_reflection_that_did_not_happen_is_not_reported_as_keep(tmp_path, monkeypatch, scope):
    """에피소드 6119: 예산 심사에서 불리지 않은 되돌아보기가 빈 답을 냈고 그것이 KEEP 으로 전달됐다."""
    runner, controller = make(tmp_path, monkeypatch, scope,
                              framing={"task_framing": "문제", "first_step": "먼저 현황을 본다", "deep_execution": 2})
    script(monkeypatch, {})                                            # 의식이 아무 답도 내지 못한다
    controller.call_stop = {"kind": "budget", "reason": "의식 호출 토큰 예산을 소진했습니다"}
    work(controller, 1, 3)
    told = json.loads(controller.reframe({"kind": "checkpoint", "evidence": "알게 된 것", "progress": "다음에 할 것"}))
    assert told["checkpoint"] is False and "verdict" not in told
    assert "토큰 예산" in told["reason"] and "이루어지지 않았다고 적는다" in told["directive"]
    logged = [json.loads(line) for path in (tmp_path / "store").rglob("events.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds = [row["kind"] for row in logged]
    assert "deep.error" in kinds and "deep.reflection" not in kinds
    memo = de.memo_text(controller._deep, controller.framing)
    assert "되돌아보기 1/2" in memo and "이루어지지 않음" in memo          # 끝내기 전 확인이 이 사실을 읽는다


def test_ordered_reflections_are_not_starved_by_the_planning_share(tmp_path, monkeypatch, scope):
    """재규정이 계획 몫을 다 써도 사람이 주문한 되돌아보기는 불린다(6119: 재규정 두 번이 16만 8천 토큰)."""
    runner, controller = make(tmp_path, monkeypatch, scope)
    controller.phase_usage["plan"] = {"input": 10 ** 9, "output": 10 ** 9}
    assert controller.model_admitted("reflect") is True
    assert controller.model_admitted("plan") is False and controller.model_admitted("reframe") is False


def test_final_check_steps_aside_when_independent_review_follows(tmp_path, monkeypatch, scope):
    """평가가 곧바로 이어지는 턴에서는 끝 확인을 부르지 않는다(에피소드 6119 에서 둘이 연달아 돌았다)."""
    runner, controller = make(tmp_path, monkeypatch, scope,
                              framing={"task_framing": "문제", "first_step": "먼저 현황을 본다",
                                       "independent_review": True})
    seen = script(monkeypatch, {"review": [json.dumps({"status": "REWORK", "reason": "x", "findings": [
        {"reason": "r", "instruction": "i", "scope": "goal"}]})]})
    work(controller, 1, 2)
    assert controller.evaluation_enabled is True
    steps = de.final_check(runner, controller, "목표 원문", "초안", [], collect=lambda e: None)
    with pytest.raises(StopIteration) as done:
        next(steps)
    assert done.value.value == "초안" and seen == []                  # 의식 모델을 부르지 않았다
    logged = [json.loads(line)["kind"] for path in (tmp_path / "store").rglob("events.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "deep.final_skipped" in logged and "deep.final_check" not in logged


def test_order_and_first_step_belong_to_their_turn():
    from framing_inheritance import STRIP_ALWAYS
    assert "deep_execution" in STRIP_ALWAYS and "first_step" in STRIP_ALWAYS


def test_real_pipeline_checks_before_finishing_and_delivers_one_rewritten_final(tmp_path, monkeypatch, scope):
    """운영 기본(켜짐)에서 실제 파이프라인 본문이 끝내기 전 확인을 거쳐 최종 응답을 한 번만 낸다."""
    import associative_recall
    from agent_pipeline import CognitivePipelineMixin
    _, controller = make(tmp_path, monkeypatch, scope)
    saved, requests = [], []

    class Runner(CognitivePipelineMixin):
        config = {"name": "worker"}
        project_path = controller.project_path
        _associate = associative_recall.stub()
        _decide_request_type = lambda *a: ("THINK", None)
        _run_consciousness_or_reuse = lambda *a, **kw: {"task_framing": "문제", "first_step": "먼저 현황을 본다"}
        _consciousness_needs_repair = lambda *a: False
        _consciousness_clarification = lambda *a: None
        _extract_achievement_criteria = lambda *a: ""
        _refresh_execution_prompt = lambda *a, **kw: "요청"
        _apply_consciousness_to_history = lambda self, h, c: h
        _after_response_async = lambda self, message, response, **kw: saved.append(response)

    def execute(**kwargs):
        requests.append(str(kwargs["message_content"]))
        resumed = "끝내기 전 확인" in requests[-1]
        yield {"type": "tool_start", "id": f"t{len(requests)}", "name": "Bash", "input": {"command": "true"}}
        yield {"type": "tool_result", "id": f"t{len(requests)}", "name": "Bash", "result": "ok"}
        yield {"type": "final", "content": "고친 응답" if resumed else "초안"}

    runner = Runner()
    runner.ai = SimpleNamespace(_provider=None, process_message_stream=execute)
    controller.runner = runner
    monkeypatch.setattr("supervision_bus.current", lambda: controller)
    monkeypatch.setattr("reframe.open_turn", lambda *a, **kw: None)
    seen = script(monkeypatch, {"review": [json.dumps({
        "status": "REWORK", "reason": "확인 없이 끝냈다",
        "findings": [{"reason": "결과를 다시 읽지 않았다", "instruction": "결과를 확인하라", "scope": "goal"}]})]})
    events = list(runner._cognitive_stream_body("요청", []))
    assert not [e for e in events if e["type"] == "error"], events
    finals = [e["content"] for e in events if e["type"] == "final"]
    assert finals == ["고친 응답"] and saved == finals            # 초안은 나가지 않고 고친 응답이 한 번 나간다
    assert len(requests) == 2 and "결과를 확인하라" in requests[1]  # 실행자를 한 번만 이었다
    assert [phase for phase, _ in seen] == ["review"]
