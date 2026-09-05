"""자기반성 게이트의 op 축 + 반성기 병렬 문장 규칙 (2026-09-05, ep2838·2837 검토 수리).

  O1  `[self:memory]{op:"recall"}` 처럼 **op 수준에서 읽기로 선언된 호출은 read** — 액션 롤업(side_effect:true)에 갇히지 않는다.
      같은 낱말의 쓰기 op(save)는 write. 실측: 2주 usage 에서 '부작용 액션' 사유 58회 중 읽기 op 다수, 반성 라운드 중앙값 46초.
  O2  병렬(&)·여러 문장 프로그램도 낱낱이 op 로 판정 — 전부 읽기면 read, 하나라도 쓰기면 그 op 를 이름 불러 write.
  O3  파서가 못 펴는 자리(do 문자열 안의 액션)는 액션 롤업(보수)으로 — 쓰기 낱말이 do 안에 있으면 write.
  O4  should_self_reflect: 읽기 op 만 부른 성공 궤적은 반성을 돌리지 않는다("읽기만 한 궤적").
  P1  증류 프롬프트 규칙 7 이 "`&` 병렬 문장은 통째로" 를 말한다(ep2837: 반성기가 한 가지만 떼어 접지 관문에 걸림).
실 사전(ibl_nodes.yaml)·안전지도는 읽기만. 실행: .venv/bin/python -m pytest backend/test_reflect_gate_op_axis_2026_09_05.py -q
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

import cognitive_trace as ct  # noqa: E402


def _ibl(code, result='{"success": true, "items": [{"a": 1}]}'):
    return {"name": "mcp__indiebizos__execute_ibl", "input": {"code": code}, "result": result, "is_error": False}


def _kind(code):
    return ct._classify_call(_ibl(code), ct._ibl_safety_map(), ct._ibl_op_safety_map())


# ---------------------------------------------------------------- O1 읽기 op vs 쓰기 op
def test_o1_read_op_inside_side_effect_action_is_read():
    assert ct._ibl_safety_map().get(("self", "memory")) is False          # 액션 롤업은 쓰기(파괴적 op 보유)
    assert ct._ibl_op_safety_map().get(("self", "memory", "recall")) is True
    kind, why = _kind('[self:memory]{op: "recall", node: "사용자 신념"}')
    assert kind == "read", why
    kind, why = _kind('[self:memory]{op: "save", node: "x", content: "y"}')
    assert kind == "write" and "self:memory" in why and 'op: "save"' in why
    assert _kind('[self:script]{op: "list"}')[0] == "read"
    assert _kind('[self:script]{op: "run", id: "시험"}')[0] == "write"


# ---------------------------------------------------------------- O2 병렬·다문장
def test_o2_parallel_and_multi_statement_programs():
    assert _kind('[self:memory]{op: "recall", node: "a"} & [self:memory]{op: "recall", node: "b"}')[0] == "read"
    assert _kind('[self:memory]{op: "recall", node: "a"}\n[self:memory]{op: "recall", node: "b"}\n[self:time]{}')[0] == "read"
    kind, why = _kind('[self:memory]{op: "recall", node: "a"}\n[self:memory]{op: "save", node: "a", content: "c"}')
    assert kind == "write" and 'op: "save"' in why


# ---------------------------------------------------------------- O3 do 안의 쓰기
def test_o3_write_inside_each_do_is_conservative_write():
    kind, _ = _kind('[self:memory]{op: "recall", node: "a"} >> [table:each]{do: "[self:write]{path: \'$it.p\', content: \'x\'}"}')
    assert kind == "write"


# ---------------------------------------------------------------- O4 게이트 전체
def test_o4_recall_only_trajectory_skips_reflection():
    calls = [_ibl('[self:memory]{op: "recall", node: "사용자 신념"}\n[self:memory]{op: "recall", node: "AI 교육 시장"}'),
             _ibl('[self:memory]{op: "recall", node: "사용자 신념"}'),
             _ibl('[self:memory]{op: "recall", node: "사용자 신념/indiebizOS"}')]
    go, why = ct.should_self_reflect(calls)
    assert go is False and "읽기만" in why, why
    calls.append(_ibl('[self:memory]{op: "save", node: "x", content: "y"}'))
    go, why = ct.should_self_reflect(calls)
    assert go is True and "부작용 액션" in why


# ---------------------------------------------------------------- P1 반성기 규칙
def test_p1_distill_prompt_keeps_parallel_sentences_whole():
    import ibl_usage_rag as rag
    p = rag._build_distill_prompt("u", "  1. [self:time]{}", "", "")
    assert "병렬 실행된 문장은" in p and "통째로" in p


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
