"""ep3860·3861 수리 회귀: files 가 다른 호출은 다른 호출 · 이미 분리된 턴의 detach 는 멱등."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pursuit_tools
import repeat_guard
import system_tools_ibl

CODE = '[self:edit]{path:"a.tsx",old_string:$old,new_string:$new}'


def _sig(files):
    return f"{CODE}|/p|{repeat_guard.inputs_digest(files)}"


def test_same_code_different_files_is_not_a_repeat():
    with repeat_guard.execution_scope(["k"], "task") as key:
        assert not any(repeat_guard.advise(key, _sig([f"old{i}", f"new{i}"]), "same result") for i in range(8))


def test_same_code_same_files_still_observes_same_result():
    with repeat_guard.execution_scope(["k"], "task") as key:
        out = [repeat_guard.advise(key, _sig(["old", "new"]), "same result") for _ in range(3)]
    assert out[:2] == ["", ""] and "반복 관측" in out[2]
    assert repeat_guard.inputs_digest(None) == repeat_guard.inputs_digest([]) == ""


def test_explicit_inputs_have_distinct_digests():
    assert repeat_guard.inputs_digest({"a": 1}) != repeat_guard.inputs_digest({"a": 2})
    assert repeat_guard.inputs_digest({"a": 1, "b": 2}) == repeat_guard.inputs_digest({"b": 2, "a": 1})


def test_detach_on_already_detached_turn_is_idempotent(monkeypatch):
    b = SimpleNamespace(row=None, detached=True)
    monkeypatch.setattr(pursuit_tools, "resolve_session", lambda a, t: b)
    out = json.loads(pursuit_tools.execute_pursuit({"op": "detach", "why": "무관"}, "agent"))
    assert out["success"] and out["result"]["already"] is True
    # 분리된 적 없는 무연결 턴, 그리고 detach 외의 쓰기는 여전히 거절
    b.detached = False
    assert not json.loads(pursuit_tools.execute_pursuit({"op": "detach"}, "agent"))["success"]
    b.detached = True
    assert not json.loads(pursuit_tools.execute_pursuit({"op": "note", "progress": "x"}, "agent"))["success"]


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
