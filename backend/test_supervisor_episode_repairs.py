"""ep3332의 도구 교정·기억 중복·전체 비용 표기 회귀. 모델/사용자 데이터는 사용하지 않는다."""
import json
import sys
from types import SimpleNamespace

import pytest

import boot_paths  # noqa: F401


def test_multiple_shell_paths_translate_to_scalar_ibl_sentences():
    from shell_shadow_gate import _render, load_table
    from ibl_parser import parse
    spec = load_table()["shadows"]["self:list"]
    sentence = _render("self:list", {"path": ["/first", "/second"]}, spec)
    assert sentence == '[self:list]{path: "/first"} & [self:list]{path: "/second"}'
    program = parse(sentence)
    assert [b["params"]["path"] for b in program[0]["branches"]] == ["/first", "/second"]


@pytest.fixture
def memory_harness(tmp_path, monkeypatch):
    from cognitive_distill import CognitiveDistillMixin
    old = "기존 사실. " * 60 + "뒤쪽에 이미 기록한 중요한 사실"
    state = {"id": 22, "content": old, "keywords": "기존"}
    updates, prompts, saved = [], [], []

    def update(*args, **kw):
        updates.append(kw)
        state.update(kw)

    memory = SimpleNamespace(
        body_noun_leak=lambda text: None,
        _get_db_path=lambda *a: str(tmp_path / "memory.db"),
        search=lambda **kw: [{"id": 22}], read=lambda *a: dict(state),
        update=update, save=lambda **kw: saved.append(kw),
    )
    tree = SimpleNamespace(map_text=lambda *a: "기록", norm_node=lambda text: text)
    monkeypatch.setitem(sys.modules, "memory_db", memory)
    monkeypatch.setitem(sys.modules, "memory_tree", tree)
    runner = CognitiveDistillMixin()
    runner.project_path, runner.agent_id = tmp_path, "test"
    return SimpleNamespace(runner=runner, state=state, updates=updates, prompts=prompts, saved=saved)


def test_memory_merges_same_target_once_and_stores_only_novel_content(memory_harness, monkeypatch):
    h = memory_harness
    facts = [{"content": "추가 사실 A", "keywords": "a"}, {"content": "추가 사실 B", "keywords": "b"}]

    def model(prompt, **kw):
        h.prompts.append(prompt)
        if len(h.prompts) == 1:
            return json.dumps(facts)
        assert "뒤쪽에 이미 기록한 중요한 사실" in prompt  # 200자 뒤 원문도 대조
        assert "추가 사실 A" in prompt and "추가 사실 B" in prompt
        assert "2. 기존:" not in prompt  # 같은 ID를 동시에 세 번 갱신하지 않는다.
        return json.dumps({"verdicts": [{"action": "UPDATE", "content": "새로 확인한 사실 A와 B"}]})

    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", model)
    before = h.state["content"]
    h.runner._distill_deep_memory("작업", "결과")
    assert len(h.updates) == 1 and not h.saved
    assert h.state["content"] == before + "\n[보충] 새로 확인한 사실 A와 B"


def test_already_contained_memory_needs_no_comparison_model_or_write(memory_harness, monkeypatch):
    h = memory_harness
    calls = []

    def model(**kw):
        calls.append(kw)
        return json.dumps([{"content": "뒤쪽에 이미 기록한 중요한 사실", "keywords": "k"}])

    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", model)
    h.runner._distill_deep_memory("작업", "결과")
    assert len(calls) == 1 and not h.updates and not h.saved


@pytest.mark.parametrize("choice", [{"action": "SAME"}, {"action": "UPDATE", "content": ""}, "UPDATE"])
def test_no_new_fact_means_no_memory_update(memory_harness, monkeypatch, choice):
    h = memory_harness
    answers = iter([json.dumps([{"content": "기존 사실을 다시 표현함"}]), json.dumps({"verdicts": [choice]})])
    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", lambda **kw: next(answers))
    h.runner._distill_deep_memory("작업", "결과")
    assert not h.updates and not h.saved


def test_learning_run_keeps_whole_turn_cost_separate_from_ibl_cost(tmp_path, monkeypatch):
    import hippo_tree
    path = tmp_path / "memory.md"
    path.write_text("# 시험\n")
    monkeypatch.setattr(hippo_tree, "doc_path", lambda topic: str(path))
    monkeypatch.setattr(hippo_tree, "_stamp", lambda *a: None)
    cost = {"execution_calls": 48, "execution_failures": 2, "supervisor_tool_failures": 3, "wall_s": 873.7}
    hippo_tree.note_run("시험", "목표", ['[self:list]{path: "."}'], calls=16, failed=0, turn_cost=cost)
    text = path.read_text()
    assert "호출 16 · 실패 0" in text
    assert '"execution_calls": 48' in text and '"supervisor_tool_failures": 3' in text
    assert "위 머리는 IBL만" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
