package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

func TestShellPreflightWholeCandidate(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX fixture")
	}
	dir := t.TempDir()
	source := "echo effect >> marker\nif true; then\n echo OK\n"
	cmd := exec.Command("/bin/sh", "-c", source)
	cmd.Dir = dir
	report := shellPreflight(context.Background(), cmd)
	if report["status"] != "invalid" || preflightRejected(report) == nil {
		t.Fatal(report)
	}
	if _, err := os.Stat(filepath.Join(dir, "marker")); !os.IsNotExist(err) {
		t.Fatal("candidate executed")
	}
	cmd = exec.Command("/bin/sh", "-c", source+"fi\n")
	cmd.Dir = dir
	if report = shellPreflight(context.Background(), cmd); report["status"] != "valid" {
		t.Fatal(report)
	}
	if _, err := os.Stat(filepath.Join(dir, "marker")); !os.IsNotExist(err) {
		t.Fatal("valid candidate evaluated by checker")
	}
}

func TestPowerShellPreflightOnActualRuntime(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("actual Windows parser required")
	}
	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", "Write-Output 'must not run'\nif ($true) {")
	report := shellPreflight(context.Background(), cmd)
	if report["status"] != "invalid" || report["executed"] != false {
		t.Fatal(report)
	}
	if report["runtime"].(map[string]interface{})["version"] == nil {
		t.Fatal(report)
	}
}

func TestCmdPreflightUnsupported(t *testing.T) {
	cmd := &exec.Cmd{Path: "cmd.exe", Args: []string{"cmd.exe", "/c", "echo must-not-run"}}
	report := shellPreflight(context.Background(), cmd)
	if report["status"] != "unsupported" || preflightRejected(report) != nil {
		t.Fatal(report)
	}
}

func TestWindowsCommandContract(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("actual Windows execution")
	}
	for kind, want := range map[string]string{"": "powershell", "powershell": "powershell", "pwsh": "pwsh", "cmd": "cmd"} {
		bin, _ := shellFor(kind, "echo test")
		if bin != want {
			t.Fatalf("%s resolved to %s", kind, bin)
		}
	}
	if bin, _ := shellFor("unknown", "echo test"); bin != "" {
		t.Fatal("unknown shell fell back")
	}
	r := residentTestRuntime(t)
	dir := t.TempDir()
	bad := "Add-Content -LiteralPath 'marker.txt' -Value 'once'\nif ($true) {\n Write-Output '한글_OK'\n"
	rejected := r.execute(context.Background(), residentTestJob(t, map[string]interface{}{"op": "shell", "cwd": dir, "cmd": bad}))
	if rejected["executed"] != false || rejected["error"] != "shell_preflight" {
		t.Fatal(rejected)
	}
	if _, err := os.Stat(filepath.Join(dir, "marker.txt")); !os.IsNotExist(err) {
		t.Fatal("first effect ran")
	}
	fixed := r.execute(context.Background(), residentTestJob(t, map[string]interface{}{"op": "shell", "cwd": dir, "cmd": bad + "}"}))
	if fixed["exit"] != 0 {
		t.Fatal(fixed)
	}
	data, err := os.ReadFile(filepath.Join(dir, "marker.txt"))
	if err != nil || string(data) != "once\r\n" {
		t.Fatalf("marker %q: %v", data, err)
	}
	legacy := r.execute(context.Background(), residentTestJob(t, map[string]interface{}{"op": "shell", "shell": "cmd", "cmd": "echo %INDIEBIZ_BATCH_TEST% & exit /b 7", "env": map[string]string{"INDIEBIZ_BATCH_TEST": "BATCH_OK"}}))
	if legacy["exit"] != 7 {
		t.Fatal(legacy)
	}
	report := legacy["diagnostics"].(map[string]interface{})
	if report["phase"] != "execution" || report["status"] != "failed" {
		t.Fatal(report)
	}
	if report["coverage"].(map[string]interface{})["syntax"] != "unsupported" {
		t.Fatal(report)
	}
	resetSession()
	defer resetSession()
	portable := doShell(Command{Cmd: "Get-Item -LiteralPath 'Z:/indiebiz-no-such-file-12345'", Cwd: dir})
	if portable["exit"] == 0 {
		t.Fatal("PowerShell error swallowed", portable)
	}
}

func TestShellExecutionFeedbackKeepsUnsupportedCoverage(t *testing.T) {
	report := shellPreflight(context.Background(), &exec.Cmd{Path: "cmd.exe", Args: []string{"cmd.exe", "/c", "missing"}})
	result := shellExecutionFeedback(report, map[string]interface{}{"exit": 9009, "executed": true, "output": "missing is not recognized"})
	diagnosis := result["diagnostics"].(map[string]interface{})
	if diagnosis["status"] != "failed" || diagnosis["phase"] != "execution" || diagnosis["exit_code"] != 9009 {
		t.Fatal(diagnosis)
	}
	if report["status"] != "unsupported" {
		t.Fatal("mutated preflight receipt")
	}
}
