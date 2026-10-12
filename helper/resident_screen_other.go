//go:build !darwin && !windows && !linux

package main

import (
	"context"
	"fmt"
	"os/exec"
)

func screenWorkerCommand(ctx context.Context, root string) (*exec.Cmd, error) {
	return nil, fmt.Errorf("unsupported desktop OS")
}
func prepareScreen(root string) error { return fmt.Errorf("unsupported desktop OS") }
func nativeScreenWorkerMain() int     { return 1 }
