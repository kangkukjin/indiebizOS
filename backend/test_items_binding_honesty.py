"""집합 참조·파라미터 침묵 회귀 — **몸이 아는 것을 말하게 한다** (2026-08-23, 상상훈련 31회차).

B31-1: `[…] >> [self:notify_user]{message: "$items.title"}` 가 `'list' object has no attribute
       'strip'` 로 죽었다. 글자 하나를 받는 자리에 집합 3건이 들어가 핸들러가 파이썬
       예외로 터졌고, 그 예외문이 그대로 사용자에게 나갔다. 무엇이 잘못됐는지도,
       어떻게 고치는지도 없는 문장이다.
       처방: 핸들러를 고치지 않는다(.strip() 하는 자리는 액션마다 있고 늘어난다 —
       열거 목록은 반드시 뒤처진다). 맥락을 아는 자리(바인딩)가 표식을 남기고,
       오류를 내보내는 자리(step 실패)가 그 표식을 번역한다.

F31-1: `[self:ask]{question: …}` → "prompt 가 필요합니다" 만 들리고, **자기가 준 question 이
       읽히지 않았다는 사실은 끝내 못 듣는다**(31회차 96과제 중 12건이 이 침묵으로 죽음).
       ibl_param_vocab 은 그 액션이 선언한 키를 계산할 수 있었다 — 아는 것을 안 말한 것이 결함.

실행: .venv/bin/python -m pytest backend/test_items_binding_honesty.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def test_i1_binding_leaves_a_mark():
    """바인딩은 무엇이 몇 건 들어갔는지 표식을 남긴다 — 이게 없으면 실패를 번역할 근거가 없다."""
    from workflow_binding import _bind_items_params
    prev = '{"items": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}'
    ti = {"_node": "self", "action": "notify_user", "params": {"message": "$items.title"}}
    out, err = _bind_items_params(ti, prev)
    assert err is None, err
    assert out["params"]["message"] == ["a", "b", "c"]
    assert out.get("_items_bound") == {"message": 3}, out.get("_items_bound")


def test_i2_failure_says_what_was_bound():
    """실패 오류문이 집합 바인딩 사실과 두 갈래 출구를 말한다."""
    from workflow_binding import _items_bound_note
    msg = _items_bound_note({"_items_bound": {"message": 3}},
                            "'list' object has no attribute 'strip'")
    assert "message=3건" in msg, msg
    assert "table:brief" in msg and "table:each" in msg, msg
    assert "'list' object has no attribute 'strip'" in msg, "원문을 지우면 안 된다"


def test_i3_no_binding_no_noise():
    """집합 바인딩이 없던 step 의 실패는 오염되지 않는다(오탐 회피)."""
    from workflow_binding import _items_bound_note
    assert _items_bound_note({}, "그냥 실패") == "그냥 실패"
    assert _items_bound_note({"_items_bound": {}}, "그냥 실패") == "그냥 실패"


def test_i4_engine_wires_the_note_into_the_envelope():
    """엔진이 실제로 그 번역기를 불러야 한다 — 함수만 있고 배선이 없으면 사용자는 못 본다."""
    import workflow_engine
    src = open(workflow_engine.__file__, encoding="utf-8").read()
    assert "_items_bound_note(tool_input, err_msg)" in src, \
        "step 실패 경로가 집합 바인딩 번역기를 안 부른다"


def test_i5_unknown_param_is_named_at_failure():
    """실패 순간에 '네가 준 이 키는 안 읽혔다' 를 말한다 — F31-1 의 심장."""
    import json
    from system_tools_ibl import _enrich_error_with_param_hint
    out = _enrich_error_with_param_hint(
        {"success": False, "error": "prompt(지시/질문)가 필요합니다."},
        '[self:ask]{question: "하늘색"}')
    hint = (out if isinstance(out, dict) else json.loads(out)).get("_param_hint") or ""
    assert "question" in hint, f"받은 미인식 키를 안 알려준다: {hint}"
    assert "prompt" in hint, f"받는 키 목록을 안 알려준다: {hint}"


def test_i6_declared_keys_are_not_flagged():
    """정당한 키는 신고하지 않는다 — 자주 틀리는 경고는 침묵보다 나쁘다(모듈 철칙)."""
    import json
    from system_tools_ibl import _enrich_error_with_param_hint
    out = _enrich_error_with_param_hint(
        {"success": False, "error": "아무 이유"},
        '[self:ask]{prompt: "하늘색"}')
    hint = (out if isinstance(out, dict) else json.loads(out)).get("_param_hint") or ""
    assert "선언한 키가 아니라" not in hint, f"정당한 키를 신고했다: {hint}"


def test_i7_mixed_items_ref_substitutes_and_marks():
    """G31-1 판정(2026-08-23): 문장 속 `$items.필드` 는 **치환 + 표식** — 거절도 침묵도 아니다."""
    import json
    from workflow_binding import _bind_items_params
    prev = '{"items": [{"title": "a"}, {"title": "b"}]}'
    ti = {"_node": "self", "action": "memory",
          "params": {"op": "save", "content": "스크래치 realty: $items.title 끝"}}
    out, err = _bind_items_params(ti, prev)
    assert err is None, err
    assert out["params"]["content"] == '스크래치 realty: ["a", "b"] 끝', out["params"]["content"]
    assert out.get("_list_in_text") == [{"param": "content", "ref": "$items.title", "rows": 2}], out.get("_list_in_text")
    assert "_items_bound" not in out, "문장 속 참조는 값 바인딩이 아니다 — 표식이 섞이면 번역이 거짓이 된다"


def test_i8_standalone_reference_still_binds():
    """값 전체 참조는 그대로 산다(무회귀) — 그리고 표식을 남기지 않는다(의도된 목록 전달)."""
    from workflow_binding import _bind_items_params
    prev = '{"items": [{"title": "a"}, {"title": "b"}]}'
    out, err = _bind_items_params(
        {"_node": "limbs", "action": "show_map", "params": {"markers": "$items"}}, prev)
    assert err is None, err
    assert isinstance(out["params"]["markers"], list) and len(out["params"]["markers"]) == 2
    assert "_list_in_text" not in out


def test_i9_var_in_text_marks_with_name():
    """`$변수` 도 같은 규칙 — 문장 속 목록은 JSON 치환 + 표식, 표식은 변수 **이름**으로 말한다."""
    from workflow_binding import _inject_step_results
    step = {"_node": "self", "action": "write", "_vars": {"곡": 0},
            "params": {"path": "x.txt", "content": "오늘 곡: {{_step_0_result}} 입니다"}}
    res = {0: '{"success": true, "items": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}'}
    out = _inject_step_results(step, res)
    assert out["params"]["content"].startswith("오늘 곡: [{"), out["params"]["content"]
    assert out.get("_list_in_text") == [{"param": "content", "ref": "$곡", "rows": 3}], out.get("_list_in_text")


def test_i10_sole_var_and_scalar_path_do_not_mark():
    """통짜 `$변수`(의도된 목록 전달)와 스칼라 경로(`$곡.0.title`)는 조용히 — 자주 틀리는 경고는 침묵보다 나쁘다."""
    from workflow_binding import _inject_step_results
    res = {0: '{"success": true, "items": [{"title": "a"}, {"title": "b"}]}'}
    sole = _inject_step_results({"action": "write", "params": {"content": "{{_step_0_result}}"}}, res)
    assert "_list_in_text" not in sole, sole.get("_list_in_text")
    scalar = _inject_step_results({"action": "write", "params": {"content": "첫 곡 {{_step_0_result.items.0.title}}"}}, res)
    assert scalar["params"]["content"] == "첫 곡 a"
    assert "_list_in_text" not in scalar, scalar.get("_list_in_text")


def test_i11_block_body_marks_the_same_way():
    """블록 몸의 `$변수`(실행기 치환)도 같은 표식 — 파이프와 블록이 다른 규칙이면 사용자는 모른다."""
    from ibl_executors import _subst_var_refs
    body = [{"_node": "self", "action": "notify_user",
             "params": {"message": "목록: $r 확인"}}]
    out = _subst_var_refs(body, {"r": {"items": [{"a": 1}, {"a": 2}]}})
    assert out[0]["params"]["message"].startswith("목록: [{"), out[0]["params"]["message"]
    assert out[0].get("_list_in_text") == [{"param": "message", "ref": "$r", "rows": 2}], out[0].get("_list_in_text")


def test_i12_failure_note_and_envelope_warning_speak_the_mark():
    """실패 번역기와 봉투 경고 둘 다 표식을 사람 말로 — 사실 + 두 갈래 출구 + 무시 허가."""
    from workflow_binding import _items_bound_note, _list_in_text_warning
    msg = _items_bound_note({"_list_in_text": [{"param": "message", "ref": "$items.title", "rows": 3}]},
                            "'list' object has no attribute 'strip'")
    assert "message←$items.title 3행" in msg and "table:brief" in msg and "table:each" in msg, msg
    w = _list_in_text_warning([{"step": 3, "action": "self:write",
                                "refs": [{"param": "content", "ref": "$곡", "rows": 3}]}])
    assert "[목록→글자]" in w and "step 3[self:write]" in w and "content←$곡 3행" in w, w
    assert "무시" in w, "정당한 용법(AI 에 데이터 먹이기)을 틀렸다고 읽게 하면 안 된다"


def test_i13_engine_wires_the_mark_into_the_envelope():
    """배선 가드 — 표식을 올리는 자리(step 기록)와 번역하는 자리(봉투 경고)가 엔진에 실재해야 한다."""
    import workflow_engine
    src = open(workflow_engine.__file__, encoding="utf-8").read()
    assert '_seq["list_in_text"].append(' in src, "step 기록이 표식을 안 모은다"
    assert "_list_in_text_warning(_seq[\"list_in_text\"])" in src, "봉투 경고가 표식을 안 번역한다"


def test_i14_caller_params_list_embed_is_reported():
    """호출자 params(저장 워크플로우 run) 의 목록 임베드도 같은 사실·같은 신고 — 세 번째 치환 자리."""
    from workflow_contract import _apply_caller_params
    steps = [{"_node": "self", "action": "write", "params": {"content": "목록: $L 끝"}}]
    _, meta = _apply_caller_params(steps, {"L": [1, 2, 3]})
    assert "목록" in (meta.get("params_warning") or "") and "table:brief" in meta["params_warning"], meta


def test_i15_parser_keeps_the_variable_name_for_the_mark():
    """파서가 `$곡` 을 {{_step_N_result}} 로 바꾸며 이름을 지우면 경고는 `$step2` 라고 말한다(실측) —
    `_ref_vars` 로 이름을 남겨 표식이 사용자의 낱말로 말하게 한다."""
    from ibl_parser import parse_with_vars
    from workflow_binding import _inject_step_results
    steps, variables = parse_with_vars(
        '$곡 = [self:music]{op: "library", q: "김광석"} >> [table:take]{n: 2}\n'
        '[self:write]{path: "x.txt", content: "오늘 곡: $곡 끝"}')
    last = steps[-1]
    assert last.get("_ref_vars") == {"곡": variables["곡"]}, last.get("_ref_vars")
    assert "_vars" not in last, "일반 step 에 블록 키를 섞으면 엔진이 블록 규약(_var_values)을 발동한다"
    res = {variables["곡"]: '{"items": [{"title": "a"}, {"title": "b"}]}'}
    out = _inject_step_results(last, res)
    assert out["_list_in_text"][0]["ref"] == "$곡", out["_list_in_text"]


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
