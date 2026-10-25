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
