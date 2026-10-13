"""구조화된 Go 검사 영수증: 실제 실행·완료·실패와 셸 성공을 구분한다."""
import json

import boot_paths  # noqa: F401
import pytest
from repair_test_results import invocation, summary


def report(*events):
    return "\n".join(json.dumps(dict(Package="example/repair", **event)) for event in events)


def completed(state="pass", **extra):
    return report({"Action": "start"}, {"Action": "run", "Test": "TestBehavior"},
                  {"Action": state, "Test": "TestBehavior"},
                  {"Action": "fail" if state == "fail" else "pass", **extra})


def test_go_invocation_keeps_quoted_regex_and_owns_report(tmp_path):
    spec = invocation("cd helper && go test -run 'TestInstall|TestLookup' ./...", tmp_path)
    assert spec["kind"] == "go"
    assert spec["cwd"] == str(tmp_path / "helper")
    assert spec["argv"] == ["go", "test", "-json", "-count=1", "-run",
                            "TestInstall|TestLookup", "./..."]


@pytest.mark.parametrize("command", [
    "go test ./... | tail -1", "go test ./...; echo PASS",
    "go test ./... > result.txt", "go test ./... && go build .",
    "go test ./...\necho PASS", "go test ./... || true", "echo passed",
])
def test_shell_success_never_becomes_test_receipt(tmp_path, command):
    assert invocation(command, tmp_path) is None


@pytest.mark.parametrize("flag", ["-json=false", "-json", "-c", "-o=helper", "-args", "-exec=echo"])
def test_cannot_override_go_report_or_execute_compile_only(tmp_path, flag):
    with pytest.raises(ValueError):
        invocation("go test " + flag, tmp_path)


def test_complete_go_report_with_stderr_and_subtests(tmp_path):
    spec = invocation("go test ./...", tmp_path)
    output = report({"Action": "start"}, {"Action": "run", "Test": "TestBehavior"},
                    {"Action": "run", "Test": "TestBehavior/child"},
                    {"Action": "pass", "Test": "TestBehavior/child"},
                    {"Action": "pass", "Test": "TestBehavior"}, {"Action": "pass"})
    got = summary(spec, output + "\ngo: downloading example/dependency\n", 0)
    assert got["passed"] and got["tests"] == 2 and got["failures"] == 0
    assert "example/repair::TestBehavior/child" in got["cases"]


@pytest.mark.parametrize("output,exit_code", [
    (completed("fail"), 0),  # Even a masked exit code cannot erase JSON failures.
    (completed("skip"), 0),
    (completed(), 1),
    (report({"Action": "start"}, {"Action": "pass"}), 0),  # No tests matched.
    (report({"Action": "start"}, {"Action": "fail"}), 1),  # Build failure.
    (report({"Action": "start"}, {"Action": "run", "Test": "TestBehavior"}), 0),
    (report({"Action": "start"}, {"Action": "pass", "Test": "TestBehavior"}), 0),
    (completed() + '\n{"Action":', 0),
    (completed() + '\n' + json.dumps({"Action": "start", "Package": "unfinished"}), 0),
    (completed() + '\n' + report({"Action": "run", "Test": "TestLate"},
                                 {"Action": "pass", "Test": "TestLate"}), 0),
    (json.dumps({"Action": "start", "Package": ["bad"]}), 0),
    ("ok example/repair (cached)", 0),
])
def test_go_failure_skip_empty_and_incomplete_never_pass(tmp_path, output, exit_code):
    assert not summary(invocation("go test ./...", tmp_path), output, exit_code)["passed"]


def test_go_multiple_packages_cannot_hide_build_failure(tmp_path):
    output = completed() + '\n' + report({"Action": "start"}, {"Action": "fail"}).replace(
        "example/repair", "example/broken")
    got = summary(invocation("go test ./...", tmp_path), output, 0)
    assert not got["passed"] and got["failures"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
