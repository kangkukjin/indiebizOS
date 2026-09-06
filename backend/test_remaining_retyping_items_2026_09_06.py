"""남은 항목 4 (2026-09-06, 사용자 "남은 것도 순서대로 착수"): ①이름 있는 프로그램 인식(fn_recognizer) ②같은 글자를 두 자리에
(입력 그림자 출처 ④ + 수리 교리 '한 파일 한 통로') ③가리킴 귀속 로그(_pointed_count) ④IBL 밖 도구 계측([출력해부] outside).

실행: .venv/bin/python -m pytest -q backend/test_remaining_retyping_items_2026_09_06.py
"""
import json
import uuid

import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


def _run(code, tmp_path, task, **extra):
    with actor_context(agent_id="probe", task_id=task):
        raw = _execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe")
    try:
        return json.loads(raw)
    except Exception:
        return {"_text": raw}


@pytest.fixture
def task():
    return f"task_test_{uuid.uuid4().hex[:8]}"


PROG = ('$a = [table:take]{items: [{"x": 1}, {"x": 2}], n: 2}\n'
        '$b = $a >> [table:take]{n: 1}')
SAME_SHAPE = ('$m = [table:take]{items: [{"x": 9}, {"x": 8}], n: 2}\n'
              '$n = $m >> [table:take]{n: 2}')          # 슬롯 값만 다르다(리터럴·숫자·변수 이름)


def test_shape_folds_slots_only():
    from fn_recognizer import shape, statements
    assert shape(PROG) == shape(SAME_SHAPE)
    assert shape(PROG) != shape('$a = [table:take]{items: [{"x": 1}], n: 2}\n$b = $a >> [table:select]{columns: ["x"]}')
    assert len(statements(PROG)) == 2


def test_named_shape_is_announced_in_envelope(tmp_path, task, monkeypatch):
    import fn_recognizer
    monkeypatch.setattr(fn_recognizer, "_aliased_shapes", lambda: {fn_recognizer.shape(PROG): "둘줄취하기"})
    out = _run(SAME_SHAPE, tmp_path, task)
    assert out.get("success") is True
    assert out["fn_hint"]["alias"] == "둘줄취하기" and "[fn:둘줄취하기]" in out["fn_hint"]["note"]
    # 이미 이름으로 부르는 프로그램·단문에는 붙지 않는다
    assert fn_recognizer.fn_hint_for("[fn:둘줄취하기]{}") is None
    assert fn_recognizer.fn_hint_for('[table:take]{items: [{"x": 1}], n: 1}') is None


def test_repeated_unnamed_program_is_counted_from_corpus(monkeypatch):
    import fn_recognizer
    monkeypatch.setattr(fn_recognizer, "_aliased_shapes", lambda: {})
    monkeypatch.setattr(fn_recognizer, "corpus_stats", lambda code: {"seen_count": 3, "success_count": 2})
    hint = fn_recognizer.fn_hint_for(PROG)
    assert hint["seen"] == 3 and "4번째" in hint["note"] and "증류" in hint["note"]


def test_same_text_typed_twice_in_a_turn_is_flagged(tmp_path, task):
    body = "\n".join(f"{i:03d} 새 내용이라 첫 자리에서는 아무 출처와도 겹치지 않는 긴 줄이다 {i}" for i in range(80))
    first = _run('[self:write]{path: "%s", content: "$file:0"}' % (tmp_path / "a.md"), tmp_path, task, files=[body])
    assert first.get("success") is not False and "retyped" not in first
    second = _run('[self:write]{path: "%s", content: "$file:0"}' % (tmp_path / "b.md"), tmp_path, task, files=[body])
    rt = second.get("retyped")
    assert rt and rt["level"] == "warn" and "이번 턴에 이미 친 내용" in rt["sources"], second


def test_outside_tools_are_metered():
    from cognitive_trace import ibl_call_cost, run_cost_line
    calls = [{"tool_name": "Bash", "input": {"command": "x" * 500}, "success": True},
             {"tool_name": "execute_ibl", "input": {"code": "[table:take]{n: 1}"}, "success": True}]
    c = ibl_call_cost(calls)
    assert c["other_calls"] == 1 and c["other_typed_chars"] == 500 and c["calls"] == 1
    assert "IBL 밖 도구 1회 500자" in run_cost_line(calls)
    only_shell = run_cost_line([calls[0]])
    assert "IBL 밖 도구 1회" in only_shell


def test_pointed_count_and_repair_doctrine():
    from pathlib import Path
    from ibl_usage_rag import _pointed_count
    assert _pointed_count([{"pointed": 2}, {"pointed": "1"}, {"x": 1}, None]) == 3
    doc = (Path(__file__).resolve().parent.parent / "data" / "common_prompts" / "fragments" / "13_repair.md").read_text(encoding="utf-8")
    assert "한 파일 한 통로" in doc


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
