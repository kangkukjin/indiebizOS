"""네이티브 셸의 실패 영수증과 감독/권한 경계를 실제 프로세스로 확인한다."""
import io
import json
import shlex
import shutil
import subprocess
import sys

import boot_paths  # noqa: F401
import pytest
import supervision_hook as hook
from test_conscious_supervisor import supervisor  # noqa: F401


def updated(command, **params):
    result = hook.shell_input({"tool_name": "Bash", "tool_input": {"command": command, **params}})
    output = result["hookSpecificOutput"]
    assert "permissionDecision" not in output
    assert output["hookEventName"] == "PreToolUse"
    assert output["updatedInput"] == {"command": "set -o pipefail\n" + command, **params}
    return output["updatedInput"]["command"]


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_failed_producer_survives_tail_without_reexecution(tmp_path, shell):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} unavailable")
    counter = tmp_path / "calls"
    script = "from pathlib import Path; Path(%r).open('a').write('once\\n'); import missing_episode5122_module" % str(counter)
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)} 2>&1 | tail -2"
    result = subprocess.run([executable, "-c", updated(command, timeout=5000, description="확인")],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "ModuleNotFoundError" in result.stdout
    assert counter.read_text() == "once\n"


@pytest.mark.parametrize("command,code,stdout", [
    ("printf 'ok\\n' | tail -1", 0, "ok\n"),
    ("(exit 7) | cat", 7, ""),
    ("(exit 7) | (exit 9)", 9, ""),
    ("(exit 7) | cat || printf recovered", 0, "recovered"),
    ("printf x | grep absent || true", 0, ""),
    ("false; printf next", 0, "next"),
    ("printf 'Traceback: ordinary text\\n'", 0, "Traceback: ordinary text\n"),
    ("cat <<'TEXT' | tail -1\n$(false) | literal\nTEXT", 0, "$(false) | literal\n"),
])
def test_shell_keeps_output_exit_codes_and_explicit_recovery(command, code, stdout):
    result = subprocess.run(["bash", "-c", updated(command)], capture_output=True, text=True, timeout=10)
    assert result.returncode == code and result.stdout == stdout


def test_other_tools_and_already_prepared_input_unchanged():
    assert hook.shell_input({"tool_name": "Read", "tool_input": {"file_path": "/tmp/a"}}) is None
    assert hook.shell_input({"tool_name": "Bash", "tool_input": {"command": ""}}) is None
    assert hook.shell_input({"tool_name": "Bash", "tool_input": {"command": updated("false | cat")}}) is None


def test_failed_pipeline_receipt_reaches_supervisor_cost(supervisor):
    from providers.claude_code import ClaudeCodeProvider
    command = updated("(exit 7) | tail -1")
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=10)
    provider = ClaudeCodeProvider(api_key="", model="test", system_prompt="test")
    supervisor.observe_native({"type": "tool_start", "id": "pipe", "name": "Bash",
                               "input": {"command": command}})
    # CLI의 nonzero→is_error 영수증을 그대로 받아 원장/집계까지 전달한다.
    events = provider._translate_stream_event({"type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": "pipe", "content": result.stdout,
        "is_error": result.returncode != 0}]}}, "", 0)
    for event, _ in events:
        supervisor.observe_native(event)
    summary = supervisor.store.cost_summary(1)
    assert summary["execution_calls"] == summary["execution_failures"] == 1


def test_hook_protocol_passes_full_input_without_granting_permission(monkeypatch, capsys):
    monkeypatch.setattr(hook, "check", lambda: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "tool_name": "Bash", "tool_input": {"command": "false | tail -1", "run_in_background": True}})))
    assert hook.main() == 0
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["updatedInput"]["run_in_background"] is True
    assert output["updatedInput"]["command"] == "set -o pipefail\nfalse | tail -1"
    assert "permissionDecision" not in output


@pytest.mark.parametrize("instruction", ["감독 턴이 종료됐습니다.", RuntimeError("unavailable")])
def test_supervisor_stop_precedes_input_rewrite(monkeypatch, capsys, instruction):
    def check():
        if isinstance(instruction, Exception):
            raise instruction
        return instruction
    monkeypatch.setattr(hook, "check", check)
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid input must not be read"))
    assert hook.main() == 2
    result = capsys.readouterr()
    assert result.out == "" and result.err


@pytest.mark.parametrize("payload", ["broken json", "[]", '{"tool_name":"Bash","tool_input":{}}'])
def test_invalid_input_stops_before_unprotected_execution(monkeypatch, capsys, payload):
    monkeypatch.setattr(hook, "check", lambda: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert hook.main() == 2
    assert capsys.readouterr().out == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
