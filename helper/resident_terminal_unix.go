//go:build !windows

package main

import (
	"os"
	"os/exec"
	"sync"
	"syscall"

	"github.com/creack/pty"
)

type unixTerminal struct {
	*os.File
	cmd  *exec.Cmd
	once sync.Once
}

func terminalAvailable() bool { return true }
func startTerminal(dir string, cols, rows int) (terminalProcess, error) {
	shell := os.Getenv("SHELL")
	if shell == "" {
		shell = "/bin/sh"
	}
	cmd := exec.Command(shell, "-i")
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "TERM=xterm-256color")
	file, err := pty.StartWithSize(cmd, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
	if err != nil {
		return nil, err
	}
	return &unixTerminal{File: file, cmd: cmd}, nil
}
func (t *unixTerminal) Resize(cols, rows int) error {
	return pty.Setsize(t.File, &pty.Winsize{Cols: uint16(cols), Rows: uint16(rows)})
}
func (t *unixTerminal) Close() error {
	t.once.Do(func() {
		// Kill the foreground job's group as well as the interactive shell's group.
		terminalKillForeground(t.File)
		_ = syscall.Kill(-t.cmd.Process.Pid, syscall.SIGKILL)
		_ = t.File.Close()
	})
	return nil
}
func (t *unixTerminal) Wait() int { return exitCode(t.cmd.Wait()) }
