"""언어 개정 2026-09-01 (사용자 판정) — `$변수 & $변수` 병렬 분기

배경: 09-01 새벽 부동산 보고서(ep2532)가 두 팬아웃 결과를 합치려고 쓴 문장

    $apt재고 = [table:each]{…} >> [table:groupby]{…}
    $house재고 = [table:each]{…} >> [table:groupby]{…}
    $apt재고 & $house재고 >> [table:join]{on: "구"}

이 "병렬 요소 파싱 실패: $apt재고" 로 죽었다 — 그날 세 주행(ep2531·2532·2533)의
**유일한 진짜 문법 오류**였다. 변수를 파이프 머리로 놓는 길은 2026-08-27 에 이미
열려 있었으므로, 결함은 능력이 아니라 **자리의 비대칭**이었다.

  P1. `$a & $b >> [변환자]` 파싱 — 두 분기가 _var_emit, 변수표는 병렬 step 이 대표로
  P2. 실행 — 두 변수의 저장 통화가 실제로 흘러 이항 변환자가 소비한다
  P3. 변수와 액션을 섞은 분기
  P4. 미할당 변수 = 파싱 시점 정직 에러 (머리 자리와 같은 판정)
  P5. 안 탄 분기의 변수(미기록) = 그 분기만 실패 + branches_failed 신고
  P6. 표기 규약이 머리 자리와 **한 벌**이다 (단일 주인 _var_emit_step)
  P7. 폴백(??) 자리는 미개방 — 경계를 이름 불러 거절한다(맨 파싱 실패 금지)

실행: .venv/bin/python -m pytest backend/test_language_revision_var_parallel.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from ibl_parser import parse, IBLSyntaxError  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 두 결과를 만들고 합치는 최소 프로그램 — 실행이 가벼운 읽기 액션으로만 짓는다.
_TWO = ('$a = [self:script]{op: "list"} >> [table:take]{n: 2}\n'
        '$b = [self:script]{op: "list"} >> [table:take]{n: 2}\n')


def _run(code):
    from workflow_engine import execute_pipeline
    return execute_pipeline(parse(code), _REPO)


def _final(res):
    fr = res.get("final_result")
    if isinstance(fr, str):
        try:
            return json.loads(fr)
        except ValueError:
            return fr
    return fr


def test_P1_변수_병렬_파싱():
    steps = parse(_TWO + '$a & $b >> [table:union]')
    par = [s for s in steps if isinstance(s, dict) and s.get("_parallel")]
    assert len(par) == 1, steps
    br = par[0]["branches"]
    assert [b.get("_var_emit") for b in br] == [True, True], br
    assert [b.get("name") for b in br] == ["a", "b"]
    # 값 주입은 step 단위로 돌므로 변수표는 **병렬 step 이 대표로** 들고 있어야 한다.
    # 인덱스는 각 변수가 가리키는 **마지막 step**(할당 파이프의 끝)이다.
    assert par[0].get("_vars") == {"a": 1, "b": 3}, par[0].get("_vars")


def test_P2_두_변수의_통화가_실제로_흐른다():
    """파싱만 되고 값이 안 흐르면 '되는 척'이다 — 이항 변환자가 소비하는지까지 본다."""
    res = _run(_TWO + '$a & $b >> [table:join]{on: "title"}')
    assert res.get("success") is True, res.get("error")
    fr = _final(res)
    assert isinstance(fr, dict) and fr.get("count") == 2, fr
    # 두 분기가 같은 두 행을 냈으므로 title 로 조인하면 두 행이 짝을 이룬다 —
    # 값이 안 흘렀다면 0행이다(파싱만 되고 '되는 척' 하는 상태의 구분자).
    assert len(fr.get("items") or []) == 2, fr


def test_P3_변수와_액션을_섞는다():
    res = _run('$a = [self:script]{op: "list"} >> [table:take]{n: 1}\n'
               '$a & [self:script]{op: "list"} >> [table:union]')
    assert res.get("success") is True, res.get("error")


def test_P4_미할당은_파싱_시점_정직_에러():
    with pytest.raises(IBLSyntaxError) as e:
        parse('$a = [self:script]{op: "list"}\n$a & $없는것 >> [table:union]')
    assert "$없는것" in str(e.value) and "할당" in str(e.value)


def test_P5_안_탄_분기의_변수는_그_분기만_실패한다():
    """V49-1 규약 — 빈 값으로 접지 않는다. 그리고 부분 실패는 봉투가 말한다."""
    res = _run('$a = [self:script]{op: "list"} >> [table:take]{n: 1}\n'
               '[if: 1 > 2]{$k = [self:script]{op: "list"}}\n'
               '$k & $a >> [table:union]')
    assert res.get("branches_failed"), "부분 실패가 봉투에 없다(침묵 금지)"
    failed = res["branches_failed"][0]["failed"][0]
    assert "$k" in failed["error"] and "기록" in failed["error"], failed
    assert res.get("warning"), "부분 실패인데 warning 이 없다"


def test_P6_표기_규약이_머리_자리와_한_벌이다():
    """단일 주인(_var_emit_step) — 한 자리에서만 되는 표기가 생기면 방언이다."""
    import ibl_parser
    src = open(os.path.join(_REPO, "backend", "ibl", "ibl_parser.py"), encoding="utf-8").read()
    assert src.count("_var_emit_step(") >= 3, "머리·분기가 같은 주인을 안 쓴다"
    assert '"_var_emit": True' not in src.split("def _var_emit_step")[0], \
        "_var_emit step 을 주인 밖에서 또 짓고 있다"
    # 같은 표기가 두 자리에서 같은 판정을 받는다 (통과/거절이 갈리지 않는다)
    for expr, ok in (("$a", True), ("$a.items", True), ("$items", False), ("$a?", False)):
        head = _TWO + f'{expr} >> [table:take]{{n: 1}}'
        branch = _TWO + f'{expr} & $b >> [table:union]'
        got = []
        for code in (head, branch):
            try:
                parse(code)
                got.append(True)
            except IBLSyntaxError:
                got.append(False)
        assert got[0] == got[1] == ok, f"{expr}: 머리={got[0]} 분기={got[1]} (기대 {ok})"
    assert ibl_parser  # 임포트 사용 표시


def test_P7_폴백_자리는_경계를_이름_불러_거절한다():
    """열지 않은 자리도 **왜** 안 되는지 말한다 — 맨 '파싱 실패'는 자가교정을 못 이끈다."""
    with pytest.raises(IBLSyntaxError) as e:
        parse(_TWO + '$a ?? $b')
    msg = str(e.value)
    assert "폴백" in msg and "병렬 분기" in msg, msg


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
