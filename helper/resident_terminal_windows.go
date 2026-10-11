//go:build windows

package main

import (
	"github.com/UserExistsError/conpty"
	"sync"
)

type windowsTerminal struct {
	*conpty.ConPty
	once sync.Once
}

func terminalAvailable() bool { return conpty.IsConPtyAvailable() }
func startTerminal(dir string, cols, rows int) (terminalProcess, error) {
	terminal, err := conpty.Start("powershell.exe -NoLogo", conpty.ConPtyWorkDir(dir), conpty.ConPtyDimensions(cols, rows))
	if err != nil {
		return nil, err
	}
	return &windowsTerminal{ConPty: terminal}, nil
}
func (t *windowsTerminal) Close() error { t.once.Do(func() { _ = t.ConPty.Close() }); return nil }
func (t *windowsTerminal) Wait() int    { return 0 } // ClosePseudoConsole terminates attached clients.
