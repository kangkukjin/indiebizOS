"""전문가의 선택 — 실행자 명령의 제 이름 섹션 가드 (2026-09-07).

사용자 설계: "전문가라면 어떻게 할지 생각해 보라"는 산문 권고가 아니라, 실행 에이전트가
받는 글에 **전문가의 선택이라는 섹션**을 두고 한 문장을 싣는다. 종전엔 task_framing 골격
안의 한 줄이라 1,300자 규정 덩어리에 묻혔다(hint 가 별도 명령문 줄로 떼어졌을 때 살아난
것과 같은 자리다).

이 시험이 고정하는 것:
  ① 값이 있으면 당위 앵커 아래 `전문가의 선택:` 한 줄로 실린다
  ② 비었거나 문자열이 아니면 라벨 자체가 없다 (허공 라벨 금지)
  ③ 여러 줄로 와도 한 줄로 눕는다 (두 번째 task_framing 이 되지 않는다)
  ④ 재규정(reframe) 결과에도 같은 섹션이 실린다 — 한 자리에서만 살면 재규정 뒤 사라진다
  ⑤ 의식 프롬프트가 필드를 요구하고, 골격에는 중복으로 남기지 않는다
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "data" / "common_prompts" / "consciousness_prompt.md"

LABEL = "전문가의 선택:"
SENT = "감정사는 가격표가 아니라 최근 체결 거래 사례부터 본다."


@pytest.fixture(scope="module")
def compile_fn():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "backend" / "cognition"))
    from prompt_builder import compile_user_command
    return compile_user_command


def test_section_carries_sentence(compile_fn):
    out = compile_fn("이 카메라 얼마쯤 해?", {"task_framing": "문제: 중고 시세 판단.",
                                              "expert_choice": SENT})
    line = [l for l in out.split("\n") if l.startswith(LABEL)]
    assert line == [f"{LABEL} {SENT}"], out
    # 당위 앵커 아래 = 명령으로 재분류되는 자리
    assert out.index("다음 절차에 따라 수행하라") < out.index(LABEL)


@pytest.mark.parametrize("value", ["", "   ", None, 0, [SENT], {"a": 1}])
def test_no_dangling_label(compile_fn, value):
    co = {"task_framing": "문제: 오늘 날씨.", "expert_choice": value}
    assert LABEL not in compile_fn("날씨 알려줘", co)


def test_missing_key_is_silent(compile_fn):
    assert LABEL not in compile_fn("날씨 알려줘", {"task_framing": "문제: 오늘 날씨."})


def test_multiline_collapses_to_one_line(compile_fn):
    out = compile_fn("집 모델 만들어줘", {
        "task_framing": "문제: 3D 주택 형상.",
        "expert_choice": "3D 형상은 Blender 로 만들어\n  glTF 로 내보낸다 —\n브라우저 기하로 새로 짜지 않는다.",
    })
    line = [l for l in out.split("\n") if l.startswith(LABEL)][0]
    assert "Blender" in line and "glTF" in line
    assert "\n" not in line and "  " not in line


def test_reframe_directive_carries_section():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "backend" / "cognition"))
    import reframe as rf
    body = rf.render_for_executor({"revised": True, "output": {
        "task_framing": "문제: 다시 규정한 문제.",
        "expert_choice": SENT,
    }})
    assert f"{LABEL} {SENT}" in body


def test_prompt_requires_field_without_skeleton_duplicate():
    text = PROMPT.read_text(encoding="utf-8")
    assert "expert_choice" in text and "### 1e. expert_choice" in text
    # 골격(task_framing) 안에 같은 조항을 남겨두지 않는다 — 중복은 프롬프트 누더기의 서명
    assert "- **전문가의 방법**" not in text
    # 이름 강제가 살아 있어야 필드가 상투구로 채워지지 않는다
    assert "반드시 이름을 담는다" in text


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(pytest.main([__file__, "-v"]))
