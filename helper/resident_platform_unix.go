//go:build !windows

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

func configureResidentDetached(c *exec.Cmd) { c.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }
func configureResidentProcess(c *exec.Cmd)  { configureMemberProcess(c) }
func residentDeleteSelf(path string) error  { return os.Remove(path) }

// Windows-only branches in the shared installer/update state machine.
func residentWindowsAutostart(*Config, string, bool) error { return os.ErrInvalid }
func residentWindowsCanRestart(*Config) bool               { return false }
func residentWindowsRestart(*Config) error                 { return os.ErrInvalid }

// residentExecutablePIDs lists the processes running one executable file.
func residentExecutablePIDs(exe string) []int {
	var pids []int
	if runtime.GOOS == "linux" {
		links, _ := filepath.Glob("/proc/[0-9]*/exe")
		for _, link := range links {
			if target, e := os.Readlink(link); e == nil && target == exe {
				if pid, e := strconv.Atoi(filepath.Base(filepath.Dir(link))); e == nil && pid != os.Getpid() {
					pids = append(pids, pid)
				}
			}
		}
		return pids
	}
	out, _ := exec.Command("ps", "-axo", "pid=,comm=").Output()
	for _, line := range strings.Split(string(out), "\n") {
		fields := strings.SplitN(strings.TrimSpace(line), " ", 2)
		if len(fields) == 2 && strings.TrimSpace(fields[1]) == exe {
			if pid, e := strconv.Atoi(fields[0]); e == nil && pid != os.Getpid() {
				pids = append(pids, pid)
			}
		}
	}
	return pids
}
func residentKillPID(pid int) { _ = syscall.Kill(pid, syscall.SIGKILL) }
