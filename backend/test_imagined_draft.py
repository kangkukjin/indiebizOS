"""상상실행 초안 관문 — 의식의 IBL 초안이 기계 앞모형을 거쳐 융합되는지 (2026-08-31).

배경(사용자 판정 집행): 의식은 문제를 규정하며 액션 이름과 산문 절차만 넘겼다 — 산문은
불가능성(안 흐르는 통화·없는 파라미터)을 숨긴다. imagined_ibl 초안은 계획을 액추에이터의
언어로 강제해 문장 짓기 자체가 계획의 시험이 되게 한다.

계약 3조:
  ① 초안은 검증 대상 — 기계 앞모형(파서·액션 실재·파라미터·T1/T2 통화 타입, LLM 0)을
     통과해야 강한 출발점, 실패하면 오류 동반 참고로 강등(validate_imagined_draft).
  ② 초안은 턴-로컬 — 해마 코퍼스에 직접 들어가는 경로가 없다(합성 접지 원칙).
     채택·실행·성공한 초안만 기존 증류가 *실행된 형태*로 거둬간다(일방향 밸브).
  ③ 채택은 관찰 — draft_adoption 액션 교집합 판정으로 [상상실행] 로그 한 줄(게이트 아님).

실행: .venv/bin/python -m pytest backend/test_imagined_draft.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

from prompt_builder import (validate_imagined_draft, draft_adoption,
                            compile_user_command)


def _any_real_action(node="sense"):
    """현재 어휘에서 실재하는 액션 하나 — 어휘 드리프트에 시험이 안 죽게 동적으로 뽑는다."""
    from ibl_access import load_nodes_raw
    actions = (load_nodes_raw() or {}).get("nodes", {}).get(node, {}).get("actions", {})
    assert actions, f"{node} 노드에 액션이 없다 — 어휘 로드 실패?"
    return next(iter(actions))


# ── V: 검증기 — 4겹 앞모형 ────────────────────────────────────────────────

def test_v1_valid_draft_passes():
    act = _any_real_action("sense")
    ok, err = validate_imagined_draft(f"[sense:{act}]{{}}")
    assert ok and err == ""


def test_v2_prose_draft_rejected():
    # 파서는 산문·미완성 조각을 조용히 삼킬 수 있다(빈 params 강등) — 액션 패턴이
    # 아예 없는 초안은 ⓪겹이 IBL 아님으로 거절해야 한다.
    ok, err = validate_imagined_draft("검색해서 정리한 뒤 보고서를 만든다")
    assert not ok and "액션" in err


def test_v3_hallucinated_action_rejected():
    ok, err = validate_imagined_draft("[sense:teleport_to_mars]{}")
    assert not ok and "미존재" in err
    ok2, err2 = validate_imagined_draft("[ghost_node:anything]{}")  # 미존재 노드도 동일
    assert not ok2 and "미존재" in err2


def _param_declaring_action():
    """선언 파라미터가 있는 sense 액션 하나 — 파라미터 어휘 검사가 실제로 무는 표본.

    (선언 없는 액션은 check_code_params 가 빈 손을 돌려줘 겹이 헛돈다 — v4 첫 판이
    'world'를 뽑아 초록 거짓이 될 뻔한 실측.)"""
    from ibl_access import load_nodes_raw
    from ibl_param_vocab import check_code_params
    actions = (load_nodes_raw() or {}).get("nodes", {}).get("sense", {}).get("actions", {})
    for a in actions:
        if check_code_params(f'[sense:{a}]{{definitely_not_a_param_xyz:"1"}}'):
            return a
    pytest.fail("선언 파라미터를 가진 sense 액션이 하나도 없다 — 어휘 회귀?")


def test_v4_unknown_param_rejected():
    act = _param_declaring_action()
    ok, err = validate_imagined_draft(
        f'[sense:{act}]{{definitely_not_a_param_xyz:"1"}}')
    assert not ok and "파라미터" in err


def test_v5_t1_starved_head_rejected():
    # 머리 변환자가 통화 없이 서 있음 — T1 이 실행 전 거절하는 모양 그대로
    ok, err = validate_imagined_draft('[table:sort]{by:"price"}')
    assert not ok and err  # 안내 문장 동반


def test_v6_empty_draft_rejected():
    assert validate_imagined_draft("")[0] is False
    assert validate_imagined_draft("   ")[0] is False


# ── F: 융합 — 통과분은 출발점, 실패분은 오류 동반 강등 ──────────────────────

def _co(draft):
    return {"task_framing": "테스트 문제 규정", "imagined_ibl": draft}


def test_f1_valid_draft_fused_as_starting_point():
    act = _any_real_action("sense")
    out = compile_user_command("메일 확인해줘", _co(f"[sense:{act}]{{}}"))
    assert "실행 초안(기계 검증 통과)" in out
    assert f"[sense:{act}]{{}}" in out
    assert "출발점" in out


def test_f2_invalid_draft_demoted_with_error():
    out = compile_user_command("정렬해줘", _co('[sense:teleport_to_mars]{}'))
    assert "검증 실패" in out and "미존재" in out
    assert "출발점" not in out            # 권위 문구 없음 — 강등
    assert "직접 재구성" in out


def test_f3_no_draft_no_mention():
    out = compile_user_command("메일 확인해줘", {"task_framing": "규정"})
    assert "실행 초안" not in out


# ── A: 채택 관찰 — 액션 교집합, 게이트 아님 ────────────────────────────────

def test_a1_adoption_detection():
    draft = '[sense:email]{} >> [table:sort]{by:"date"}'
    used = [{"tool_name": "execute_ibl",
             "input": {"code": '[sense:email]{limit:5}'}, "success": True}]
    other = [{"tool_name": "execute_ibl",
              "input": {"code": '[self:script]{}'}, "success": True}]
    assert draft_adoption(draft, used) is True       # 교집합 있음 = 채택
    assert draft_adoption(draft, other) is False     # 실행했지만 다른 길 = 미채택
    assert draft_adoption(draft, []) is None         # 실행 없음 = 판정 불가
    assert draft_adoption("", used) is None          # 초안 없음 = 판정 불가


# ── 밸브: 초안이 해마로 새는 직접 경로가 없다 ──────────────────────────────

def test_valve_no_direct_corpus_path():
    """구조 검사: prompt_builder(초안의 집)는 해마 쓰기(add_example)를 모른다.

    상상→실행→기억 일방향 밸브의 기계 확인 — 초안 코드가 실행을 거치지 않고
    코퍼스에 들어가는 import 경로가 생기면 이 시험이 막는다(합성 접지 원칙)."""
    import inspect
    import prompt_builder
    src = inspect.getsource(prompt_builder)
    assert "add_example" not in src
    assert "add_examples_batch" not in src


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
