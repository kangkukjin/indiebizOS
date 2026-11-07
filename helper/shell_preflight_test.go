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
