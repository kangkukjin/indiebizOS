"""의식 에이전트 JSON 파서 관용성 테스트

2026-05-28 회귀: opus가 capability_focus 객체 마지막 키 뒤에 trailing comma를 붙여
JSON 파싱이 실패하고 consciousness_output=None이 되어 평가 루프 전체가 침묵하던 사례.

_parse_response는 엄격 파싱 실패 시 trailing comma 청소 후 재시도해야 한다.

실행: cd backend && python3 test_consciousness_json_relax.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재 (물리 이동 2026-08-05)

from consciousness_agent import ConsciousnessAgent


def _make_parser():
    # ConsciousnessAgent는 _parse_response가 self에 의존 안 함 — 인스턴스만 만들면 됨.
    # __init__은 AI provider 초기화를 시도하므로 직접 호출 안 하고 인스턴스만 골격으로 만듬.
    obj = ConsciousnessAgent.__new__(ConsciousnessAgent)
    return obj


def test_strict_json_still_works():
    """정상 JSON은 변함 없이 파싱되어야 함."""
    p = _make_parser()
    text = '{"task_framing": "정상 케이스", "needs_clarification": false}'
    result = p._parse_response(text)
    assert result is not None, "정상 JSON 파싱 실패"
    assert result["task_framing"] == "정상 케이스"
    print("✓ 엄격 JSON 정상 동작")


def test_trailing_comma_object_recovered():
    """객체 마지막 키 뒤 trailing comma도 청소 후 파싱되어야 함."""
    p = _make_parser()
    # 2026-05-28 실제 사례 재현 — capability_focus 객체 마지막 키 뒤 trailing comma
    text = '''
{
  "task_framing": "indiebizOS 홈페이지 배포",
  "capability_focus": {
    "primary_nodes": ["engines"],
    "hint": "vercel 토큰 확인 후 배포",
  },
  "self_awareness": "홈페이지 에이전트"
}
'''.strip()
    result = p._parse_response(text)
    assert result is not None, f"trailing comma 청소 후에도 파싱 실패"
    assert result["task_framing"] == "indiebizOS 홈페이지 배포"
    assert result["capability_focus"]["hint"] == "vercel 토큰 확인 후 배포"
    print("✓ 객체 trailing comma 복구")


def test_trailing_comma_array_recovered():
    """배열 마지막 요소 뒤 trailing comma도 청소되어야 함."""
    p = _make_parser()
    text = '{"task_framing": "test", "guide_files": ["a", "b", "c",]}'
    result = p._parse_response(text)
    assert result is not None, "배열 trailing comma 청소 실패"
    assert result["guide_files"] == ["a", "b", "c"]
    print("✓ 배열 trailing comma 복구")


def test_nested_trailing_comma_recovered():
    """중첩 객체에서도 작동해야 함."""
    p = _make_parser()
    text = '''
{
  "task_framing": "nested",
  "capability_focus": {
    "tools": ["read_guide", "run_command",],
    "primary_nodes": ["self",],
  },
}
'''.strip()
    result = p._parse_response(text)
    assert result is not None
    assert result["capability_focus"]["tools"] == ["read_guide", "run_command"]
    assert result["capability_focus"]["primary_nodes"] == ["self"]
    print("✓ 중첩 trailing comma 복구")


def test_genuine_broken_json_still_fails():
    """진짜로 깨진 JSON(청소로 복구 불가)은 None을 반환해야 함."""
    p = _make_parser()
    # 짝 안 맞는 중괄호
    text = '{"task_framing": "broken", "x": [1, 2, 3'
    result = p._parse_response(text)
    assert result is None, f"진짜 깨진 JSON이 None을 반환해야 함, 실제: {result}"
    print("✓ 진짜 깨진 JSON은 None 반환")


def test_codefence_with_trailing_comma():
    """```json 블록 안의 trailing comma도 작동해야 함."""
    p = _make_parser()
    text = '''```json
{
  "task_framing": "fenced",
  "guide_files": ["x",],
}
```'''
    result = p._parse_response(text)
    assert result is not None, "코드 펜스 + trailing comma 파싱 실패"
    assert result["task_framing"] == "fenced"
    print("✓ 코드 펜스 + trailing comma 복구")


def test_2026_05_28_real_case():
    """2026-05-28 로그에서 실제로 발생한 옵스 출력 부분 모사."""
    p = _make_parser()
    text = '''
{
  "task_framing": "사용자가 indiebizOS 홈페이지 배포 및 링크를 요청.",
  "needs_clarification": false,
  "clarification_question": "",
  "achievement_criteria": "",
  "history_summary": "직전 작업에서 indiebizOS 홈페이지를 가이드의 워크플로우대로 개편 완료.",
  "capability_focus": {
    "primary_nodes": ["engines", "self"],
    "highlight_actions": ["engines:web_site"],
    "tools": ["read_guide", "run_command", "ask_user_question"],
    "hint": "먼저 web_builder.md를 read_guide로 확인. 추측으로 배포 시도하지 말 것.",
  },
  "guide_files": ["web_builder.md"],
  "self_awareness": "홈페이지 디자인·제작 전문 에이전트.",
  "world_state": "오늘 2026-05-28, 사용자는 청주에 있음."
}
'''.strip()
    result = p._parse_response(text)
    assert result is not None, "2026-05-28 실제 사례 파싱 실패 — 패치 효과 없음"
    assert "task_framing" in result
    assert result["capability_focus"]["hint"].endswith("말 것.")
    print("✓ 2026-05-28 실제 회귀 사례 복구")


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
