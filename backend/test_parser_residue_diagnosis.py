"""파라미터 잔여 거절의 **진단**이 원인을 맞히는가 (2026-09-03).

사용자 관측(ep2741): 실제로 깨진 문장은 키 표기였는데
    [self:edit]{path: "…", old_string": "…", new_string": "…"}
파서는 "값 문자열 안의 따옴표가 이스케이프되지 않았을 가능성이 큽니다" 라고 안내했다.
그대로 믿으면 멀쩡한 값을 이스케이프하러 가는, 고치는 사람을 엉뚱한 데로 보내는 자리다.
틀린 진단은 침묵보다 나쁘다 — 침묵은 사람을 멈춰 세우지만 오진단은 잘못 움직이게 한다.

수리: _reject_residue 가 고정 문구 대신 멈춘 지점의 토큰으로 원인을 갈라 말한다.
실행: .venv/bin/python -m pytest backend/test_parser_residue_diagnosis.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from ibl.ibl_parser_values import IBLSyntaxError, _parse_params  # noqa: E402


def _reject(text):
    with pytest.raises(IBLSyntaxError) as e:
        _parse_params(text)
    return str(e.value)


def test_P1_키_뒤_군더더기_따옴표는_키_표기_오류로_진단된다():
    """ep2741 재현 문장 — 진단이 '키'를 가리켜야 한다."""
    msg = _reject('{path: "a.md", old_string": "A", new_string": "B"}')
    assert "키 표기 오류" in msg and "old_string" in msg
    # 옛 오진단 문구가 처방으로 붙으면 안 된다(부정문으로 언급하는 것은 허용).
    assert "이스케이프되지 않았을 가능성" not in msg, "엉뚱한 데를 고치게 만드는 진단"


def test_P2_키_앞_따옴표_미닫힘도_키_표기로_진단된다():
    msg = _reject('{path: "a.md", "old_string: "X"}')
    assert "키 표기 오류" in msg and "닫히지" in msg


def test_P3_구분자_오류를_각각_구별한다():
    assert "`=` 가 아니라 `:`" in _reject('{path: "a.md", old_string = "X"}')
    assert "`:` 가 빠졌습니다" in _reject('{path: "a.md", old_string "X"}')


def test_P4_진짜_값_이스케이프_문제는_종전대로_안내한다():
    """원인 판별이 생겼다고 원래 맞던 진단을 잃으면 안 된다."""
    msg = _reject('{path: "a.md", content: "그는 "안녕" 이라 했다"}')
    assert "이스케이프되지 않았을 가능성" in msg
    assert "키 표기 오류입니다" not in msg


def test_P5_멈춘_자리는_늘_보고된다():
    """진단이 갈리든 말든 '어디까지 읽었나 / 무엇이 남았나'는 항상 사실이다."""
    for text in ('{path: "a.md", old_string": "A"}',
                 '{path: "a.md", content: "그는 "안녕" 이라 했다"}'):
        msg = _reject(text)
        assert "해석된 키: [path" in msg and "남은 조각" in msg


def test_P6_정상_문장은_그대로_통과한다():
    got = _parse_params('{path: "a.md", old_string: "X", new_string: "Y"}')
    assert got == {"path": "a.md", "old_string": "X", "new_string": "Y"}
    # JSON 스타일(양쪽 감싼 키)도 종전대로 정상이다
    assert _parse_params('{"path": "a.md", "old_string": "X"}')["old_string"] == "X"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
