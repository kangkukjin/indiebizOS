"""49회차 상상훈련 수리 회귀 — 축: **실행 상태 승계**(바인딩이 실행 경계를 건너 사는가).

격자 = 운반 기제 6종(액션할당 스칼라 · 식할당 스칼라 · 통화변수 · `$items` 집합참조 ·
`$it` 행바인딩 · spill 참조) × 경계 8종(파이프 다음 step · 다음 독립문장 · if 조건식 ·
블록 몸 · 블록 밖 · `&` 가지 · `??` 폴백 가지 · `each do` 안) = 48칸.
36~46회차가 닫은 **값 의미론**(같은 *값*이 표면마다 같은 판정을 받는가)과도,
48회차의 **정직 표지 전파**(실패 *사실*이 경계를 건너는가)와도 다른 밭이다 —
여기서 묻는 것은 "**성공한 바인딩**이 경계를 건너 살아남는가"이고, 스코프·수명은
런타임 사전의 동적 상태라 AST census 로는 셀 수 없다(가이드 §3-2 축 선정 관문 통과).

재현하는 결함(전부 실측):

  B49-1 **dry-run 이 멀쩡한 문장에 거짓 빨강을 낸다 — `$변수` × `do` 컨테이너.**
     파서는 바깥에 `$n = …` 이 있으면 `do` 문자열 속 `$n` 을 `{{_step_0_result}}` 로
     **미리** 바꿔 둔다. 그런데 `/ibl/validate` 의 `_walk_do_param` 재파싱 재시도는
     `$` 로만 훑어 그 자리표를 못 보고 지나쳤고, 재파싱기가 `{{` 를 객체 리터럴의
     시작으로 읽어 죽었다. 실측:
         $n = 2
         [table:each]{items: [{a: 1}], do: "[sense:host]{op: \"apps\", limit: $n}"}
           → validate valid:false  /  execute success:true
     조종실은 번역→**검수**→실행이라, 거짓 빨강은 곧 멀쩡한 문장의 차단이다.
     따옴표로 감싼 `\"$n\"` 은 문자열 값이 되어 통과했으므로 **인용 없는 자리 전용**.
     `_DO_CARRYING` 6종(each·schedule·trigger·workflow·manage_events·delegate)이 같은
     재파싱을 공유하므로 부류 전체가 이 한 줄에 걸려 있었다.

  B49-2 **블록 몸에서 *태어난* `$변수`가 소리 없이 사라진다.**
     `[repeat:]` 은 바깥에 **이미 있던** 이름만 되쓰고(`_var_updates` — step_results 에
     슬롯이 있어야 한다), `[if]/[case]/[try]` 는 몸의 할당을 아예 추적하지 않는다.
     그래서 `$n = 0` 을 미리 둔 *재할당*만 살아남는 비대칭이 생겼고, 떨어진 쪽은
     표지 하나 없이 사라져 **뒤 문장이 엉뚱한 곳을 탓했다**. 실측:
         [if: 1 == 1]{$k = 7}
         [if: $k == 7]{[self:time]}[else]{[sense:host]{op:"status"}}
           → "조건 평가 실패 1건 — 판정 불능이라 else 분기를 보류했습니다"
     수리는 **스코프 의미론을 바꾸지 않는다**(블록이 스코프를 만드는지는 언어 개정
     사안 → 사용자 판정 몫). 떨궜다는 *사실*에 `vars_dropped` 표지를 붙일 뿐이다 —
     48회차가 연 "정직 표지가 조합 경계를 못 건넌다" 부류의 같은 처방.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402


# ─────────────────────────── B49-1 ───────────────────────────

CODE_B49_1 = '$n = 2\n[table:each]{items: [{a: 1}], do: "[sense:host]{op: \\"apps\\", limit: $n}"}'


def _do_param_of(code: str) -> str:
    """파서를 태운 뒤 each step 의 `do` param — 자리표가 이미 박힌 *실제* 모양."""
    from ibl_parser import parse
    for st in parse(code):
        if isinstance(st, dict) and st.get("action") == "each":
            return st["params"]["do"]
    raise AssertionError(f"each step 을 못 찾음: {code}")


def test_B49_1_파서가_do_속_변수를_자리표로_바꿔_둔다():
    """결함의 전제 — 검수가 보는 do 에는 `$n` 이 없고 `{{_step_N_result}}` 가 있다."""
    do = _do_param_of(CODE_B49_1)
    assert "$n" not in do, do
    assert "_step_" in do and "_result" in do, do


def test_B49_1_옛_재시도는_이_모양을_못_푼다():
    """이빨 — 수리 전의 `$` 전용 재시도로는 여전히 파싱이 죽는다(결함 재현)."""
    import re
    from ibl_parser import parse as _parse, IBLSyntaxError
    do = _do_param_of(CODE_B49_1)
    with pytest.raises(IBLSyntaxError):
        _parse(do)                                    # 자리표 그대로 → 죽는다
    with pytest.raises(IBLSyntaxError):
        _parse(re.sub(r"\$\w+(?:\.\w+)*", "1", do))   # 옛 재시도 → 여전히 죽는다


def test_B49_1_자리표를_메우면_재파싱이_산다():
    """수리 — 자리표를 먼저 메우고 남은 맨 `$참조`를 정본 REF_RE 로 훑으면 파싱된다."""
    from workflow_binding import blank_step_refs
    from common.ibl_vars import REF_RE
    from ibl_parser import parse as _parse
    do = _do_param_of(CODE_B49_1)
    inner = _parse(REF_RE.sub("1", blank_step_refs(do)))
    assert inner and inner[0].get("action") == "host", inner


def test_B49_1_자리표_굴절은_경로형과_괄호형까지_본다():
    """방언 방지 — `.path` 붙은 자리표도, `${이름}` 괄호형 참조도 한 벌이 처리한다."""
    from workflow_binding import blank_step_refs
    from common.ibl_vars import REF_RE
    assert blank_step_refs("a {{_step_3_result.items.0.title}} b") == "a 1 b"
    assert blank_step_refs("{{_step_0_result}}", repl="X") == "X"
    assert blank_step_refs("자리표 없음") == "자리표 없음"
    assert REF_RE.sub("1", "${이름}과 $맨몸.경로") == "1과 1"


@pytest.mark.parametrize("code", [
    CODE_B49_1,
    '$n = 2\n[sense:host]{op: "apps", limit: 2} >> [table:each]{do: "[sense:host]{op: \\"apps\\", limit: $n}"}',
])
def test_B49_1_검수가_실행되는_문장을_통과시킨다(code):
    """종단 — dry-run 이 실행 가능한 문장에 valid:true 를 낸다(거짓 빨강 소멸)."""
    import asyncio
    from api_ibl import validate_ibl, ValidateRequest
    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        validate_ibl(ValidateRequest(code=code)))
    bad = [s for s in out.get("steps", []) if s.get("valid") is False]
    assert out.get("valid") is True, (out.get("syntax_error"), bad)


# ─────────────────────────── B49-2 ───────────────────────────

def test_B49_2_할당_이름은_몸의_모양과_무관하게_걷힌다():
    """파이프 list · 단일 dict · 분기 action — 세 모양 모두 `_assign_name` 한 벌로."""
    from ibl_honesty import assigned_in_body
    assert assigned_in_body({"_assign": True, "name": "k", "_assign_name": "k"}) == ["k"]
    assert assigned_in_body([{"_assign_name": "a"}, {"_assign_name": "b"}]) == ["a", "b"]
    assert assigned_in_body([{"_assign_name": "a"}, {"_assign_name": "a"}]) == ["a"]   # 중복 제거
    assert assigned_in_body({"_node": "self", "action": "time"}) == []
    assert assigned_in_body(None) == [] and assigned_in_body("평문") == []


def test_B49_2_표지는_통화를_침범하지_않는다():
    """dict 봉투에만 싣는다 — 스칼라를 감싸면 하류 통화 계약이 깨진다(F19-1 판정)."""
    from ibl_honesty import note_vars_dropped
    out = note_vars_dropped({"items": []}, [{"_assign_name": "k"}])
    assert out["vars_dropped"] == ["k"]
    assert note_vars_dropped("스칼라", [{"_assign_name": "k"}]) == "스칼라"      # 감싸지 않는다
    assert "vars_dropped" not in note_vars_dropped({}, [{"_node": "self"}])      # 할당 없으면 조용
    kept = note_vars_dropped({}, [{"_assign_name": "n"}], kept={"n"})            # 되쓴 이름은 제외
    assert "vars_dropped" not in kept


def test_B49_2_표지는_단일_소스에_등재돼_있다():
    """손으로 열거된 표지는 반드시 샌다 — HONESTY_KEYS 와 걷는 쪽이 함께 안다."""
    from ibl_honesty import HONESTY_KEYS, markers_of
    assert "vars_dropped" in HONESTY_KEYS
    assert markers_of({"vars_dropped": ["k"], "items": []}) == {"vars_dropped": ["k"]}
    assert markers_of({"vars_dropped": []}) == {}      # 빈 값은 소음


def _run(code: str):
    from ibl_parser import parse
    from ibl_engine import execute_ibl
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return execute_ibl(parse(code)[0], root, "test")


@pytest.mark.parametrize("code,name", [
    ('[if: 1 == 1]{$k = 7}', "k"),
    ('[repeat: 2, max: 3]{$r = [self:time]}', "r"),
    ('[try]{$k = 7}[catch]{[self:time]}', "k"),
])
def test_B49_2_경계가_떨군_변수를_신고한다(code, name):
    """종단 — 블록 몸에서 태어난 이름은 못 나가되, 그 사실이 봉투에 남는다."""
    out = _run(code)
    assert isinstance(out, dict), out
    assert name in (out.get("vars_dropped") or []), out


def test_B49_2_바깥에_있던_이름의_재할당은_신고_대상이_아니다():
    """대조군 — 되쓸 슬롯이 있는 이름은 정상 승계라 표지가 붙으면 소음이 된다.

    (`$n = 0` 을 미리 두고 몸에서 재할당하는 교재 M6 용법이 바로 이 경로다.)"""
    from ibl_parser import parse
    from ibl_engine import execute_ibl
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    steps = parse('$n = 0\n[repeat: 2, max: 3]{$n = $n + 1}')
    rep = [s for s in steps if isinstance(s, dict) and s.get("_repeat")][0]
    rep = {**rep, "_var_values": {"n": "0"}}
    out = execute_ibl(rep, root, "test")
    assert isinstance(out, dict), out
    assert "n" not in (out.get("vars_dropped") or []), out
    assert (out.get("_var_updates") or {}).get("n") is not None, out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
