//go:build !windows

package main

import "os/exec"

func elevatedWindowsCommand(exe, address, token string) *exec.Cmd { return nil }
