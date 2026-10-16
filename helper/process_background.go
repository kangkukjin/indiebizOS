package main

import (
	"context"
	"os/exec"
)

// backgroundCommandContext is for internal probes and command-line work, never
// for opening a requested application or displaying an OS permission prompt.
// Keep stdio, cancellation and Unix process-group ownership with the caller.
func backgroundCommandContext(ctx context.Context, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	configureBackgroundProcess(cmd)
	return cmd
}
