package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestWindowsBackgroundChildConsole(t *testing.T) {
	if os.Getenv("INDIEBIZ_CONSOLE_TEST") != "1" {
		return
	}
	handle, _, _ := syscall.NewLazyDLL("kernel32.dll").NewProc("GetConsoleWindow").Call()
	fmt.Fprint(os.Stdout, handle)
	os.Exit(0)
}

func TestWindowsBackgroundCommandHasNoConsole(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := backgroundCommandContext(ctx, os.Args[0], "-test.run=^TestWindowsBackgroundChildConsole$")
	cmd.Env = append(os.Environ(), "INDIEBIZ_CONSOLE_TEST=1")
	out, err := cmd.CombinedOutput()
	if err != nil || strings.TrimSpace(string(out)) != "0" {
		t.Fatalf("background child has a console: %q %v", out, err)
	}
}

func TestWindowsBackgroundPreservesProcessConfiguration(t *testing.T) {
	cmd := backgroundCommandContext(context.Background(), "cmd", "/D", "/S", "/C", `echo "a b"`)
	cmd.SysProcAttr.CreationFlags |= 0x00000200 // CREATE_NEW_PROCESS_GROUP
	configureMemberProcess(cmd)
	line := cmd.SysProcAttr.CmdLine
	configureBackgroundProcess(cmd)
	if !cmd.SysProcAttr.HideWindow || cmd.SysProcAttr.CreationFlags&0x08000200 != 0x08000200 || line == "" || line != cmd.SysProcAttr.CmdLine || cmd.Cancel == nil {
		t.Fatalf("lost hidden-window, quoting or cancellation configuration: %+v", cmd.SysProcAttr)
	}
}
