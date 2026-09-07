"""관용구는 어휘다 — 자동 증식 중단 + 두 층 (사용자 판정 2026-09-07).

"그런 관용구는 실질적으로 어휘나 마찬가지야. … 자주 쓰는 관용구가 어휘라는 것은 그 숫자를 마구
늘려서는 안된다는 거야. 그래서 지금 매 에피소드마다 관용구를 증류하는건 그만둬야겠어."

두 층: `always_on=1` = 시스템 프롬프트에 소개 = 어휘(사람이 고른다) / `always_on=0` = 등록만
(이름으로 부를 수는 있으나 소개되지 않아 보통은 쓰이지 않는다 — 앱 버튼 같은 명시 호출의 자리).
"""
import os
import re
import sys

import pytest

import boot_paths  # noqa: E402,F401

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    return open(os.path.join(_REPO, rel), encoding="utf-8").read()


def test_no_automatic_naming_path_remains():
    """이름을 주는 길이 둘이었다 — 한쪽만 끊으면 샌다(09-07 전수 감사가 확인한 부류)."""
    src = _read("backend/cognition/ibl_usage_rag.py")
    body = src[src.index("def distill_from_turn") if "def distill_from_turn" in src else 0:]
    assert "_distill_phrase(" not in body.split("from ibl_idiom import")[-1], \
        "관용구 자동 증류가 아직 불린다"
    assert "unique_fn_name(sanitize_fn_name(" not in src, \
        "낱말 경로의 자동 작명이 남아 있다 — 이름은 어휘다"


def test_reflector_no_longer_asked_for_idioms():
    """증류를 멈췄으면 반성기에게 관용구를 짓게 하는 요청도 없어야 한다(출력 토큰은 매 턴 비용)."""
    src = _read("backend/cognition/ibl_usage_rag.py")
    for key in ('"phrase_name"', '"phrase_meaning"', '"slots"'):
        assert key not in src, f"반성기 JSON 계약에 {key} 가 남아 있다"


def test_map_serves_only_the_vocabulary_tier():
    src = _read("backend/ibl/ibl_access.py")
    assert "COALESCE(always_on,0) = 1" in src, "상시 지도가 always_on 층으로 좁혀지지 않았다"


def test_map_entry_says_when_and_how():
    """지도는 뜻이 아니라 **부를 조건**을 싣는다 — 이름만으로는 이번 일과 맞는지 판정할 자리가 없다."""
    from ibl_access import _idioms_block
    text = _idioms_block(None)
    if not text:
        pytest.skip("상시 관용구 0건")
    for line in text.splitlines():
        if line.startswith("- "):
            continue
        assert not line.startswith("  ") or line.startswith(("  언제:", "  골격:")), line
    assert "  언제:" in text and "  골격:" in text


def test_skeleton_keeps_control_blocks():
    """골격은 액션만이 아니라 제어 블록도 말한다 — 기다림이 사라지면 '어떻게'가 반쪽이다."""
    from ibl_access import _skeleton
    got = _skeleton('$j = [self:script]{op: "run"}; [repeat: until $s.status == "done", max: 3]'
                    '{$s = [self:script]{op: "status"}}')
    assert "repeat" in got, got


def test_registration_requires_a_when():
    """등록 관문 — '언제' 없이는 등록되지 않는다(지도가 실을 것이 없다)."""
    sys.path.insert(0, os.path.join(_REPO, "scripts"))
    import register_idiom
    info, why = register_idiom._gates("좁혀서읽기2", "", '[self:grep]{pattern: "x"} >> [table:take]{n: 1}')
    assert info is None and "--when" in why


def test_entry_gate_reads_idiom_bodies_as_functions():
    """원장 입구 관문도 관용구를 함수 몸으로 읽는다 — 아니면 파이프 머리 슬롯이 오타로 거절된다."""
    from ibl_param_vocab import code_syntax_error
    body = '$추림 = $목록 >> [table:take]{n: 8}; $return = $추림'
    assert code_syntax_error(body) is not None                    # 최상위로는 오타
    assert code_syntax_error(body, function_body=True) is None    # 함수 몸으로는 시그니처


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
