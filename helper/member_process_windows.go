package main

import (
	"os/exec"
	"strconv"
	"time"
)

func configureMemberProcess(cmd *exec.Cmd) {
	cmd.Cancel = func() error { return exec.Command("taskkill", "/T", "/F", "/PID", strconv.Itoa(cmd.Process.Pid)).Run() }
	cmd.WaitDelay = 2 * time.Second
}
