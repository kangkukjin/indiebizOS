"""자기 수리 훈련의 시험 대상 (긴문장 상상훈련 97회차 씨앗, 2026-10-26).

이 파일은 **의도된 결함**을 담은 훈련 대상이다. 실제 수리 영수증 판정(`repair_policy.completion`)의
대체 구현이 아니며, 라이브 코드는 이 모듈을 import 하지 않는다.

- 요구(정본, 바꾸지 않는다): 세 관측(적용·활성·커밋) 중 하나라도 명시적 `False` 면 `failed`,
  `False` 가 없고 하나라도 `None`(미관측)이면 `unverified`, 셋 다 `True` 면 `achieved`.
- 심은 결함: `None` 을 실패로 접는다 → `test_none_is_unverified` 가 실패한다.
- 허용 수정 범위: `fold_receipt` 함수 **본문**만. 시험·활성화 조건·import 는 고정이다.
- 기본 비활성: 환경변수 `INDIEBIZ_REPAIR_TRAINING_SUBJECT=1` 일 때만 예제 시험이 돈다.
  실행: `INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 .venv/bin/python3 -m pytest backend/test_repair_training_subject.py -q`
"""
import os

import pytest


def fold_receipt(applied, activated, committed):
    """세 관측을 achieved / failed / unverified 로 접는다."""
    observations = (applied, activated, committed)
    if any(value is False for value in observations):
        return "failed"
    if any(value is None for value in observations):
        return "unverified"
    return "achieved"


ENABLED = os.environ.get("INDIEBIZ_REPAIR_TRAINING_SUBJECT") == "1"
pytestmark = pytest.mark.skipif(
    not ENABLED, reason="수리 훈련 시험 대상 — INDIEBIZ_REPAIR_TRAINING_SUBJECT=1 로 켠다")


def test_all_true_is_achieved():
    assert fold_receipt(True, True, True) == "achieved"


def test_explicit_false_is_failed():
    assert fold_receipt(True, False, True) == "failed"


def test_none_is_unverified():
    assert fold_receipt(True, None, True) == "unverified"


def test_false_beats_none():
    assert fold_receipt(None, False, None) == "failed"


if __name__ == "__main__":
    pytest.main([__file__])
