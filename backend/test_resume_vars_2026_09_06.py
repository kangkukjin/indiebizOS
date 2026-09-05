"""부분 성공 봉투 재사용 — resume_vars (2026-09-06, ep2882: 39/39 step 이 살아 있는데 전체를 다시 돌려 중복 지불).

문장 하나가 죽으면 봉투에 `resume_vars{vars_ref, vars, failed_vars}` 가 실리고, 죽은 문장만 고쳐
`execute_ibl(code=그 문장, resume={vars_ref})` 하면 산 변수가 재실행 없이 주입된다.

실행: .venv/bin/python -m pytest -q backend/test_resume_vars_2026_09_06.py
"""
import json

from system_tools import _execute_ibl_unified


def _run(code, tmp_path, **extra):
    return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe"))


# 두 번째 문장은 **런타임**에만 죽는 실패(없는 파일) — 정적 통화 검사가 실행 전에 잡는 실패(없는 열)는
# 애초에 실행되지 않아 부분 성공 봉투가 생기지 않는다(관문이 먼저다).
PROGRAM = ('$a = [table:take]{items: [{"x": 1}, {"x": 2}], n: 2}\n'
           '$b = [self:read]{path: "/nonexistent_dir_2026_09_06/missing.txt"}\n'
           '$c = [table:take]{items: [{"y": 9}], n: 1}')


def test_partial_failure_envelope_carries_live_vars(tmp_path):
    out = _run(PROGRAM, tmp_path)
    assert out.get("success") is False and out.get("statements_failed") == 1
    rv = out.get("resume_vars")
    assert rv and rv["vars"] == ["a", "c"] and rv["failed_vars"] == ["b"], out.get("resume_vars")
    assert "전체 재실행 금지" in rv["note"]
    live = json.loads(open(rv["vars_ref"], encoding="utf-8").read())
    assert set(live) == {"a", "c"} and json.loads(live["a"])["items"][0]["x"] == 1


def test_resume_only_the_dead_statement_with_injected_vars(tmp_path):
    rv = _run(PROGRAM, tmp_path)["resume_vars"]
    fixed = '$b = $a >> [table:take]{n: 1}\n$d = $c >> [table:take]{n: 1}'
    out = _run(fixed, tmp_path, resume={"vars_ref": rv["vars_ref"]})
    assert out.get("success") is True, out.get("error")
    assert out.get("resumed_vars") == ["a", "c"]
    fr = out.get("final_result")
    fr = json.loads(fr) if isinstance(fr, str) else fr
    assert fr["items"] == [{"y": 9}]


def test_pipe_head_var_from_resume_parses(tmp_path):
    """미할당 파이프 머리는 종전대로 파싱 에러 — 시딩된 이름만 산다."""
    rv = _run(PROGRAM, tmp_path)["resume_vars"]
    bad = _run('$z >> [table:take]{n: 1}', tmp_path, resume={"vars_ref": rv["vars_ref"]})
    assert bad.get("success") is not True and "z" in json.dumps(bad, ensure_ascii=False)


def test_two_resume_modes_are_exclusive(tmp_path):
    rv = _run(PROGRAM, tmp_path)["resume_vars"]
    out = _run('$b = $a >> [table:take]{n: 1}', tmp_path, resume={"vars_ref": rv["vars_ref"], "from_step": 2})
    assert "한 가지만" in out.get("error", "")


def test_missing_spill_is_honest(tmp_path):
    out = _run('$b = $a >> [table:take]{n: 1}', tmp_path, resume={"vars_ref": str(tmp_path / "nope.json")})
    assert "resume 실패" in out.get("error", "")


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
