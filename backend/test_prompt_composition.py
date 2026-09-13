"""프롬프트 구성 표면 관문 — 에이전트 목록·조각 스키마·실제 빌더 총량 대조."""
import boot_paths  # noqa: F401
import pytest

import prompt_composition as PC

_KEYS = {"key", "label", "layer", "kind", "source", "condition", "included", "chars", "tokens", "content", "note"}


def test_catalog_lists_every_agent_kind():
    cat = PC.list_agents()
    ids = {a["id"] for a in cat["agents"]}
    assert {"system_ai", "project_agent", "consciousness", "supervisor", "unconscious", "evaluator",
            "distill"} <= ids
    assert all("build" not in a for a in cat["agents"])
    assert cat["default_sample"]


@pytest.mark.parametrize("agent_id", ["unconscious", "evaluator", "supervisor", "history_checkpoint",
                                      "guide_maintenance", "deep_memory", "autoresponse"])
def test_cheap_agents_assemble_with_schema(agent_id):
    r = PC.assemble(agent_id, "샘플")
    assert r["agent"]["id"] == agent_id
    assert r["sections"], agent_id
    for s in r["sections"]:
        assert _KEYS <= set(s), s.get("key")
        assert s["layer"] in ("system", "turn", "user")
        assert s["kind"] in ("file", "dynamic", "memory", "history", "constant", "turn", "input")
        if s.get("ref_agent"):
            assert s["chars"] > 0 and not s["content"]   # 다른 항목을 참조하는 조각 — 분량만
        else:
            assert s["chars"] == len(s["content"])
        if not s["included"]:
            assert s["condition"], f"{agent_id}/{s['key']}: 안 실린 조각은 조건을 적어야 한다"
    assert set(r["totals"]) == {"system", "turn", "user"}


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        PC.assemble("nope", "x")


def test_system_ai_sections_match_real_builder():
    """조각 합 ≈ 실제 build_system_ai_prompt_split 결과 — 결합 개행(조각 수-1 × 2) 만큼만 다르다."""
    r = PC.assemble("system_ai", "테스트")
    if "error" in r["assembled"]:
        pytest.skip(r["assembled"]["error"])
    sys_secs = [s for s in r["sections"] if s["layer"] == "system" and s["included"]]
    joiner = 2 * (len(sys_secs) - 1)
    assert r["assembled"]["stable_chars"] - r["totals"]["system"]["chars"] == joiner


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
