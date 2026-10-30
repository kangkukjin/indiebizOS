//go:build !windows

package main

import (
	"fmt"
	"strings"
)

func residentMachineSetup(cfg *Config) error {
	return fmt.Errorf("무인 관리 서비스 설치는 현재 Windows에서 지원합니다")
}

func residentMachineActive(cfg *Config) bool { return false }
func residentMachineCLI(args []string) (bool, int) {
	return len(args) > 1 && strings.HasPrefix(args[1], "--resident-machine-"), 125
}
