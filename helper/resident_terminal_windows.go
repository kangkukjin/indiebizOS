//go:build windows

package main

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"github.com/UserExistsError/conpty"
	"sync"
	"unicode/utf16"
)

type windowsTerminal struct {
	*conpty.ConPty
	once sync.Once
}

func terminalAvailable() bool { return conpty.IsConPtyAvailable() }
func startTerminal(dir string, cols, rows int) (terminalProcess, error) {
	return startTerminalCommand(dir, cols, rows, "")
}
func startTerminalCommand(dir string, cols, rows int, command string) (terminalProcess, error) {
	line := "powershell.exe -NoLogo"
	if command != "" {
		units := utf16.Encode([]rune(command))
		data := make([]byte, len(units)*2)
		for i, v := range units {
			binary.LittleEndian.PutUint16(data[i*2:], v)
		}
		line += " -NoProfile -EncodedCommand " + base64.StdEncoding.EncodeToString(data)
	}
	terminal, err := conpty.Start(line, conpty.ConPtyWorkDir(dir), conpty.ConPtyDimensions(cols, rows))
	if err != nil {
		return nil, err
	}
	return &windowsTerminal{ConPty: terminal}, nil
}
func (t *windowsTerminal) Close() error { t.once.Do(func() { _ = t.ConPty.Close() }); return nil }
func (t *windowsTerminal) Wait() int {
	code, err := t.ConPty.Wait(context.Background())
	if err != nil {
		return -1
	}
	return int(code)
}
