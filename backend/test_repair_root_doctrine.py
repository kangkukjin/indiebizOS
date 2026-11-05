"""수리 지침의 갱신·그랜트별 전달을 실제 프롬프트 조립으로 확인한다."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognition"))

from runtime_utils import get_base_path  # noqa: E402

PROMPTS = get_base_path() / "data" / "common_prompts"


def _read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_d4_prompt_reloads_on_mtime_change(tmp_path):
    """D4 — 역할 프롬프트 파일이 바뀌면 provider 재구성 없이 본문이 갱신된다."""
    from consciousness_agent import ConsciousnessAgent

    role = tmp_path / "consciousness_prompt.md"
    role.write_text("옛 교리", encoding="utf-8")

    agent = object.__new__(ConsciousnessAgent)   # provider 없이 캐시 규약만 검사
    agent._prompt = role.read_text(encoding="utf-8")
    agent._prompt_path = role
    agent._prompt_mtime = ConsciousnessAgent._file_mtime(role)
    from vocabulary_state import revision
    agent._vocabulary_revision = revision()

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


def test_d5_repair_fragment_reaches_executor_only_with_grant(monkeypatch):
    """D5 — 그랜트 있는 턴: 13_repair.md 가 turn_context 에 실린다 / 없는 턴: 안 실린다."""
    import prompt_builder
    import thread_context
    from red_grant import issue_grant, revoke_grant

    # 앞선 수리 재개 시험의 임시 저장소를 가리키는 싱글턴을 물려받지 않는다.
    monkeypatch.setattr(prompt_builder, "_prompt_builder_instance",
                        prompt_builder.PromptBuilder(PROMPTS))

    doctrine = _read("fragments/13_repair.md").strip()
    assert doctrine
    task_id = "task_doctrine_probe_d5"
    snap = thread_context.snapshot()
    try:
        thread_context.set_current_task_id(task_id)
        thread_context.set_current_agent_id("system_ai")

        # 그랜트 없음 — 교리 없음
        revoke_grant(task_id=task_id)
        ctx = prompt_builder._build_dynamic_context(consciousness_output=None, model_name="m")
        assert doctrine not in ctx

        # 그랜트 발급 — 교리가 실행자 앞에 실린다
        issue_grant(agent_id="system_ai", task_id=task_id, reason="d5")
        ctx = prompt_builder._build_dynamic_context(consciousness_output=None, model_name="m")
        assert doctrine in ctx
        for other_task in ("task_other", ""):
            thread_context.set_current_task_id(other_task)
            other_ctx = prompt_builder._build_dynamic_context(consciousness_output=None, model_name="m")
            assert doctrine not in other_ctx
        assert ctx.startswith("<turn_context")   # dynamic — stable prefix 캐시를 안 깬다
    finally:
        revoke_grant(task_id=task_id)
        thread_context.restore(snap)


def test_d6_base_prompt_scope_is_the_chain():
    """D6 — 실행자 base 프롬프트의 경계가 범위가 아니라 사슬이다."""
    t = _read("base_prompt_v7.md")
    assert "요청의 원인 사슬을 따라 필요한 부분을 고치되" in t
    assert "관계없는 개선으로 범위를 넓히지 마라" in t


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
