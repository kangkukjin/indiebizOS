"""관용구 접지의 단위 = 실행 **문장** (2026-09-07).

재현하는 결함(ep2943 실측): 한 execute_ibl 호출은 대개 여러 독립 문장을 담은 *프로그램*
인데, `_phrase_grounded` 는 호출 하나를 통째로 한 서명으로 접어 관용구 문장(=한 문장)과
비교했다. 문장 수가 다르면 `len(p_acts) != len(c_acts)` 에서 반드시 어긋나므로 **실행된
문장을 글자 그대로 관용구에 넣어도 접지에 실패**했다 — 여러 줄로 일하는 턴, 곧 배울
값어치가 있는 턴일수록 확실히 떨어지는 관문이었다. 결정론적 재현(실행 문장을 그대로
관용구로): 231턴 중 58턴(25%) 거부 → 0턴. 08-25~09-06 실사용 접지 실패 12건도 같은 뿌리
(호출 경계에서 온 거짓 매칭이 `pos` 를 먼저 소비해 '순서 어긋남'으로 둔갑한 것 포함).

고정하는 계약:
  G1  실행된 문장을 그대로 넣으면 접지된다 — 다문장 프로그램에서도. (관문의 최소 요건)
  G2  실행에 없던 액션 머리는 거절.
  G3  별개 문장을 `>>` 로 봉합한 거짓 흐름은 거절 — 흐름 접지는 *한 문장* 안이다
      (문장 단위로 자르면서 오히려 엄격해진 자리: 종전엔 한 호출 안 아무 데나 있으면 됐다).
  G4  실행 순서를 뒤집으면 거절(부분열 규약).
  G5  액션 없는 문장: 산문은 거절, 상수 바인딩(`$기준 = "…"`)은 이 주행이 같은 이름을
      같은 방식으로 묶었을 때만 통과(ep2882 실측 — 슬롯이 앉는 자리).
  G6  인자 키가 실행보다 많으면 거절(관용구는 실행의 압축이지 확장이 아니다).
  G7  문장 자르기는 조용히 되돌아가지 않는다 — `_statements_of` 가 실패를 삼키면 관문이
      옛 결함으로 복귀하면서 아무 신호도 안 남는다(수리 중 실측).

실행: .venv/bin/python -m pytest backend/test_idiom_grounding_statement_unit_2026_09_07.py -q
"""
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from cognition.ibl_idiom import _phrase_grounded, _statements_of  # noqa: E402

# ep2943 첫 호출 — 4문장짜리 프로그램(실물 모양)
PROGRAM = (
    '$fx = [sense:stock]{op: "quote", ticker: "KRW=X"} & [sense:stock]{op: "quote", ticker: "DX-Y.NYB"}'
    ' >> [table:union]\n'
    '$fx >> [table:select]{columns: ["symbol", "current_price"]}\n'
    '[sense:stock]{op: "history", ticker: "KRW=X", period: "1y"} >> [table:take]{n: -6}\n'
    '[sense:kosis]{query: "외환보유액"}'
)
CALLS = [PROGRAM]


def test_g1_executed_statements_ground_verbatim():
    stmts = _statements_of(PROGRAM)
    assert len(stmts) == 4, "전제: 한 호출이 4문장짜리 프로그램"
    assert _phrase_grounded(stmts[:3], {}, CALLS) is None


def test_g1b_slotted_statements_still_ground():
    phrase = [
        '$fx = [sense:stock]{op: "quote", ticker: "${통화1}"} & [sense:stock]{op: "quote", ticker: "${통화2}"}'
        ' >> [table:union]',
        '[sense:stock]{op: "history", ticker: "${통화1}", period: "${기간}"} >> [table:take]{n: $n}',
    ]
    assert _phrase_grounded(phrase, {"통화1": "KRW=X", "통화2": "DX-Y.NYB", "기간": "1y", "n": -6}, CALLS) is None


def test_g2_unexecuted_head_rejected():
    why = _phrase_grounded(['[sense:weather]{city: "서울"}'], {}, CALLS)
    assert why and "실행에 없음" in why


def test_g3_welded_flow_across_statements_rejected():
    """서로 다른 문장의 액션을 `>>` 로 이으면 거짓 흐름 — 거절."""
    welded = '[sense:kosis]{query: "외환보유액"} >> [table:select]{columns: ["symbol", "current_price"]}'
    why = _phrase_grounded([welded], {}, CALLS)
    assert why and "실행에 없음" in why


def test_g4_reordered_rejected():
    stmts = _statements_of(PROGRAM)
    why = _phrase_grounded([stmts[2], stmts[0]], {}, CALLS)
    assert why and "순서 어긋남" in why


def test_g5_prose_rejected_binding_grounded():
    calls = ['$기준 = "직전 호까지 이미 다룬 사건 목록"\n[sense:search]{query: "AI"} >> [table:take]{n: 3}']
    assert _phrase_grounded(['이 브리핑을 전달받고 수신 확인한 단계들을 말해줘'], {}, calls)
    assert _phrase_grounded(['$기준 = "${기준}"',
                             '[sense:search]{query: "${질의}"} >> [table:take]{n: $n}'], {}, calls) is None
    why = _phrase_grounded(['$안묶은이름 = "x"',
                            '[sense:search]{query: "${질의}"} >> [table:take]{n: $n}'], {}, calls)
    assert why and "액션 없음" in why


def test_g6_extra_param_key_rejected():
    why = _phrase_grounded(['[sense:kosis]{query: "${질의}", org_id: "101"}'], {}, CALLS)
    assert why and "실행에 없음" in why


def test_g7_statement_split_does_not_swallow_failures():
    import ast
    fn = ast.parse(inspect.getsource(_statements_of)).body[0]
    handlers = [n for n in ast.walk(fn) if isinstance(n, (ast.Try, ast.ExceptHandler))]
    assert not handlers, "조용한 폴백은 관문을 옛 결함으로 되돌린다"


if __name__ == "__main__":
    pytest.main([__file__])
