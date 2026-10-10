//go:build !windows

package main

import (
	"os"
	"os/exec"
	"syscall"
)

func configureResidentDetached(c *exec.Cmd) { c.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }
func configureResidentProcess(c *exec.Cmd)  { configureMemberProcess(c) }
func residentDeleteSelf(path string) error  { return os.Remove(path) }
