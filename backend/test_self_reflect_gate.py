"""자기반성 게이트 — 읽기만 한 궤적은 길어도 스킵, 실패·변경·분류 불가는 반성 (2026-09-02).

실측 근거: git 상태 확인 턴(run_command 읽기 9회, 전부 성공)이 복잡도 규칙(≥5)에 걸려
반성 5라운드(+60s·13만 토큰)를 더 돌았다. 반성의 존재 이유(실패 오해·표류·세계 변경 검증)는
읽기 궤적에 없다 — 사용자 판정으로 읽기 궤적 제외.
"""
import boot_paths  # noqa: F401
import cognitive_trace as ct


def _rc(cmd, result="ok"):
    return {"name": "run_command", "input": {"command": cmd}, "result": result, "is_error": False}


def _ibl(code, result='{"success": true, "items": [1]}'):
    return {"name": "mcp__indiebizos__execute_ibl", "input": {"code": code}, "result": result, "is_error": False}


def _fake_safety(monkeypatch, table):
    monkeypatch.setattr(ct, "_ibl_safety_map", lambda: table)


def test_shell_read_only_recognizer():
    ok = ct.shell_command_is_read_only
    assert ok("cd /x && git status")
    assert ok("git log --oneline -5 | head -3")
    assert ok("grep -rn 'foo' backend | wc -l")
    assert ok("sed -n 200,230p a.py")
    assert ok("DBF=1 ls -la")
    assert ok("sqlite3 a.db 'select count(*) from t'")
    assert not ok("git commit -m x")
    assert not ok("echo hi > out.txt")
    assert not ok("sed -i 's/a/b/' f")
    assert not ok("find . -name '*.pyc' -delete")
    assert not ok("python3 -c 'import x'")
    assert not ok("cat a | xargs rm")
    assert not ok("sqlite3 a.db 'delete from t'")
    assert not ok("")


def test_long_read_only_trajectory_skips(monkeypatch):
    _fake_safety(monkeypatch, {("self", "read"): True, ("self", "grep"): True, ("sense", "here"): True})
    calls = [_rc("cd /r && git status"), _rc("git log --oneline -3"), _rc("git diff --stat"),
             _rc("ls -la memory_"), _rc("head -30 docs/x.md"), _ibl("[self:read]{path: \"a.py\"}"),
             _ibl("[self:grep]{pattern: \"x\"} & [sense:here]{}"), _rc("grep -rn foo backend"),
             _rc("git diff backend/a.py")]
    do, why = ct.should_self_reflect(calls, min_tool_calls=5)
    assert do is False and "읽기만 한 궤적" in why


def test_write_action_reflects_even_if_short(monkeypatch):
    _fake_safety(monkeypatch, {("self", "read"): True, ("self", "write"): False})
    do, why = ct.should_self_reflect([_ibl("[self:write]{path: \"a\", content: \"b\"}")], min_tool_calls=5)
    assert do is True and "self:write" in why


def test_unregistered_action_is_conservative(monkeypatch):
    _fake_safety(monkeypatch, {})
    do, why = ct.should_self_reflect([_ibl("[limbs:whatever]{}")], min_tool_calls=5)
    assert do is True and "limbs:whatever" in why


def test_failure_signal_reflects(monkeypatch):
    _fake_safety(monkeypatch, {("self", "read"): True})
    do, why = ct.should_self_reflect([_rc("git status", result='{"success": false}')], min_tool_calls=5)
    assert do is True and "실패 신호" in why
    do, why = ct.should_self_reflect([{"name": "run_command", "input": {"command": "ls"}, "result": "", "is_error": True}])
    assert do is True and "도구 오류" in why


def test_unknown_shell_counts_toward_complexity(monkeypatch):
    _fake_safety(monkeypatch, {})
    reads = [_rc("git status")] * 4
    do, why = ct.should_self_reflect(reads + [_rc("python3 -c 'print(1)'")], min_tool_calls=5)
    assert do is True and "분류 불가" in why
    do, why = ct.should_self_reflect(reads[:2] + [_rc("python3 -c 'print(1)'")], min_tool_calls=5)
    assert do is False and "짧고 성공한 궤적" in why


def test_file_write_tool_reflects():
    do, why = ct.should_self_reflect([{"name": "Edit", "input": {}, "result": "ok", "is_error": False}])
    assert do is True and "파일 변경" in why


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
