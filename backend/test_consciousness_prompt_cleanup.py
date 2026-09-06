"""의식 프롬프트 정리 (2026-09-06) — 누더기 제거의 회귀 고정물.

1) 항상 켜진 본문에는 수리 전용 조항·이력·죽은 길이 규칙이 없다.
2) 수리 교리는 repair=True 인 호출의 <repair_doctrine> 블록으로만 실린다.
3) 파서: 문자열 값 안의 ``` 가 JSON 을 조기 절단하지 않는다.
4) 구제: JSON 모양의 깨진 응답을 원문 그대로 규정으로 넘기지 않는다.
5) assumptions 가 실행자 명령에 전제 목록으로 융합된다.
"""
import boot_paths  # noqa: F401

import pytest

from runtime_utils import get_base_path
from consciousness_agent import ConsciousnessAgent

PROMPTS = get_base_path() / "data" / "common_prompts"


def _read(rel):
    return (PROMPTS / rel).read_text(encoding="utf-8")


def _agent():
    return ConsciousnessAgent.__new__(ConsciousnessAgent)


def test_main_prompt_has_no_repair_tail_or_history():
    t = _read("consciousness_prompt.md")
    for dead in ("메타 인지 가드", "시스템 수리 안전수칙", "backend_keeper_off", "지연 적용",
                 "폐지되었다", "ep1264", "ep2386", "2026-06-28", "2026-08-19", "1-2문장", "1~2문장"):
        assert dead not in t, f"본문에 남아선 안 되는 문구: {dead}"
    # 골격과 전제 칸은 있어야 한다
    for keep in ("세상의 방식", "전문가의 방법", "무게·멈춤선", "assumptions", "<repair_doctrine>"):
        assert keep in t, f"본문에 있어야 하는 문구: {keep}"
    # 중복 조항은 한 번만
    assert t.count("수단(능력)은 가두지 않는다") == 1


def test_repair_fragment_holds_the_doctrine():
    f = _read("fragments/14_consciousness_repair.md")
    for keep in ("뿌리에서 고치", "원인 사슬", "되묻기는 두 종류뿐", "apply", "리로드를 손으로 강제하지 마라"):
        assert keep in f


def test_doctrine_block_only_when_repair():
    a = _agent()
    base = a._build_input("고쳐줘", [], "", "", "sys", "", "", None)
    assert "<repair_doctrine" not in base
    rep = a._build_input("고쳐줘", [], "", "", "sys", "", "", None, repair_doctrine="교리 본문")
    assert "<repair_doctrine" in rep and "교리 본문" in rep
    assert rep.index("<repair_doctrine") < rep.index("<user_message>")   # 사용자 메시지가 마지막


def test_parse_fence_inside_string_value_does_not_truncate():
    a = _agent()
    inner = "hint 안의 코드 펜스 ```python print(1)``` 가 있어도"
    text = "```json\n{\"task_framing\": \"문제: x\", \"capability_focus\": {\"hint\": \"" + inner + "\"}}\n```"
    r = a._parse_response(text)
    assert r is not None and r["task_framing"] == "문제: x"
    assert r["capability_focus"]["hint"] == inner


def test_salvage_rejects_raw_json_but_recovers_framing():
    a = _agent()
    broken = "```json\n{\"task_framing\": \"" + "문제: 음악앱 검색 결과가 적다. " * 4 + "\", \"needs_clarification\": false,"
    r = a._salvage_framing(broken)
    assert r is not None and r.get("_salvaged")
    assert not r["task_framing"].startswith("```")
    assert r["task_framing"].startswith("문제: 음악앱")
    # framing 자체를 못 건지면 버린다
    assert a._salvage_framing("```json\n{\"foo\": \"" + "x" * 80 + "\"") is None
    # 산문은 종전대로 통째 구제
    prose = "이 문제는 " + "산문 규정 " * 20
    assert a._salvage_framing(prose)["task_framing"] == prose.strip()


def test_assumptions_fused_into_user_command():
    import prompt_builder
    co = {"task_framing": "문제: x", "assumptions": ["원장 파일이 있다", "라이브러리 X 가 설치돼 있다"]}
    cmd = prompt_builder.compile_user_command("보고서 써줘", co)
    assert "이 계획의 전제" in cmd
    assert "- 원장 파일이 있다" in cmd and "- 라이브러리 X 가 설치돼 있다" in cmd
    # 형식이 틀리면 조용히 생략
    assert "이 계획의 전제" not in prompt_builder.compile_user_command("x", {"task_framing": "y", "assumptions": 3})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
