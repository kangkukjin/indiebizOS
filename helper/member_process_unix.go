//go:build !windows

package main

import (
	"os/exec"
	"syscall"
	"time"
)

// 회원이 중단하면 자식 명령도 함께 종료한다. 허브 프로세스에는 연결되지 않는다.
func configureMemberProcess(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 2 * time.Second
}
