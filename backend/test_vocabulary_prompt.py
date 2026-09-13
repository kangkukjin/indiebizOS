"""저장고 이동은 다음 모델 입력을 줄인다 — 상주 AI·의식·관용구 회귀."""
import boot_paths  # noqa: F401
import sqlite3
from types import SimpleNamespace

import pytest
import yaml
import prompt_builder  # 경로 상수는 임시 몸으로 전환하기 전에 초기화한다.

from test_vocabulary_state import box
from vocabulary_lifecycle import HUMAN_AUTHORITY


@pytest.fixture
def prompt_box(box, monkeypatch):
    import ibl_access
    import ibl_registry
    import ibl_routing
    import prompt_builder

    actions = {name: {"tool": name, "router": "handler", "description": f"{name} 전용 설명"}
               for name in ("base", "awake", "asleep")}
    (box / "data/ibl_nodes.yaml").write_text(yaml.safe_dump({
        "nodes": {"sense": {"description": "지각", "actions": actions}}
    }, allow_unicode=True))
    prompts = box / "data/common_prompts"
    (prompts / "fragments").mkdir(parents=True)
    (prompts / "base_prompt_v6.md").write_text("공통 규칙")
    (prompts / "consciousness_prompt.md").write_text("문제 규정 역할")
    (box / "data/system_ai_role.txt").write_text("시스템 역할")
    monkeypatch.setattr(prompt_builder, "get_base_path", lambda: box)
    monkeypatch.setattr(prompt_builder, "_prompt_builder_instance", prompt_builder.PromptBuilder(prompts))
    monkeypatch.setattr(prompt_builder, "get_system_structure_core", lambda: "공통 구조")
    # 별도 프로세스의 캐시도 활성 revision만으로 갱신돼야 한다. 로컬 무효화에 기대지 않는다.
    monkeypatch.setattr(ibl_routing, "invalidate_runtime_caches", lambda: [])
    monkeypatch.setattr(ibl_registry, "_nodes_path", box / "data/ibl_nodes.yaml")
    ibl_access.invalidate_nodes_cache()
    ibl_registry.invalidate_nodes()
    yield box
    ibl_access.invalidate_nodes_cache()
    ibl_registry.invalidate_nodes()


@pytest.mark.parametrize("system", [True, False])
def test_storage_move_shrinks_resident_provider_prompt_and_wake_restores(prompt_box, system):
    from agent_pipeline import CognitivePipelineMixin
    from prompt_builder import build_agent_prompt_split, build_system_ai_prompt_split
    from vocabulary_desktop import edit_desktop

    class Runner(CognitivePipelineMixin):
        config = {"_is_system_ai": system}
        project_path = prompt_box

        def _load_role(self):
            return "역할 유지"

        def _build_system_ai_prompt_split(self, role, consciousness, memory, **kwargs):
            return build_system_ai_prompt_split(
                consciousness_output=consciousness, execution_memory=memory, **kwargs)

        def _build_system_prompt_split(self, role, consciousness, memory):
            return build_agent_prompt_split(
                "테스트", role=role, consciousness_output=consciousness, execution_memory=memory)

    runner = Runner()
    runner.ai = SimpleNamespace(system_prompt="INITIAL", _provider=SimpleNamespace(system_prompt="INITIAL"))
    sent = []

    def next_request():
        with runner.turn_ai_scope():
            # 회상·의식·reflex가 하나도 없는 요청이 과거에는 초기 프롬프트를 그대로 썼다.
            message = runner._refresh_execution_prompt("안녕")
            sent.append(runner.ai._provider.system_prompt)
            assert runner.ai.system_prompt == sent[-1]
            assert "안녕" in message

    next_request()
    # 실제 상주 상태: 잠들기 전에 만들어 둔 사전으로 바탕 객체를 둔다.
    runner.ai.system_prompt = runner.ai._provider.system_prompt = sent[0]
    edit_desktop("move", item="awake", parent="store", authority=HUMAN_AUTHORITY)
    next_request()
    edit_desktop("move", item="awake", parent="desktop", authority=HUMAN_AUTHORITY)
    next_request()
    assert "[sense:awake] awake 전용 설명" in sent[0]
    assert "[sense:awake]" not in sent[1]
    assert "[sense:base]" in sent[1]
    assert len(sent[1]) < len(sent[0])
    assert sent[2] == sent[0]
    assert runner.ai._provider.system_prompt == sent[0]  # 다른 진행 중 턴의 바탕은 불변


def test_idiom_cache_tracks_activation_without_local_invalidation(prompt_box):
    from ibl_access import idioms_map
    from vocabulary_lifecycle import set_package_active

    db = prompt_box / "data/ibl_usage.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE ibl_examples (
            intent TEXT, ibl_code TEXT, success_count INTEGER, fail_count INTEGER,
            topic TEXT, alias TEXT, always_on INTEGER, created_at TEXT)""")
        conn.execute("INSERT INTO ibl_examples VALUES (?, ?, 3, 0, '검증', '잠드는관용구', 1, '2026')",
                     ("검증용", '[sense:awake]{}; [sense:awake]{}'))
    before_file = db.read_bytes()
    assert "잠드는관용구" in idioms_map(None)
    set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    assert "잠드는관용구" not in idioms_map(None)
    set_package_active("awake", True, authority=HUMAN_AUTHORITY)
    assert "잠드는관용구" in idioms_map(None)
    assert db.read_bytes() == before_file


def test_held_consciousness_instance_refreshes_without_role_file_change(prompt_box):
    from consciousness_agent import ConsciousnessAgent
    from vocabulary_lifecycle import set_package_active

    agent = object.__new__(ConsciousnessAgent)
    agent._load_prompt()
    before = agent._prompt
    assert "sense:awake ::" in before
    set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    agent._reload_prompt_if_changed()
    assert "sense:awake ::" not in agent._prompt
    assert len(agent._prompt) < len(before)
    set_package_active("awake", True, authority=HUMAN_AUTHORITY)
    agent._reload_prompt_if_changed()
    assert agent._prompt == before


def test_supervisor_catalog_and_contract_follow_activation(prompt_box, monkeypatch):
    from supervisor_runtime import tool_context, action_schema
    from vocabulary_lifecycle import set_package_active
    import thread_context

    monkeypatch.setattr(thread_context, "get_allowed_nodes", lambda: None)
    controller = SimpleNamespace(framing={"capability_focus": {
        "highlight_actions": ["sense:awake", "sense:asleep"]}}, catalog={})
    initial = tool_context(controller)
    assert "sense:awake" in initial["available_actions"]
    assert "sense:asleep" not in initial["available_actions"]
    assert [v["action"] for v in initial["focused_actions"]] == ["sense:awake"]
    set_package_active("awake", False, authority=HUMAN_AUTHORITY)
    assert "sense:awake" not in tool_context(controller)["available_actions"]
    with pytest.raises(ValueError, match="사용할 수 없는"):
        action_schema("sense:awake")
    set_package_active("awake", True, authority=HUMAN_AUTHORITY)
    assert tool_context(controller) == initial
    assert action_schema("sense:awake")["definition"]
    monkeypatch.setattr(thread_context, "get_allowed_nodes", lambda: {"self"})
    assert tool_context(controller)["available_actions"] == []
    with pytest.raises(ValueError, match="사용할 수 없는"):
        action_schema("sense:awake")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
