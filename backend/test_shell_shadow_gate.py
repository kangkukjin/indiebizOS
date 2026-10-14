"""셸/네이티브와 IBL의 공존: 강제 번역 없이 의미·기존 보호를 유지한다."""
import importlib.util
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import shell_shadow_gate as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ESS = os.path.join(ROOT, "data", "packages", "installed", "tools", "system_essentials")


def _ess(name):
    spec = importlib.util.spec_from_file_location(f"{name}_shadow_test", os.path.join(_ESS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("command", [
    "grep -vE '^(HOST|PASSWORD)=' .env | grep -E '^[A-Z_]+=' > filtered.env",
    "ls source/*.txt; cat source/*.txt | sed -n '1,4p'",
    "python3 -c \"open('result.txt','w').write('ok')\"",
])
def test_legacy_hook_does_not_translate_or_reject_shell(command):
    assert G.judge_shell(command, cwd=ROOT) is None
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ROOT}
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "backend/base/shell_shadow_gate.py"), ROOT],
                          input=json.dumps(event), capture_output=True, text=True)
    assert proc.returncode == 0 and not proc.stdout and not proc.stderr


def test_native_policy_keeps_supervision_and_role_boundaries():
    from providers.claude_code import ClaudeCodeProvider as P
    inst = object.__new__(P)
    inst._binary_path, inst.model, inst.system_prompt = "claude", None, "S"
    cmd = inst._build_command(stream=True, mcp_config_path="/tmp/x.json")
    for name in ("Read", "Grep", "Glob", "Bash", "Write", "Edit"):
        assert name in cmd[cmd.index("--tools") + 1].split(",")
        assert name not in cmd[cmd.index("--disallowed-tools") + 1].split(",")
    hooks = json.loads(cmd[cmd.index("--settings") + 1])["hooks"]["PreToolUse"]
    assert len(hooks) == 1 and "supervision_hook.py" in hooks[0]["hooks"][0]["command"]
    assert "Bash" in hooks[0]["matcher"]
    assert "shell_shadow_gate" not in json.dumps(hooks)
    inst.agent_role = "consciousness"
    cmd = inst._build_command(stream=True, mcp_config_path="/tmp/x.json")
    assert cmd[cmd.index("--tools") + 1] == "Read"
    assert "Read" not in cmd[cmd.index("--disallowed-tools") + 1].split(",")
    assert "Bash" in cmd[cmd.index("--disallowed-tools") + 1].split(",")


def test_run_command_preserves_inverted_filter_pipeline(tmp_path):
    handler = _ess("handler")
    (tmp_path / ".env").write_text("HOST=local\nPASSWORD=synthetic\nKEEP=quoted value\n# comment\n", encoding="utf-8")
    context = SimpleNamespace(tool_name="run_command", project_path=str(tmp_path), agent_id="probe")
    out = handler.execute({"command": "grep -vE '^(HOST|PASSWORD)=' .env | grep -E '^[A-Z_]+=' > filtered.env"}, context)
    assert (tmp_path / "filtered.env").read_text() == "KEEP=quoted value\n", out
    # IBL 중복 관문을 없애도 위험 명령 승인과 강제 재기동 보호는 남는다.
    out = handler.execute({"command": "rm -rf /"}, context)
    assert out.startswith("__REQUIRES_APPROVAL__"), out


def test_run_command_keeps_reload_and_repair_owner(monkeypatch, tmp_path):
    handler = _ess("handler")
    context = SimpleNamespace(tool_name="run_command", project_path=str(tmp_path), agent_id="probe")
    monkeypatch.setattr(handler, "_staging_mod", lambda: SimpleNamespace(reload_forcing_violation=lambda *a: "reload denied"))
    assert json.loads(handler._execute({"command": "touch backend/api.py"}, context))["error"] == "reload denied"
    calls = []
    monkeypatch.setattr(handler, "_red_grant_active", lambda: True)
    scope = SimpleNamespace(prepare=lambda **kw: (kw["payload"], kw["project"]),
                            run_shell=lambda *a: calls.append(a[1:]) or {"success": True, "isolated": True})
    monkeypatch.setattr(handler, "_staging_mod", lambda: SimpleNamespace(reload_forcing_violation=lambda *a: None))
    monkeypatch.setattr(handler, "_load_sibling", lambda name: scope)
    out = handler._execute({"command": "grep -v x source.txt"}, context)
    assert json.loads(out)["isolated"] is True and calls == [("grep -v x source.txt", 60)]


def test_s8_truncated_marker_carries_next_step():
    from ibl_honesty import describe_promoted, TRUNCATED_NEXT_STEP
    assert TRUNCATED_NEXT_STEP in describe_promoted(["truncated"])
    assert TRUNCATED_NEXT_STEP not in describe_promoted(["passthrough_rows"])


# ---------------------------------------------------------------- S9 낱말 상위집합
def test_s9_grep_context_ignore_case_read_numbered_tail_edit_range(tmp_path):
    G2 = _ess("fs_grep")
    (tmp_path / "a.py").write_text("l1\nl2\nNEEDLE here\nl4\nl5\nneedle lower\n", encoding="utf-8")
    r = json.loads(G2.run({"pattern": "NEEDLE", "path": str(tmp_path), "context": 1}, str(tmp_path)))
    assert r["items"][0]["문맥"] == "2  l2\n3> NEEDLE here\n4  l4"
    assert "a.py-2- l2" in r["text"] and "a.py:3: NEEDLE here" in r["text"]
    r = json.loads(G2.run({"pattern": "needle", "path": str(tmp_path), "ignore_case": True, "output_mode": "count"}, str(tmp_path)))
    assert r["items"][0]["매칭 수"] == 2
    r = json.loads(G2.run({"pattern": "니들없음", "path": str(tmp_path), "ignore_case": True, "context": 2}, str(tmp_path)))
    assert r["total"] == 0
    E = _ess("fs_edit")
    assert E.replace_line_range("a\nb\nc\nd\ne\n", 2, 4, "") == {"content": "a\ne\n", "note": "줄 2~4(3줄) 삭제"}
    assert E.replace_line_range("a\nb\nc\n", 2, 2, "X\nY")["content"] == "a\nX\nY\nc\n"
    assert "error" in E.replace_line_range("a\nb\n", 1, 1, "X", old_string="zzz")
    assert "error" in E.replace_line_range("a\nb\n", 5, 5, "X")
    H = _ess("handler")
    p = tmp_path / "t.txt"
    p.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    class Ctx:
        tool_name = "read_op"; project_path = str(tmp_path); agent_id = "probe"
    out = H.execute({"path": str(p), "numbered": True, "tail": 2}, Ctx())
    assert out.startswith("[줄 4-5 / 전체 5줄") and "4\td\n5\te\n" in out
    Ctx.tool_name = "edit_file"
    out = H.execute({"path": str(p), "start_line": 2, "end_line": 3, "new_string": ""}, Ctx())
    assert "줄 2~3(2줄) 삭제" in out and p.read_text(encoding="utf-8") == "a\nd\ne\n"
    out = H.execute({"path": str(p), "new_string": "z"}, Ctx())
    assert out.startswith("Error: old_string 또는 start_line")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
