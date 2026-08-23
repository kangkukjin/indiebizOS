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


def test_i7_mixed_reference_is_refused_not_stored():
    """B31-2: 문장 속 집합 참조는 치환도 경고도 없이 **글자 그대로 저장**됐다 — 이젠 거절한다."""
    from workflow_binding import _bind_items_params
    prev = '{"items": [{"title": "a"}, {"title": "b"}]}'
    ti = {"_node": "self", "action": "memory",
          "params": {"op": "save", "content": "스크래치 realty: $items.title"}}
    out, err = _bind_items_params(ti, prev)
    assert err, "문장 속 집합 참조가 조용히 통과했다 — 글자 그대로 저장된다"
    assert "content" in err and "$items" in err, err
    assert "table:each" in err, "나갈 길을 안 알려준다"


def test_i8_standalone_reference_still_binds():
    """거절이 정상 사용까지 잡으면 안 된다 — 값 전체 참조는 그대로 산다(무회귀)."""
    from workflow_binding import _bind_items_params
    prev = '{"items": [{"title": "a"}, {"title": "b"}]}'
    out, err = _bind_items_params(
        {"_node": "limbs", "action": "show_map", "params": {"markers": "$items"}}, prev)
    assert err is None, err
    assert isinstance(out["params"]["markers"], list) and len(out["params"]["markers"]) == 2


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
