r"""IBL `$변수` 괄호 표기 `${이름}` 회귀 테스트 (2026-08-22)

왜 있는가 — 이름 경계가 `\w` 라서 한국어에서는 조사·단위가 이름에 먹힌다.
`"$n건"` 은 변수 `n` 뒤의 글자 `건` 이 아니라 **변수 `n건`** 이다(파서·주입기·시그니처
3자 일관). 영어는 공백이 경계를 대신 그어 주지만 한국어는 아니라서, 괄호가 경계를
사람이 직접 긋는 유일한 수단이 된다. 두 표기는 같은 뜻이다.

표기의 단일 진실 = `common/ibl_vars.py`. 이 배터리는 그 규약이 **모든 층**에서 같은지를
본다 — 예전엔 층마다 `\w+` 와 `[^\W\d]\w*` 로 방언이 갈려 있었다.

    B1. 표기 모듈 자체 — 발견·치환·통짜 판정
    B2. ★경계: `$n건`=변수 n건 / `${n}건`=변수 n + 글자 건
    B3. 파서 — 괄호형 할당·참조·경로
    B4. 시그니처 — 괄호형 자유 변수 발견, 숫자 이름($100)은 인자로 안 셈
    B5. 호출자 params 주입 — 괄호형 + 통짜 참조 타입 보존
    B6. [table:each] 행 참조 — 괄호형 치환·유령 변수 판정
    B7. 블록 — 식 할당·if 조건의 괄호형 바인딩 (실행까지)
    B8. $items 집합 바인딩 예약어의 괄호형
    B9. 표기 혼용·공백 관용

실행: python3 backend/test_ibl_var_notation.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import workflow_engine  # noqa: E402
from common.ibl_vars import (find_names, sub_ref, is_sole_ref, split_ref, REF_RE)  # noqa: E402
from ibl_parser import parse  # noqa: E402
from workflow_engine import execute_pipeline, execute_workflow_action  # noqa: E402
from workflow_contract import _free_vars, _apply_caller_params  # noqa: E402


def test_b1_notation_module():
    assert find_names("${n}건 $city ${r.file} $r.count") == ["n", "city", "r"]
    assert sub_ref("${n}건", "n", lambda p: "5") == "5건"
    assert sub_ref("$r.file", "r", lambda p: "X" + p) == "X.file"
    assert is_sole_ref("${count}", "count") and is_sole_ref("$count", "count")
    # 경로가 붙으면 통짜가 아니다 — 값을 그대로 주면 `.file` 이 조용히 사라진다
    assert not is_sole_ref("${r.file}", "r")
    assert split_ref(REF_RE.fullmatch("${r.a.b}")) == ("r", ".a.b")
    print("B1 OK — 표기 모듈(발견·치환·통짜 판정·경로 분해)")


def test_b2_korean_suffix_boundary():
    """★이 배터리의 존재 이유."""
    assert find_names("$n건") == ["n건"], "맨몸 표기의 경계가 바뀌면 옛 문장이 깨진다"
    assert find_names("${n}건") == ["n"], "괄호가 경계를 못 긋고 있다"
    assert sub_ref("$n건", "n", lambda p: "5") == "$n건", "변수 n 이 n건 을 침식"
    assert sub_ref("${n}건", "n", lambda p: "5") == "5건"
    print("B2 OK — $n건=변수 n건 / ${n}건=변수 n + 글자 건")


def test_b3_parser():
    # 괄호형 할당 + 참조
    steps = parse('${r} = [sense:time]{}\n[self:notify_user]{message: "${r}"}')
    assert steps[0].get("_assign_name") == "r", steps[0]
    assert steps[1]["params"]["message"] == "{{_step_0_result}}", steps[1]

    # 괄호형 경로
    steps = parse('$r = [sense:time]{}\n[limbs:os_open]{path: "${r.file}"}')
    assert steps[1]["params"]["path"] == "{{_step_0_result.file}}", steps[1]

    # 미할당 괄호형은 리터럴로 남는다 — 그 자리가 인자 자리다
    steps = parse('[table:take]{n: "${count}건"}')
    assert steps[0]["params"]["n"] == "${count}건", steps[0]
    print("B3 OK — 파서 괄호형 할당·참조·경로, 미할당은 리터럴")


def test_b4_signature():
    assert _free_vars(parse('[table:take]{n: "${count}건"}')) == ["count"]
    assert _free_vars(parse('[table:take]{n: "$count건"}')) == ["count건"]
    # 숫자로 시작하는 이름은 인자로 세지 않는다 — 가격·금액 리터럴 오탐 방지
    assert _free_vars(parse('[self:notify_user]{message: "$100 짜리"}')) == []
    # `$file:N` 은 파서의 파일 참조 플레이스홀더 — 인자가 아니다
    assert _free_vars(parse('[self:write]{path: "a.py", content: $file:0}')) == []
    print("B4 OK — 시그니처가 괄호형을 인자로 인식 / $100 은 인자 아님")


def test_b5_caller_injection():
    steps = parse('[table:take]{n: "${count}", note: "상한 ${count}건"}')
    steps, meta = _apply_caller_params(steps, {"count": 5})
    p = steps[0]["params"]
    assert p["n"] == 5 and isinstance(p["n"], int), f"괄호형 통짜 참조 타입 소실: {p['n']!r}"
    assert p["note"] == "상한 5건", p["note"]
    assert meta.get("params_injected") == ["count"], meta
    print("B5 OK — 괄호형 주입 + 통짜 참조 원시 타입 보존")


def test_b6_each_row_ref():
    from ibl_executors import _each_substitute, _each_foreign_vars
    out, missing = _each_substitute('[self:x]{t: "${it.t}건"}', {"t": "A"}, "it")
    assert out == '[self:x]{t: "A건"}' and not missing, (out, missing)
    # 없는 필드는 정직하게 신고
    _out2, missing2 = _each_substitute('[self:x]{t: "${it.nope}"}', {"t": "A"}, "it")
    assert missing2 == ["nope"], missing2
    # 유령 변수 판정도 괄호형을 본다
    assert _each_foreign_vars('[self:x]{t: "${ghost}"}', "it") == ["ghost"]
    assert _each_foreign_vars('[self:x]{t: "${it.t}"}', "it") == []
    print("B6 OK — each 행 참조 괄호형 치환·유령 변수 판정")


def test_b7_blocks_execute():
    r = execute_pipeline(parse('$n = 5\n$m = ${n} + 1'), ".")
    assert r.get("success") and '"value": 6' in str(r.get("final_result")), r
    r2 = execute_pipeline(parse('$n = 5\n[if: ${n} > 3]{ $hit = 1 }'), ".")
    assert r2.get("success") and '"matched_value": 5' in str(r2.get("final_result")), r2
    print("B7 OK — 식 할당·if 조건의 괄호형 바인딩(실행 검증)")


def test_b8_items_binding():
    assert workflow_engine._ITEMS_REF.match("${items}"), "괄호형 $items 미인식"
    m = workflow_engine._ITEMS_REF.match("${items.name}")
    assert m and (m.group(1) or m.group(2)) == "name", m
    m2 = workflow_engine._ITEMS_REF.match("$items.name")
    assert m2 and (m2.group(1) or m2.group(2)) == "name", m2
    print("B8 OK — $items 집합 바인딩 예약어의 괄호형")


def test_b9_mixed_and_spaces():
    # 한 문장에 두 표기 혼용
    assert _free_vars(parse('[sense:search]{query: "$city ${topic}"}')) == ["city", "topic"]
    # 괄호 안 공백 관용
    assert find_names("${ n }") == ["n"]
    assert sub_ref("${ n }건", "n", lambda p: "5") == "5건"
    # 저장 → 시그니처 → 인자 없이 거절까지 종단
    out = execute_workflow_action("workflow", {
        "op": "save", "workflow_id": "_t_brace", "name": "_t_brace",
        "do": '[table:take]{items: [{"a": 1}, {"a": 2}], n: "${count}"}',
    }, ".")
    try:
        assert out.get("params_required") == ["count"], out
        bad = execute_workflow_action("workflow", {"op": "run", "workflow_id": "_t_brace"}, ".")
        assert not bad.get("success") and bad.get("params_missing") == ["count"], bad
        good = execute_workflow_action("workflow", {
            "op": "run", "workflow_id": "_t_brace", "params": {"count": 1}}, ".")
        assert good.get("success") and good.get("count") == 1, good
    finally:
        workflow_engine.delete_workflow("_t_brace")
    print("B9 OK — 표기 혼용·공백 관용·저장→시그니처→거절/실행 종단")


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
