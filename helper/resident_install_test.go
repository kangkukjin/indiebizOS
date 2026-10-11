//go:build !windows

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestPutExecutableKeepsThePreviousAndRestoresOnFailure(t *testing.T) {
	dir := t.TempDir()
	dest, src := filepath.Join(dir, "indiebiz-helper"), filepath.Join(dir, "usb-helper")
	_ = os.WriteFile(dest, []byte("old"), 0700)
	_ = os.WriteFile(src, []byte("new"), 0700)
	if e := residentPutExecutable(src, dest); e != nil {
		t.Fatal(e)
	}
	if b, _ := os.ReadFile(dest); string(b) != "new" {
		t.Fatal("not replaced", string(b))
	}
	if b, _ := os.ReadFile(dest + ".previous"); string(b) != "old" {
		t.Fatal("previous not kept", string(b))
	}
	if residentPutExecutable(filepath.Join(dir, "missing"), dest) == nil {
		t.Fatal("missing source accepted")
	}
	if b, _ := os.ReadFile(dest); string(b) != "new" {
		t.Fatal("failed replacement left the installation changed", string(b))
	}
}

// Run from a copy of this test binary, it stands in for a long-running helper.
func TestStandInProcess(t *testing.T) {
	if os.Getenv("INDIEBIZ_TEST_STAND_IN") == "1" {
		time.Sleep(time.Minute)
	}
}

// The installed helper may be any older build, so it is ended by executable path
// while a process of another executable is left alone.
func TestReplaceInstalledEndsOnlyProcessesOfThatExecutable(t *testing.T) {
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	dest, other, src := filepath.Join(dir, "indiebiz-helper"), filepath.Join(dir, "bystander"), filepath.Join(dir, "usb-helper")
	self, e := os.Executable()
	if e != nil {
		t.Fatal(e)
	}
	for _, path := range []string{dest, other} {
		if e = residentCopy(self, path); e != nil {
			t.Fatal(e)
		}
	}
	_ = os.WriteFile(src, []byte("new build"), 0700)
	start := func(path string) (*exec.Cmd, chan error) {
		c := exec.Command(path, "-test.run=^TestStandInProcess$")
		c.Env = append(os.Environ(), "INDIEBIZ_TEST_STAND_IN=1")
		if e := c.Start(); e != nil {
			t.Fatal(e)
		}
		done := make(chan error, 1)
		go func() { done <- c.Wait() }()
		return c, done
	}
	installed, installedDone := start(dest)
	bystander, bystanderDone := start(other)
	defer bystander.Process.Kill()
	defer installed.Process.Kill()
	for attempt := 0; len(residentExecutablePIDs(dest)) == 0 && attempt < 50; attempt++ {
		time.Sleep(20 * time.Millisecond)
	}
	if pids := residentExecutablePIDs(dest); len(pids) != 1 || pids[0] != installed.Process.Pid {
		t.Fatal("installed process not found by executable", pids, installed.Process.Pid)
	}
	cfg := &Config{InstallationID: "0000" + "0000000000000000000000000000", DataDir: dir}
	_ = os.WriteFile(residentUpdatePath(dir), []byte("{}"), 0600)
	if e = residentReplaceInstalled(cfg, src, dest); e != nil {
		t.Fatal(e)
	}
	select {
	case <-installedDone:
	case <-time.After(5 * time.Second):
		t.Fatal("installed helper still running")
	}
	select {
	case <-bystanderDone:
		t.Fatal("a process of another executable was ended")
	default:
	}
	if b, _ := os.ReadFile(dest); string(b) != "new build" {
		t.Fatal("not replaced")
	}
	if _, e = os.Stat(residentUpdatePath(dir)); !os.IsNotExist(e) {
		t.Fatal("pending self-update record survived a by-hand replacement")
	}
}
