"""언어 개정 2026-08-27 (사용자 판정 4건) — 변수 의미론·파이프 머리·items 개방·문자열 식

배경: 완성 보고서 프로그램 실측(docs/VOCAB_COMPOSABILITY_HANDOFF "초안 은퇴" 절)이
남긴 언어 판정 4건을 사용자가 전부 허용. 같은 병(변수 치환=JSON 문자열)을 소비자마다
되읽기로 때우던 부류(B19-2→P30→B52)의 뿌리 폐쇄 + 표현 개방 3건.

  V1. 통짜 `.path` 참조는 **원형**(list/dict/스칼라)으로 치환된다 — 문자열화하지 않는다
  V2. bare `$var`(경로 없음)는 v4 추출 계약(F17-3) 그대로 — 이 개정과 다른 사건
  V3. 문장 **속** 참조는 종전대로 문자열화 (글자 자리)
  V4. `$변수 >> [액션]` 파이프 머리 — 파서가 _var_emit 으로 탈당의
  V5. 파이프 머리 미할당 변수 = 파싱 시점 정직 에러 / `$items` 예약어는 비적용
  V6. _var_emit 실행 — 저장 결과 방출 · 미기록(안 탄 분기)은 정직 에러 (V49-1 규약)
  V7. 변환자 items 개방 — 단항 변환자 전부 tool.json 에 items(array) 선언
  V8. safe_expr 문자열 함수 — split/replace/strip/upper/lower/contains/join

실행: .venv/bin/python -m pytest backend/test_language_revision_var_semantics.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_V1_통짜_경로_참조는_원형이다():
    from ibl.workflow_binding import _sub_step_refs
    stored = {0: json.dumps({"queue": [{"a": 1}, {"a": 2}], "n": 5,
                             "meta": {"k": "v"}}, ensure_ascii=False)}
    assert _sub_step_refs("{{_step_0_result.queue}}", stored, {}, None, None) == [{"a": 1}, {"a": 2}]
    assert _sub_step_refs("{{_step_0_result.meta}}", stored, {}, None, None) == {"k": "v"}
    # 스칼라도 원형 — "5" 가 아니라 5 (int 선언 param 에 그대로 들어간다)
    assert _sub_step_refs("{{_step_0_result.n}}", stored, {}, None, None) == 5


def test_V2_bare_참조는_v4_계약_그대로():
    from ibl.workflow_binding import _sub_step_refs
    stored = {0: json.dumps({"success": True, "message": "산문 정본이다 " * 30}, ensure_ascii=False)}
    out = _sub_step_refs("{{_step_0_result}}", stored, {}, None, None)
    assert isinstance(out, str) and "산문 정본이다" in out and "success" not in out


def test_V3_문장_속_참조는_문자열화():
    from ibl.workflow_binding import _sub_step_refs
    stored = {0: json.dumps({"n": 5, "row": [1, 2]}, ensure_ascii=False)}
    out = _sub_step_refs("값은 {{_step_0_result.n}} 이고 행은 {{_step_0_result.row}} 다",
                         stored, {}, None, None)
    assert out == "값은 5 이고 행은 [1, 2] 다"


def test_V4_변수_파이프_머리_탈당의():
    from ibl.ibl_parser import parse_with_vars
    steps, _ = parse_with_vars(
        '$표 = [table:take]{items: [{a: 1}], n: 1}\n$표 >> [table:sort]{by: "a"}')
    emits = [s for s in steps if isinstance(s, dict) and s.get("_var_emit")]
    assert len(emits) == 1 and emits[0]["name"] == "표"
    assert emits[0]["_vars"] == {"표": 0}
    # `.path` 붙은 머리도 된다
    steps2, _ = parse_with_vars(
        '$표 = [table:take]{items: [{a: 1}], n: 1}\n$표.items >> [table:sort]{by: "a"}')
    e2 = [s for s in steps2 if isinstance(s, dict) and s.get("_var_emit")][0]
    assert e2["path"].lstrip(".") == "items"


def test_V5_미할당_머리는_파싱_에러_예약어는_비적용():
    from ibl.ibl_parser import parse_with_vars
    # ★파서와 같은 평면 경로로 — ibl.ibl_parser_values 로 받으면 모듈 이중 정체로
    #   예외 클래스가 다른 객체가 되어 raises 가 못 잡는다(싱글턴 이중 임포트 부류).
    from ibl_parser_values import IBLSyntaxError
    with pytest.raises(IBLSyntaxError, match="할당되지 않았습니다"):
        parse_with_vars('$유령 >> [table:sort]{by: "a"}')
    # `$items` 는 집합 바인딩 예약어 — 머리 탈당의 대상이 아니다(그 규약의 판정대로 흐름)
    try:
        steps, _ = parse_with_vars('$items >> [table:sort]{by: "a"}')
        assert not any(isinstance(s, dict) and s.get("_var_emit") for s in steps)
    except IBLSyntaxError:
        pass                                    # 예약어 경로의 정직 거절도 수용 — emit 만 아니면 된다


def test_V6_var_emit_실행_방출과_미기록():
    from ibl.ibl_engine import execute_ibl
    stored = json.dumps({"items": [{"a": 1}]}, ensure_ascii=False)
    out = execute_ibl({"_var_emit": True, "name": "표", "path": "",
                       "_var_values": {"표": stored}}, _REPO, None)
    assert out == stored, "저장 결과를 그대로 방출해야 파이프 통화 규약이 보존된다"
    # ★2026-09-03 수리: 경로 머리는 여전히 **원형 추출**(문자열화하지 않는다)이지만,
    #   추출한 것이 행 목록이면 통화 봉투를 씌워 방출한다. 교재가 약속한 것이 그것이고
    #   ("$변수.경로 >> [액션] — 그 안의 배열 필드가 **통화로 방출**된다"), 맨 list 로
    #   흘리면 dict 만 읽는 소비자 전원이 입력을 못 알아본다 — 실측: `$본.items >>
    #   [table:spreadsheet]` 가 빈 1×1 xlsx + success:true(카카오맵 335곳이 사라졌다).
    #   맨 list 는 파이프에서 이미 `&` 병렬의 "입력 여러 개"로 예약돼 있어, 감싸는 자리는
    #   공용 게이트가 아니라 뜻을 아는 이 생산자다(ibl_engine._as_currency).
    out2 = execute_ibl({"_var_emit": True, "name": "표", "path": ".items",
                        "_var_values": {"표": stored}}, _REPO, None)
    assert out2 == {"items": [{"a": 1}]}, "경로 머리는 원형 추출 + 통화 봉투"
    # 목록이 아닌 추출(스칼라·dict)은 감싸지 않는다 — 통화가 아닌 것을 통화인 척하지 않는다.
    out3 = execute_ibl({"_var_emit": True, "name": "표", "path": ".items.0.a",
                        "_var_values": {"표": stored}}, _REPO, None)
    assert out3 == 1, "스칼라 추출은 그대로"
    miss = execute_ibl({"_var_emit": True, "name": "표", "path": "", "_var_values": {}},
                       _REPO, None)
    assert miss.get("success") is False and "기록하지 않았습니다" in miss.get("error", "")


def test_V7_변환자_items_전부_선언():
    tj = json.load(open(os.path.join(
        _REPO, "data", "packages", "installed", "tools", "data-ops", "tool.json"),
        encoding="utf-8"))
    tools = {t["name"]: t for t in tj["tools"]}
    # 단항 변환자 전부 — join(이항)·structure(본문형)만 의도적 제외.
    for name in ("data_filter", "data_sort", "data_take", "data_select", "data_compute",
                 "data_rename", "data_flatten", "data_dedup", "data_since",
                 "data_groupby", "data_union", "data_merge", "render_document"):
        props = ((tools[name].get("input_schema") or {}).get("properties") or {})
        assert props.get("items", {}).get("type") == "array", f"{name} 에 items 선언이 없다"


def test_V8_문자열_식_함수():
    from common.safe_expr import compile_expr, eval_expr, FUNCS
    for fn in ("split", "replace", "strip", "upper", "lower", "contains", "join"):
        assert fn in FUNCS, f"{fn} 이 화이트리스트에 없다"
    code, _, _ = compile_expr("split(name, ' (')[0]")
    assert eval_expr(code, {"name": "세종시 (행정중심복합도시)"}) == "세종시"
    code2, _, _ = compile_expr("upper(replace(s, '-', '_'))")
    assert eval_expr(code2, {"s": "a-b"}) == "A_B"
    code3, _, _ = compile_expr("contains(t, '전세')")
    assert eval_expr(code3, {"t": "아파트 전세 5억"}) is True


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
