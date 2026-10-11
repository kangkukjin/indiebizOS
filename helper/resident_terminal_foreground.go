//go:build !windows

package main

import (
	"golang.org/x/sys/unix"
	"os"
	"syscall"
)

func terminalKillForeground(file *os.File) {
	if group, err := unix.IoctlGetInt(int(file.Fd()), unix.TIOCGPGRP); err == nil && group > 0 {
		_ = syscall.Kill(-group, syscall.SIGKILL)
	}
}
