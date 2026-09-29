"""78·79회차 잔여: 평문 실패 판정 한 벌 — 머리 장식(인자 경고)이 실패를 성공으로 바꾸지 않는다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ibl"))

from common.currency import decorate_param_warning, is_plain_failure, plain_body  # noqa: E402
from ibl_engine import _attach_param_warning  # noqa: E402
from ibl_envelope import classify_currency  # noqa: E402
from workflow_verdict import is_error_result  # noqa: E402


def test_decorated_plain_failure_stays_failure_in_every_reader():
    raw = "오류: 파일이 없습니다"
    decorated = _attach_param_warning(raw, {"message": "미인식 파라미터 ['x']"})
    assert decorated.startswith("[param_warning]")
    assert plain_body(decorated) == raw
    assert is_error_result(decorated)
    assert classify_currency(decorated)[0] == "error"


def test_plain_failure_prefixes_are_one_rule():
    for text in ("Error: boom", "  오류: 실패"):
        assert is_error_result(text)
        assert classify_currency(text)[0] == "error"
    assert not is_error_result("정상 본문")
    assert classify_currency("정상 본문")[0] == "text"
    assert not is_plain_failure(decorate_param_warning("정상 본문", "경고"))


def test_v2_adapter_reads_decorated_legacy_failure_as_tool_fault():
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    decorated = decorate_param_warning("Error: nope", "경고")
    try:
        decode_envelope(decorated, {"protocol": "legacy-envelope"})
    except Fault as exc:
        assert exc.code == "TOOL"
    else:
        raise AssertionError("장식된 평문 실패가 성공/모양 오류로 샜다")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
