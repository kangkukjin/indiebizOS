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

실행: .venv/bin/python -m pytest backend/test_items_binding_honesty.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401










def test_i5_unknown_param_is_named_at_failure():
    from ibl_v2_entry import handle_request
    out=handle_request({'code':'[self:ask]{question:"하늘색"}','edition':2,'check':True})
    assert not out['ok'] and 'question' in str(out['issues'])
    assert 'UNKNOWN_ARGUMENT' in str(out['issues'])



def test_i6_declared_keys_are_not_flagged():
    from ibl_v2_entry import handle_request
    out=handle_request({'code':'[self:ask]{prompt:"하늘색"}','edition':2,'check':True})
    assert out['ok'], out





















if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
