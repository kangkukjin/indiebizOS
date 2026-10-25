"""실패 문법의 정직성 회귀 — 30회차 (2026-08-23)

30회차 축 = **실패 문법(8) × 실패 원인(12) = 96칸**. 코퍼스 3,582문장 중 오류 경로를
밟는 문장이 **28건(0.78%)** 뿐이라, 언어의 '고장 나는 쪽 절반'은 거의 시험된 적이 없었다.

재현하는 결함(전부 실측):
  B30-1 **`[try]{[A] & [B]}` 가 엉뚱한 문구로 죽는다.**
     파서는 병렬을 `{"_parallel": [...]}` 한 step 으로 내는데, `execute_ibl` 의 블록
     디스패치 목록(`_goal`/`_condition`/`_case`/`_try`/`_repeat`/`_assign`)에 `_parallel`
     만 빠져 있었다. 블록 몸은 `_run_body` 가 dict 를 `execute_ibl` 로 곧장 넘기므로
     아래 `action` 검사까지 떨어져 이렇게 죽었다:
         _caught = {"error": "action 파라미터가 필요합니다.", "node": null, "action": null}
     ★봉투가 스스로 "무엇이 죽었는지 모른다"고 자백한다(node·action 이 null).
     ★같은 부류를 코드가 이미 이름 붙여 알고 있었다 — system_tools_ibl.py 의
       "전 표면 블록 실행 봉쇄 부류" 주석. 최상위 경로는 고쳤고 블록 몸은 안 고쳤다.
     대조: `??` 는 같은 한계를 **검수 시점에 정확히** 거절한다("& 와 ?? 를 섞을 수 없습니다").
     같은 한계를 두 문법이 다르게 말하면 안 된다.

  B30-2 **서킷 브레이커가 블록 문장을 전부 빈 키 하나로 뭉쳤다.**
     `_fail_key = f"{agent}:{_node}:{_action}"` 인데 블록 문장은 node·action 이 비어
     모든 블록이 `agent::` **한 바구니**에 들어갔다. 서로 무관한 블록 셋이 실패하면
     *모든* 블록 문장이 90초 차단됐고 메시지는 `[:] 액션이 연속 3회 실패…` 라며 아무
     이름도 대지 못했다. 실측: 한 훈련 회차에 빈 키 차단 **36회**.
     ★게다가 판정이 **두 벌**이었다(체크 지점·갱신 지점이 각자 키를 조립) — 그래서 같은
       실수가 두 곳에 있었다. 수리는 `_breaker_key()` 한 벌로 모았다.

  B30-3 **리허설의 의도된 실패가 사용자의 실제 호출을 차단할 수 있었다.**
     훈련은 갭을 찾으려고 `ZZZZINVALID` 를 일부러 밟는데, 그 실패가 차단기를 열면
     그 90초 동안 사용자의 진짜 `[sense:stock]` 호출까지 막힌다. E28-3('리허설은 삶이
     아니다')이 건강 원장에 내린 판정과 같은 규율을 차단기에도 적용 — **지우지 않고
     키 공간을 분리**한다(훈련 안에서의 폭주 방어는 그대로 산다).

실행: .venv/bin/python -m pytest backend/test_failure_grammar_honesty.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


# ── B30-2 / B30-3: 차단기 판정은 한 벌 ────────────────────────────────











# ── B30-1: 블록 몸의 병렬 ────────────────────────────────────────────





# ── F30-1: 정직 표지가 교재에서 가르쳐지는가 ──────────────────────────

def test_R7_봉투_정직_표지가_교재에_있다():
    """몸이 표지를 달아도 읽는 법을 안 가르치면 아무도 안 본다.

    30회차 실측: `_fallback_used`·`ok_count`/`error_count`·`rows_in` 은 몸이 실제로
    싣는데 공통 프롬프트·어휘 src 어디에도 **0회** 언급이었다. 특히 `_fallback_used` 는
    데이터의 *출처가 바뀌었다*는 표지라, 못 읽으면 검색 결과를 시세라고 보고하게 된다.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 이 검사는 저장 원문의 구형 실행 계약이다. 현재 교재는 test_ibl_composition_teaching에서 실행한다.
    frag = os.path.join(root, "docs", "compatibility", "ibl_legacy_language.md")
    src = open(frag, encoding="utf-8").read()
    for marker in ("_fallback_used", "ok_count", "error_count", "rows_in",
                   "skipped_steps", "_caught", "condition_errors", "halted"):
        assert marker in src, f"교재가 정직 표지 '{marker}' 를 가르치지 않는다"




# ── B48-1 / B48-2 (48회차, 2026-08-27): 표지가 조합 경계를 못 건넌다 ──────────
#
# 48회차 축 = **정직 표지 × 조합 경로**. 표지가 *붙는지*(R7·R8 이 본 것)와
# 표지가 *경계를 건너는지*는 다른 질문이고, 후자는 한 번도 시험된 적이 없었다.


def test_R9_표지_목록은_단일_소스다():
    """B48-1: 표지 목록이 자리마다 **손으로 열거**돼 있어서, 열거에서 빠진 키는
    그 경계에서 조용히 사라졌다(B24-1 병렬·B27-4 블록몸·F35-1 폴백에 이은 네 번째).
    교재가 가르치는 표지와 코드가 아는 표지가 어긋나면 모델은 없는 것을 찾는다."""
    from ibl_honesty import HONESTY_KEYS, markers_of
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 이 검사는 저장 원문의 구형 실행 계약이다. 현재 교재는 test_ibl_composition_teaching에서 실행한다.
    frag = os.path.join(root, "docs", "compatibility", "ibl_legacy_language.md")
    src = open(frag, encoding="utf-8").read()
    for marker in HONESTY_KEYS:
        assert marker in src, f"코드는 표지 '{marker}' 를 아는데 교재가 안 가르친다"
    # 걷는 쪽도 같은 목록을 쓴다 — 빈 값은 소음이므로 싣지 않는다.
    assert markers_of({"error_count": 2, "passthrough_rows": 0, "items": [1]}) == {"error_count": 2}
    assert markers_of('{"truncated": true}') == {"truncated": True}   # 문자열 봉투도 푼다
    assert markers_of("평문") == {} and markers_of(None) == {}






if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
