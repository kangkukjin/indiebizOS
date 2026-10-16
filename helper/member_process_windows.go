package main

import (
	"context"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func configureMemberProcess(cmd *exec.Cmd) {
	configureShellCommand(cmd)
	configureBackgroundProcess(cmd)
	cmd.Cancel = func() error {
		return backgroundCommandContext(context.Background(), "taskkill", "/T", "/F", "/PID", strconv.Itoa(cmd.Process.Pid)).Run()
	}
	cmd.WaitDelay = 2 * time.Second
}

// cmd.exe parses /C with its own quoting rules, not CommandLineToArgvW.
// Keep the script verbatim inside /S's outer quotes; never EscapeArg it.
func configureShellCommand(cmd *exec.Cmd) {
	name := strings.ToLower(filepath.Base(cmd.Path))
	if (name != "cmd.exe" && name != "cmd") || len(cmd.Args) < 3 || !strings.EqualFold(cmd.Args[len(cmd.Args)-2], "/c") {
		return
	}
	prefix := make([]string, 0, len(cmd.Args)-1)
	for _, arg := range cmd.Args[:len(cmd.Args)-1] {
		prefix = append(prefix, syscall.EscapeArg(arg))
	}
	if cmd.SysProcAttr == nil {
		cmd.SysProcAttr = &syscall.SysProcAttr{}
	}
	cmd.SysProcAttr.CmdLine = strings.Join(prefix, " ") + " \"" + cmd.Args[len(cmd.Args)-1] + "\""
}
