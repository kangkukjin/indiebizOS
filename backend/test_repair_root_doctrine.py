"""수리 교리: 뿌리에서 끝내라 — 범위 축소 임시처방·과잉 되묻기 방지 배터리 (2026-09-01).

사용자 관찰: 자기수정을 시키면 "시킨 일을 벗어나지 않기 위해" 발견한 원인을 안 고치고
보고만 하며, 심각하지 않은 결함마다 "고칠까요?"를 되물었다. 근본은 한 문장이었다 —
의식 프롬프트 §시스템 수리 안전수칙의 옛 조항이 *스코프 크리프 방지*와 *원인 사슬 추적*을
같은 문장에 묶어, 사슬 위의 뿌리까지 '명령 밖'으로 분류시켰다.

  D1 의식 교리 — 뿌리에서 고치라는 지시가 있고, 옛 '보고만' 조항은 은퇴했다
  D2 의식 교리 — '명령 밖'을 사슬 밖으로 정의하고, 되묻기를 두 종류로 한정한다
  D3 평가 관문 — 사슬 위의 원인을 보고만 하고 끝낸 수리 턴은 미달로 잡는다
  D4 프롬프트 mtime — 교리를 고치면 재기동 없이 다음 턴부터 새 본문이 주입된다
  D5 소비처 주입 — 그랜트가 살아 있는 턴에만 fragments/13_repair.md 가 실행자 turn_context 에 실린다
  D6 실행자 base 프롬프트 — 옛 "요청하지 않은 개선 금지"가 사슬 경계 판본으로 바뀌었다

★D5 가 이 배터리의 핵심이다(2026-09-02 재수리). 09-01 판은 교리를 의식 프롬프트(생산처)에만
두어, 1-2문장 task_framing 병목 뒤의 실행자에게는 반대 압력(base 의 '요청 밖 개선 금지')만
온전히 닿았다 — 뿌리를 알고도 소비처가 아닌 자리를 고친, 사용자가 지적한 바로 그 패턴.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognition"))

from runtime_utils import get_base_path  # noqa: E402

PROMPTS = get_base_path() / "data" / "common_prompts"


def _read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_d1_consciousness_orders_root_fix():
    """D1 — 뿌리 지시가 있고 옛 '보고만' 조항은 사라졌다."""
    t = _read("consciousness_prompt.md")
    assert "뿌리에서 고치" in t
    assert "원인 사슬" in t
    # 은퇴 문구 — 사슬 위의 원인까지 보고만 하게 만들던 자리
    assert "수리 중 발견한 다른 문제는 고치지 말고 보고만" not in t


def test_d2_scope_is_the_chain_and_asking_is_bounded():
    """D2 — '명령 밖'=사슬 밖, 되묻기는 요구사항 변경·파괴적 변경 둘뿐."""
    t = _read("consciousness_prompt.md")
    assert "사슬 밖" in t
    assert "같은 사슬 안이면 묻지 말고 고쳐라" in t
    assert "되묻기는 두 종류뿐" in t


def test_d3_evaluator_fails_symptom_only_repair():
    """D3 — 평가자가 증상 가리기 수리를 미달로 잡는다."""
    t = _read("evaluator_prompt.md")
    assert "증상 가리기" in t
    # 미달의 정의가 '뿌리를 안 고친 것'이지 '뿌리를 말한 것'이 아니어야 한다 —
    # 관문이 정직성에 벌점을 주면 가르치는 것은 "뿌리를 언급하지 마라"가 된다.
    assert "뿌리를 안 고친 것" in t
    assert "뿌리를 말한 것" in t


def test_d4_prompt_reloads_on_mtime_change(tmp_path):
    """D4 — 역할 프롬프트 파일이 바뀌면 provider 재구성 없이 본문이 갱신된다."""
    from consciousness_agent import ConsciousnessAgent

    role = tmp_path / "consciousness_prompt.md"
    role.write_text("옛 교리", encoding="utf-8")

    agent = object.__new__(ConsciousnessAgent)   # provider 없이 캐시 규약만 검사
    agent._prompt = role.read_text(encoding="utf-8")
    agent._prompt_path = role
    agent._prompt_mtime = ConsciousnessAgent._file_mtime(role)

    agent._reload_prompt_if_changed()
    assert agent._prompt == "옛 교리"            # 무변경이면 다시 읽지 않는다

    role.write_text("새 교리", encoding="utf-8")
    os.utime(role, (agent._prompt_mtime + 10, agent._prompt_mtime + 10))
    called = {}

    def _fake_load():
        called["yes"] = True
        agent._prompt = role.read_text(encoding="utf-8")
        agent._prompt_mtime = ConsciousnessAgent._file_mtime(role)

    agent._load_prompt = _fake_load
    agent._reload_prompt_if_changed()
    assert called.get("yes"), "mtime 이 바뀌었는데 재적재가 안 걸렸다"
    assert agent._prompt == "새 교리"


def test_d5_repair_fragment_reaches_executor_only_with_grant():
    """D5 — 그랜트 있는 턴: 13_repair.md 가 turn_context 에 실린다 / 없는 턴: 안 실린다."""
    import prompt_builder
    import thread_context
    from red_grant import issue_grant, revoke_grant

    task_id = "task_doctrine_probe_d5"
    snap = thread_context.snapshot()
    try:
        thread_context.set_current_task_id(task_id)
        thread_context.set_current_agent_id("system_ai")

        # 그랜트 없음 — 교리 없음
        revoke_grant(task_id=task_id)
        ctx = prompt_builder._build_dynamic_context(consciousness_output=None, model_name="m")
        assert "수리 턴" not in ctx

        # 그랜트 발급 — 교리가 실행자 앞에 실린다
        issue_grant(agent_id="system_ai", task_id=task_id, reason="d5")
        ctx = prompt_builder._build_dynamic_context(consciousness_output=None, model_name="m")
        assert "원인 사슬을 끝까지 따라가" in ctx
        assert "되묻기는 두 종류뿐" in ctx
        assert "최종 보고 형식" in ctx
        assert ctx.startswith("<turn_context")   # dynamic — stable prefix 캐시를 안 깬다
    finally:
        revoke_grant(task_id=task_id)
        thread_context.restore(snap)


def test_d6_base_prompt_scope_is_the_chain():
    """D6 — 실행자 base 프롬프트의 경계가 범위가 아니라 사슬이다."""
    t = _read("base_prompt_v6.md")
    assert "- 요청하지 않은 개선을 하지 마라\n" not in t
    assert "원인 사슬 밖" in t


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
