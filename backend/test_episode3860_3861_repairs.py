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
    repeat_guard.reset_all()
    assert not any(repeat_guard.advise("k", _sig([f"old{i}", f"new{i}"])) for i in range(8))


def test_same_code_same_files_still_advises():
    repeat_guard.reset_all()
    out = [repeat_guard.advise("k", _sig(["old", "new"])) for _ in range(3)]
    assert out[:2] == ["", ""] and "반복 감지" in out[2]
    assert repeat_guard.inputs_digest(None) == repeat_guard.inputs_digest([]) == ""


def test_mcp_guard_signature_carries_inputs_digest():
    """CC 경로 어댑터는 stdio 프로세스라 직접 못 부른다 — 시그니처 조립을 소스로 고정."""
    src = (Path(__file__).resolve().parent.parent / "mcp_server.py").read_text(encoding="utf-8")
    call = re.search(r"_repeat_advisory\((.*?)\)\n", src, flags=re.S).group(1)
    assert "inputs_digest(inputs)" in call




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
