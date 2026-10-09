package main

import (
	"os/exec"
	"runtime"
)

// 화면을 켜두거나 유휴 연결을 위해 잠자기를 막지 않는다. 작업 중 idle sleep만 막는다.
func holdAwake() func() {
	if runtime.GOOS != "darwin" {
		return func() {}
	}
	cmd := exec.Command("/usr/bin/caffeinate", "-i", "-w", deliveryPID)
	if cmd.Start() != nil {
		return func() {}
	}
	return func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }
}
