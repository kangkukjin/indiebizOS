//go:build !windows

package main

import (
	"io"
	"net"
	"time"
)

// mediaIPCDial opens the mpv JSON IPC socket (unix domain socket).
func mediaIPCDial(path string) (io.ReadWriteCloser, error) {
	return net.DialTimeout("unix", path, time.Second)
}
