//go:build !windows

package main

import (
	"fmt"
	"os"
	"syscall"
)

func memberFileIdentity(file *os.File) (string, error) {
	var stat syscall.Stat_t
	if e := syscall.Fstat(int(file.Fd()), &stat); e != nil {
		return "", e
	}
	return fmt.Sprintf("%d:%d", stat.Dev, stat.Ino), nil
}
