"""증류 할당 앞점 복원 회귀 — ACHIEVED 주행이 `$변수` 하나 때문에 학습 0건이 되던 자리 (2026-09-06).

재현하는 결함(실측 ep2905 `$실패`·ep2943 `$fx`): 실행은
    $fx = [a] & [b] >> [table:union]
    $fx >> [table:select]{…}
였는데 반성기가 옮기면서 좌변 `$fx = ` 만 떨어뜨렸다. 구문 관문이 "변수 $fx 이(가) 앞에서
할당되지 않았습니다" 로 거절 → GoalEval ACHIEVED 인 주행에서 낱말도 관용구도 안 남았다.
30일 창에서 2건, 둘 다 실사용 턴이다.

고정하는 계약 다섯:
  A1  떨어진 좌변은 *실행 이력의* 할당문에서 되살린다 — 복원 뒤 코드가 파싱된다.
  A2  같은 문장인지는 접지 게이트와 같은 자로 묻는다: 머리 열의 순서 보존 부분열
      (증류=압축이므로 부분집합 허용). 머리가 안 맞으면 복원하지 않는다.
  A3  이름을 지어내지 않는다 — 실행에 그 할당이 없으면 종전대로 거절(정직한 실패).
  A4  후보 이름이 갈리면(같은 머리 열의 서로 다른 좌변) 손대지 않는다.
  A5  복원은 원문 표기(줄바꿈·간격)를 건드리지 않고 앞점만 끼운다. 멀쩡한 코드는 무변경.

실행: .venv/bin/python -m pytest backend/test_distill_var_assignment_2026_09_06.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from ibl_param_vocab import code_syntax_error  # noqa: E402
from cognition.ibl_usage_rag import (  # noqa: E402
    _restore_var_assignments,
    _syntax_gate_with_restore,
)

# ep2943 실행 원문(축약 없이 같은 모양)
EXECUTED = [
    '$fx = [sense:stock]{op: "quote", ticker: "KRW=X"} & [sense:stock]{op: "quote", ticker: "DX-Y.NYB"}'
    ' & [sense:stock]{op: "quote", ticker: "JPY=X"} >> [table:union]\n'
    '$fx >> [table:select]{columns: ["symbol", "current_price"]}',
]
# 반성기가 낸 것 — 좌변만 없다
DROPPED = ('[sense:stock]{op: "quote", ticker: "KRW=X"} & [sense:stock]{op: "quote", ticker: "DX-Y.NYB"}'
           ' & [sense:stock]{op: "quote", ticker: "JPY=X"} >> [table:union]\n'
           '$fx >> [table:select]{columns: ["symbol", "current_price"]}')


def test_a1_restores_and_parses():
    assert code_syntax_error(DROPPED), "전제: 떨어진 코드는 구문 관문에 걸린다"
    fixed, restored = _restore_var_assignments(DROPPED, EXECUTED)
    assert restored == ["fx"]
    assert fixed.startswith("$fx = [sense:stock]")
    assert code_syntax_error(fixed) is None


def test_a2_compressed_statement_still_grounds():
    """증류가 병렬 가지를 줄여도(압축) 머리 열 부분열이면 되살린다."""
    compressed = ('[sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]\n'
                  '$fx >> [table:select]{columns: ["symbol"]}')
    fixed, restored = _restore_var_assignments(compressed, EXECUTED)
    assert restored == ["fx"]
    assert code_syntax_error(fixed) is None


def test_a2b_head_mismatch_is_not_restored():
    """머리가 실행 할당문에 없으면 복원하지 않는다 — 아무 문장에나 이름을 붙이지 않는다."""
    other = ('[sense:search]{source: "gnews", query: "환율"}\n'
             '$fx >> [table:select]{columns: ["symbol"]}')
    fixed, restored = _restore_var_assignments(other, EXECUTED)
    assert restored == []
    assert fixed == other


def test_a3_no_invention_when_execution_has_no_assignment():
    executed_without_assign = ['[sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]']
    code, err = _syntax_gate_with_restore(DROPPED, executed_without_assign, "[시험]")
    assert err and "할당되지 않았습니다" in err
    assert code == DROPPED


def test_a4_ambiguous_candidates_are_left_alone():
    """같은 머리 열의 서로 다른 좌변이 둘 — 고르는 것은 창작이므로 손대지 않는다."""
    executed = [
        '$a = [sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]',
        '$b = [sense:stock]{op: "quote", ticker: "JPY=X"} >> [table:union]',
    ]
    code = ('[sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]\n'
            '$a & $b >> [table:select]{columns: ["symbol"]}')
    fixed, restored = _restore_var_assignments(code, executed)
    assert restored == []
    assert fixed == code


def test_a5_healthy_code_untouched():
    healthy = ('$fx = [sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]\n'
               '$fx >> [table:select]{columns: ["symbol"]}')
    assert code_syntax_error(healthy) is None
    fixed, restored = _restore_var_assignments(healthy, EXECUTED)
    assert restored == [] and fixed == healthy
    code, err = _syntax_gate_with_restore(healthy, EXECUTED, "[시험]")
    assert err is None and code == healthy


def test_a5b_separator_preserved():
    """`;` 로 이은 관용구 표기도 그대로 — 앞점만 끼운다."""
    joined = ('[sense:stock]{op: "quote", ticker: "KRW=X"} >> [table:union]; '
              '$fx >> [table:select]{columns: ["symbol"]}')
    fixed, restored = _restore_var_assignments(joined, EXECUTED)
    assert restored == ["fx"]
    assert "; $fx >> [table:select]" in fixed
    assert code_syntax_error(fixed) is None


def test_gate_is_single_owner_for_both_paths():
    """관용구 경로도 같은 문을 쓴다 — 관문이 두 벌이면 방언이 갈린다."""
    import inspect
    from cognition import ibl_idiom
    src = inspect.getsource(ibl_idiom._distill_phrase)
    assert "_syntax_gate_with_restore" in src
    assert "code_syntax_error(code)" not in src


if __name__ == "__main__":
    pytest.main([__file__])
