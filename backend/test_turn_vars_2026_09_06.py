"""턴 범위 변수 — 언어 개정 2026-09-06(사용자 판정: `$rN` 핸들·resume_vars 명시 확장 대신 변수 수명을 턴으로).

`$이름 = …` 로 할당한 변수는 같은 턴(task_id)의 다음 execute_ibl 호출에서 그대로 보인다. 모델이 앞 결과를
다시 치지 않게(ep2890 부동산 22.8K자·ep2884 수리 112K자 되받아쓰기). 기판은 resume_vars 와 같은 스필+preset.

실행: .venv/bin/python -m pytest -q backend/test_turn_vars_2026_09_06.py
"""
import json
import uuid

import pytest

from system_tools import _execute_ibl_unified
from thread_context import actor_context


def _run(code, tmp_path, task, agent="probe", **extra):
    with actor_context(agent_id=agent, task_id=task):
        return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id=agent))


@pytest.fixture
def task():
    return f"task_test_{uuid.uuid4().hex[:8]}"


def _fr(out):
    fr = out.get("final_result")
    return json.loads(fr) if isinstance(fr, str) else fr


def test_var_survives_to_next_call_in_same_turn(tmp_path, task):
    first = _run('$a = [table:take]{items: [{"x": 1}, {"x": 2}, {"x": 3}], n: 3}\n'
                 '$b = [table:take]{items: [{"y": 9}], n: 1}', tmp_path, task)
    assert first.get("success") is True, first.get("error")
    assert first["turn_vars"]["live"] == ["a", "b"] and "다시 치지" in first["turn_vars"]["note"]
    second = _run('$c = $a >> [table:take]{n: 1}', tmp_path, task)
    assert second.get("success") is True, second.get("error")
    assert second["turn_vars"]["injected"] == ["a"] and second["turn_vars"]["live"] == ["c"]
    assert _fr(second)["items"] == [{"x": 1}]
    # 세 호출에 걸친 합성 — 명시 resume 한 개로는 못 하던 자리
    third = _run('$a & $b >> [table:union]', tmp_path, task)
    assert third.get("success") is True, third.get("error")
    assert third["turn_vars"]["injected"] == ["a", "b"]
    assert len(_fr(third)["items"]) == 4


def test_single_statement_assignment_is_kept(tmp_path, task):
    one = _run('$solo = [table:take]{items: [{"k": 1}], n: 1}', tmp_path, task)
    assert one.get("success") is not False and one["turn_vars"]["live"] == ["solo"]
    nxt = _run('$solo >> [table:take]{n: 1}', tmp_path, task)
    assert nxt.get("success") is True and _fr(nxt)["items"] == [{"k": 1}]


def test_other_turn_does_not_see_it(tmp_path, task):
    _run('$a = [table:take]{items: [{"x": 1}], n: 1}', tmp_path, task)
    other = _run('$a >> [table:take]{n: 1}', tmp_path, f"{task}_other")
    assert other.get("success") is not True and "a" in json.dumps(other, ensure_ascii=False)
    assert "turn_vars" not in other


def test_no_task_id_means_no_turn_scope(tmp_path):
    out = json.loads(_execute_ibl_unified({"code": '$a = [table:take]{items: [{"x": 1}], n: 1}'},
                                          str(tmp_path), agent_id="probe_no_task"))
    assert out.get("success") is not False and "turn_vars" not in out


def test_in_program_reassignment_wins(tmp_path, task):
    _run('$a = [table:take]{items: [{"x": 1}], n: 1}', tmp_path, task)
    out = _run('$a = [table:take]{items: [{"z": 7}], n: 1}\n$a >> [table:take]{n: 1}', tmp_path, task)
    assert out.get("success") is True and _fr(out)["items"] == [{"z": 7}]
    # 다음 호출은 새 값을 본다
    nxt = _run('$a >> [table:take]{n: 1}', tmp_path, task)
    assert _fr(nxt)["items"] == [{"z": 7}]


def test_explicit_resume_vars_win_over_turn_vars(tmp_path, task):
    _run('$a = [table:take]{items: [{"turn": 1}], n: 1}', tmp_path, task)
    spill = tmp_path / "explicit.json"
    spill.write_text(json.dumps({"a": json.dumps({"items": [{"explicit": 1}]})}), encoding="utf-8")
    out = _run('$a >> [table:take]{n: 1}', tmp_path, task, resume={"vars_ref": str(spill)})
    assert out.get("success") is True and _fr(out)["items"] == [{"explicit": 1}]
    assert out.get("resumed_vars") == ["a"] and "injected" not in out.get("turn_vars", {})


def test_partial_failure_still_keeps_live_vars_for_the_turn(tmp_path, task):
    prog = ('$a = [table:take]{items: [{"x": 1}], n: 1}\n'
            '$b = [self:read]{path: "/nonexistent_dir_2026_09_06/missing.txt"}')
    out = _run(prog, tmp_path, task)
    assert out.get("success") is False and out["turn_vars"]["live"] == ["a"]
    nxt = _run('$a >> [table:take]{n: 1}', tmp_path, task)
    assert nxt.get("success") is True and _fr(nxt)["items"] == [{"x": 1}]


def test_reserved_names_are_not_injected():
    from ibl_turn_vars import referenced
    assert referenced('$items >> [table:take]{n: $i} $error $return $file:0 $real ${also}') == ["also", "real"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
