"""의식 출력 키 라우팅 관문 — 채워지는데 아무도 안 읽는 필드 금지 (2026-09-07).

실측 배경: `capability_focus.tools` 는 의식 출력의 84.9%(225/265 에피소드)에 채워졌고
`primary_nodes` 는 96.2%에 채워졌지만, 라이브 경로(compile_user_command + turn_context)
어디에도 실리지 않았다. tools 는 도입(2026-03-30) 이래 프롬프트 조립에 읽힌 적이 한 번도
없고(`git log -S`), 그걸 정제하는 필터(_filter_unavailable_tools, 2026-05-28)는 존재한 적
없는 통로를 지키고 있었다. primary_nodes 의 유일한 독자는 skip_dynamic=False 분기인데,
두 표면 모두 split 경로를 쓰므로 도달 불가였다.

이 관문이 고정하는 것: **의식 프롬프트의 응답 형식에 있는 키는 전부 살아있는 소비처에
닿는다.** 새 키를 프롬프트에 추가하면 여기 등록해야 하고, 닿는 곳이 없으면 필드를 지워야
한다(출력 토큰은 매 턴의 지연이다).

검증 방식은 grep 이 아니라 *실제 조립* — 키마다 고유 표식을 심어 조립된 글에서 찾는다.
불리언 키는 뒤집었을 때 소비처의 답이 달라지는지로 본다.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "data" / "common_prompts" / "consciousness_prompt.md"

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "cognition"))


def _prompt_schema_keys() -> set:
    """의식 프롬프트 '응답 형식' 예시 JSON 의 키 집합 (중첩은 'a.b' 로)."""
    text = PROMPT.read_text(encoding="utf-8")
    body = text.split("## 응답 형식", 1)[1]
    m = re.search(r"```json\n(\{.*?\n\})\n```", body, re.S)
    assert m, "응답 형식에 json 예시 블록이 없다"
    example = json.loads(m.group(1))
    keys = set()
    for k, v in example.items():
        if isinstance(v, dict):
            keys.update(f"{k}.{sub}" for sub in v)
        else:
            keys.add(k)
    return keys


def _sentinel(key: str) -> str:
    return "SENTINEL~" + key.replace(".", "~")


def _fill(keys) -> dict:
    """모든 키에 고유 표식을 심은 의식 출력을 만든다."""
    out = {"capability_focus": {}}
    for key in keys:
        head, _, sub = key.partition(".")
        target, name = (out["capability_focus"], sub) if sub else (out, head)
        if name in ("assumptions", "guide_files", "highlight_actions", "primary_nodes", "tools"):
            target[name] = [_sentinel(key)]
        elif name == "criteria":
            target[name] = [{"text": _sentinel(key), "user_quote": "", "fallback": "한계를 명시"}]
        elif name.startswith("needs_"):
            target[name] = True
        else:
            target[name] = _sentinel(key)
    return out


class _Mixin:
    """파이프라인 소비처(제어 키)만 떼어낸 최소 몸."""
    def __init__(self):
        from cognitive_consciousness import CognitiveConsciousnessMixin
        self.__class__ = type("_M", (CognitiveConsciousnessMixin,), {})


@pytest.mark.parametrize("summary", ["", " \n\t "])
def test_no_relevant_history_is_an_explicit_empty_context(summary):
    from copy import deepcopy
    from cognitive_consciousness import CognitiveConsciousnessMixin
    history = [{"role": "user", "content": "블루칼라 보고서만 표로 작성해"},
               {"role": "assistant", "content": "이전 보고서를 진행하겠습니다."}]
    original = deepcopy(history)
    output = {"task_framing": "제주 관광 유입 원인을 설명한다", "history_summary": summary}
    assert CognitiveConsciousnessMixin()._apply_consciousness_to_history(history, output) == []
    assert history == original  # 전달 맥락만 비우고 원문은 보존한다.


@pytest.mark.parametrize("output", [None, {}, {"task_framing": "현재 문제"},
                                    {"history_summary": None}, {"history_summary": False},
                                    {"history_summary": []}, {"history_summary": {}}])
def test_missing_or_invalid_history_decision_does_not_erase_context(output):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    history = [{"role": "user", "content": "제주 통계를 조사해"}]
    assert CognitiveConsciousnessMixin()._apply_consciousness_to_history(history, output) is history


def test_partial_history_preserves_referent_and_correction_without_old_constraints():
    from cognitive_consciousness import CognitiveConsciousnessMixin
    history = [{"role": "user", "content": "블루칼라 보고서는 표만 작성해"},
               {"role": "user", "content": "제주 관광을 2024년 기준으로 조사해"},
               {"role": "user", "content": "아니, 그 비교 기간은 2025년으로 고쳐"}]
    summary = "제주 관광 비교 작업을 이어간다. 사용자가 비교 기간을 2025년으로 정정했다."
    result = CognitiveConsciousnessMixin()._apply_consciousness_to_history(
        history, {"task_framing": "제주 관광을 2025년 기준으로 비교", "history_summary": summary})
    assert len(result) == 1 and summary in result[0]["content"]
    assert result[0]["_history_replacement"] is True
    assert "블루칼라" not in result[0]["content"] and "2024" not in result[0]["content"]
    assert len(history) == 3


def _assembled_text(co: dict) -> str:
    """실행자·평가·재규정이 실제로 조립하는 글 전부를 이어 붙인다."""
    from prompt_builder import compile_user_command, _build_dynamic_context
    from cognitive_consciousness import CognitiveConsciousnessMixin

    parts = [compile_user_command("표식 요청", co),
             _build_dynamic_context(co, model_name="테스트모델", execution_memory="")]

    # history_summary — 원본 히스토리를 대체하는 경로
    holder = CognitiveConsciousnessMixin()
    parts.append(json.dumps(
        holder._apply_consciousness_to_history([{"role": "user", "content": "원본"}], co),
        ensure_ascii=False))
    # clarification — needs_clarification=true 일 때의 질문 경로
    parts.append(str(holder._consciousness_clarification(co)))
    return "\n".join(p for p in parts if p)


# 불리언 키 = 뒤집었을 때 소비처의 답이 달라지는지로 본다.
def _bool_probes():
    from cognitive_consciousness import CognitiveConsciousnessMixin
    holder = CognitiveConsciousnessMixin()
    return {
        "needs_clarification": lambda v: holder._consciousness_clarification(
            {"needs_clarification": v, "clarification_question": "질문"}),
        "needs_repair": lambda v: holder._consciousness_needs_repair({"needs_repair": v}),
    }


def test_every_prompt_key_reaches_a_consumer(tmp_path):
    keys = _prompt_schema_keys()
    co = {**_fill(keys), "pursuit_id": None}
    from pursuit_bind import Binding, _current, accept_output
    from pursuit_ledger import PursuitLedger
    ledger = PursuitLedger(tmp_path / "pursuit.db", "routing-test")
    binding = Binding(None, ledger, "routing-test", "routing-turn", "과제", [])
    token = _current.set(binding)
    try:
        accept_output({**co, "scope": "turn"})
        assert binding.row is None
        accept_output({**co, "scope": "pursuit"})
        assert binding.row is not None
        assert binding.row["title"] == _sentinel("title")
        assert binding.row["goal_criteria"] == _sentinel("goal_criteria")
        pid = binding.row["id"]
        accept_output({**co, "scope": "turn", "detach_pursuit": True})
        assert binding.row is None
        old = ledger.create("기존", "기존 목표", "other")
        accept_output({**co, "scope": "turn", "pursuit_id": old["id"],
                       "pursuit_reason": _sentinel("pursuit_reason")})
        assert binding.row["id"] == old["id"]
        assert ledger.get(pid)["title"] == _sentinel("title")
        assert ledger.turns(pid)[0]["state"] == "detached"
    finally:
        _current.reset(token)
    keys -= {"scope", "title", "goal_criteria", "detach_pursuit", "pursuit_id", "pursuit_reason"}
    text = _assembled_text(co)
    probes = _bool_probes()

    dead = []
    for key in sorted(keys):
        name = key.rpartition(".")[2]
        if name.startswith("needs_"):
            probe = probes.get(name)
            if probe is None:
                dead.append(f"{key} (불리언인데 소비처 프로브 미등록)")
            elif probe(True) == probe(False):
                dead.append(f"{key} (뒤집어도 소비처의 답이 같다)")
            continue
        if _sentinel(key) not in text:
            dead.append(f"{key} (조립된 글 어디에도 안 실린다)")

    assert not dead, (
        "의식이 채우지만 아무 데도 닿지 않는 키:\n  - " + "\n  - ".join(dead) +
        "\n\n소비처를 만들거나 필드를 프롬프트에서 지워라 — 출력 토큰은 매 턴의 지연이다."
    )


def test_reframe_reply_carries_the_same_keys():
    """재규정(reframe) 응답도 같은 칸들을 싣는다 — 한 자리에서만 살면 재규정 뒤 사라진다."""
    import reframe
    keys = {k for k in _prompt_schema_keys()
            if k in ("task_framing", "expert_choice", "assumptions",
                     "achievement_criteria", "capability_focus.hint",
                     "capability_focus.highlight_actions")}
    co = _fill(keys)
    co["_revision"] = {"revision_no": 1}
    rendered = reframe.render_for_executor({"revised": True, "output": co})
    for key in sorted(keys):
        assert _sentinel(key) in rendered, f"재규정 응답에 {key} 가 빠졌다:\n{rendered}"


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(pytest.main([__file__, "-v"]))
