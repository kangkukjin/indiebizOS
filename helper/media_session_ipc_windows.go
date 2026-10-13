//go:build windows

package main

import (
	"io"
	"os"
)

// mediaIPCDial opens the mpv JSON IPC named pipe as a client.
func mediaIPCDial(path string) (io.ReadWriteCloser, error) {
	return os.OpenFile(path, os.O_RDWR, 0)
}
