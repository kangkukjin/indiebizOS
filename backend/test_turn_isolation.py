"""동시 턴은 서로의 프롬프트·모델을 덮지 않는다 — 턴 사유 AI 뷰 관문 (2026-08-31).

배경: 시스템 AI 러너는 **싱글턴**이다(get_system_ai_runner). 그런데 인지 파이프라인은
그 상주 객체에 턴마다 달라지는 값을 쓴다 —
  · `self.ai.system_prompt` / `self.ai._provider.system_prompt` (4단계, 의식 framing 포함)
  · `self.ai._provider` 슬롯 (3단계 THINK/REPAIR/reflex 모델 스왑)
  · `_last_tool_images/_results/_calls` (이 턴의 도구 수확)
채팅 턴·위임 턴·스케줄러 턴이 겹치면 나중 턴의 대입이 앞 턴의 값을 덮는다. 스왑은
finally 에서 복원하니 **최종 상태**는 맞지만, 겹치는 구간 동안 한쪽이 남의 프롬프트·
남의 모델로 돈다.

이 위험은 위임 루프를 파이프라인에 합류시키면서(fbad190d) 비로소 닿게 됐다 — 그전엔
위임이 파이프라인 밖이라 프롬프트를 안 썼다. 그래서 그 수리와 한 벌로 닫는다.

처방은 잠금이 아니라 **격리**다: 턴 안에서 `runner.ai` 는 스레드-사유 얕은 사본이다.
잠금을 골랐다면 자기 위임(턴 안에서 [others:delegate] → 위임 루프는 다른 스레드)이
같은 잠금을 기다려 교착이었다.

  T1 두 스레드가 동시에 프롬프트를 써도 서로의 값을 안 본다
  T2 provider 슬롯 스왑도 스레드 사유다 (남의 모델로 돌지 않는다)
  T3 스코프 밖에서는 바탕 객체 그대로 (턴 밖 대입=_init_ai·기어 전파가 살아 있어야 한다)
  T4 스코프는 재진입 가능 — 중첩은 바깥 사본을 잇는다 (위임 핀이 살아남는다)
  T5 관문 자기검증 — 격리를 끄면 T1 이 실제로 깨진다 (침묵 통과 방지)
  T6 사유 사본은 값만 사유화하고 비싼 것(클라이언트·세션)은 참조로 공유한다
  T7 격리는 가장 바깥 경계까지 — CLI 프로바이더의 시스템 프롬프트 임시 파일
"""
import os
import sys
import threading

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
for _p in ("", "base", "cognition", "datastore", "ibl", "services", "surface", "common"):
    _d = os.path.join(BACKEND, _p) if _p else BACKEND
    if _d not in sys.path:
        sys.path.insert(0, _d)

import boot_paths  # noqa: F401,E402  (독립 스크립트 규약)
from cognition.agent_pipeline import CognitivePipelineMixin, per_turn_provider_view  # noqa: E402


class _FakeProvider:
    """system_prompt 를 들고 있는 최소 프로바이더 — 실제 것과 같은 자리만 흉내낸다."""

    def __init__(self, model):
        self.model = model
        self.system_prompt = "BASE"
        self.agent_id = "system_ai"
        self._last_tool_calls = []


class _FakeAI:
    def __init__(self):
        self.system_prompt = "BASE"
        self._provider = _FakeProvider("base-model")
        self._last_tool_calls = []


class _FakeRunner(CognitivePipelineMixin):
    """ai 프로퍼티·턴 스코프만 빌려 쓰는 최소 러너(상주 싱글턴을 흉내낸다)."""

    def __init__(self):
        self.ai = _FakeAI()          # 스코프 밖 대입 → 바탕


def _run_two_turns(runner, use_scope=True):
    """두 스레드가 각자 자기 프롬프트를 쓰고, 상대가 쓴 뒤에 자기 값을 다시 읽는다.

    배리어로 '겹침'을 강제한다 — 겹치지 않으면 이 부류 결함은 안 보인다.
    """
    seen = {}
    barrier = threading.Barrier(2)

    def turn(name):
        def body():
            runner.ai.system_prompt = name
            runner.ai._provider.system_prompt = name
            runner.ai._last_tool_calls.append(name)
            barrier.wait(timeout=5)        # 둘 다 쓴 뒤에 읽는다
            seen[name] = (runner.ai.system_prompt,
                          runner.ai._provider.system_prompt,
                          list(runner.ai._last_tool_calls))
        if use_scope:
            with runner.turn_ai_scope():
                body()
        else:
            body()

    threads = [threading.Thread(target=turn, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return seen


def test_t1_concurrent_prompts_do_not_bleed():
    """T1 — 동시 턴이 서로의 system_prompt 를 덮지 않는다."""
    runner = _FakeRunner()
    seen = _run_two_turns(runner, use_scope=True)
    assert set(seen) == {"A", "B"}, f"두 턴이 다 끝나지 않았다: {seen}"
    for name, (ai_p, prov_p, calls) in seen.items():
        assert ai_p == name, f"{name} 턴이 남의 ai.system_prompt 를 봤다: {ai_p}"
        assert prov_p == name, f"{name} 턴이 남의 provider.system_prompt 를 봤다: {prov_p}"
        assert calls == [name], f"{name} 턴의 도구 수확에 남의 것이 섞였다: {calls}"


def test_t2_provider_swap_is_thread_private():
    """T2 — provider 슬롯 스왑이 남의 턴에 새지 않는다."""
    runner = _FakeRunner()
    base = runner.ai._provider
    swapped = {}
    barrier = threading.Barrier(2)

    def swapper():
        with runner.turn_ai_scope():
            runner.ai._provider = _FakeProvider("repair-model")   # THINK/REPAIR 스왑 흉내
            barrier.wait(timeout=5)
            swapped["swapper"] = runner.ai._provider.model

    def bystander():
        with runner.turn_ai_scope():
            barrier.wait(timeout=5)
            swapped["bystander"] = runner.ai._provider.model

    ts = [threading.Thread(target=swapper), threading.Thread(target=bystander)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)

    assert swapped.get("swapper") == "repair-model"
    assert swapped.get("bystander") == "base-model", (
        f"곁의 턴이 남의 스왑 모델로 돌았다: {swapped.get('bystander')}")
    assert runner.ai._provider is base, "턴이 끝난 뒤 바탕 provider 가 바뀌어 있다"


def test_t3_outside_scope_is_the_base_object():
    """T3 — 스코프 밖 읽기/쓰기는 바탕 객체 (기어 전파·_init_ai 가 살아 있어야 한다)."""
    runner = _FakeRunner()
    base_ai = runner.ai
    with runner.turn_ai_scope():
        assert runner.ai is not base_ai, "턴 안에서 사본이 아니라 바탕을 봤다"
        runner.ai.system_prompt = "TURN"
    assert runner.ai is base_ai
    assert runner.ai.system_prompt == "BASE", "턴의 쓰기가 바탕으로 샜다"

    new_ai = _FakeAI()
    runner.ai = new_ai                      # 턴 밖 대입 = 바탕 교체
    assert runner.ai is new_ai


def test_t4_scope_is_reentrant_and_keeps_the_outer_pin():
    """T4 — 중첩 스코프는 바깥 사본을 잇는다 (위임 모델 핀이 안쪽에서 사라지지 않는다)."""
    runner = _FakeRunner()
    with runner.turn_ai_scope():
        runner.ai._provider = _FakeProvider("delegation-pin")     # 바깥 핀
        outer_ai = runner.ai
        with runner.turn_ai_scope():                              # 파이프라인이 다시 연다
            assert runner.ai is outer_ai, "중첩이 새 사본을 떠 바깥 핀을 지웠다"
            assert runner.ai._provider.model == "delegation-pin"
        assert runner.ai._provider.model == "delegation-pin", "안쪽 스코프 종료가 핀을 지웠다"
    assert runner.ai._provider.model == "base-model"


def test_t5_gate_detects_the_bug_when_isolation_is_off():
    """T5 — 격리를 끄면 T1 이 실제로 깨진다(관문 자기검증).

    ★'통과 ✓'는 아무것도 안 하는 관문에서도 나온다. 음성 대조가 있어야 신뢰할 수 있다.
    """
    runner = _FakeRunner()
    seen = _run_two_turns(runner, use_scope=False)
    bled = [n for n, (ai_p, prov_p, calls) in seen.items()
            if ai_p != n or prov_p != n or calls != [n]]
    assert bled, ("격리를 껐는데도 값이 안 섞였다 — 이 시험은 결함을 재현하지 못하므로 "
                  "T1 의 통과도 근거가 없다")


def test_t7_cli_prompt_file_is_not_shared_across_concurrent_turns():
    """T7 — 격리는 가장 바깥 경계까지 간다: CLI 프로바이더의 시스템 프롬프트 임시 파일.

    객체를 사유화해도(T1~T4) 프롬프트가 **공유 파일**로 새면 소용없다. 종전 경로 키는
    agent_id 뿐이라, 시스템 AI 의 채팅 턴과 위임 턴(둘 다 agent_id="system_ai")이 한
    파일을 덮어써 나중에 spawn 하는 subprocess 가 남의 턴 프롬프트를 읽을 수 있었다.
    """
    from providers.cli_provider import CliSubprocessProvider

    paths = {}
    barrier = threading.Barrier(2)

    class _P(CliSubprocessProvider):
        STATE_PREFIX = "gate_test"
        TOOL_POLICY = ""

        def __init__(self):                      # 실 초기화(바이너리 탐색) 우회
            self.agent_id = "system_ai"
            self.agent_name = "시스템 AI"
            self.system_prompt = ""
            self.no_tools = True

    def turn(name):
        p = _P()
        p.system_prompt = name
        written = p._write_system_prompt_file()
        barrier.wait(timeout=5)                  # 둘 다 쓴 뒤에 읽는다
        with open(written, encoding="utf-8") as f:
            paths[name] = (written, f.read())

    ts = [threading.Thread(target=turn, args=(n,)) for n in ("PROMPT_A", "PROMPT_B")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)

    assert set(paths) == {"PROMPT_A", "PROMPT_B"}, f"두 턴이 다 끝나지 않았다: {paths}"
    a_path, a_text = paths["PROMPT_A"]
    b_path, b_text = paths["PROMPT_B"]
    assert a_path != b_path, f"동시 턴이 같은 프롬프트 파일을 공유한다: {a_path}"
    assert a_text == "PROMPT_A" and b_text == "PROMPT_B", (
        f"프롬프트가 서로 덮였다: {a_text!r} / {b_text!r}")
    for pth, _ in paths.values():
        os.unlink(pth)


def test_t6_provider_view_shares_the_expensive_parts():
    """T6 — 사유 사본은 값만 사유화하고 비싼 것(클라이언트)은 참조로 공유한다."""
    prov = _FakeProvider("m")
    prov._client = object()
    prov._last_tool_calls = ["stale"]
    view = per_turn_provider_view(prov)
    assert view is not prov
    assert view._client is prov._client, "클라이언트까지 복제하면 비용·세션이 깨진다"
    assert view._last_tool_calls == [], "턴 수확 버퍼가 앞 턴 값을 물고 왔다"
    view.system_prompt = "MINE"
    assert prov.system_prompt == "BASE", "사본의 쓰기가 원본으로 샜다"

    class _Unclonable:
        def __copy__(self):
            raise RuntimeError("복제 불가")
    bad = _Unclonable()
    assert per_turn_provider_view(bad) is bad, "복제 실패 시 턴을 죽이지 말고 후퇴해야 한다"
    assert per_turn_provider_view(None) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
