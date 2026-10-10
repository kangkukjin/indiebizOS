package main

import (
	"encoding/base64"
	"encoding/binary"
	"os/exec"
	"strings"
	"syscall"
	"unicode/utf16"
)

func configureResidentDetached(c *exec.Cmd) {
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
}
func configureResidentProcess(c *exec.Cmd) { configureMemberProcess(c); configureResidentDetached(c) }
func residentDeleteSelf(path string) error {
	script := "Start-Sleep -Seconds 2; Remove-Item -LiteralPath '" + strings.ReplaceAll(path, "'", "''") + "' -Force"
	units := utf16.Encode([]rune(script))
	b := make([]byte, len(units)*2)
	for i, u := range units {
		binary.LittleEndian.PutUint16(b[i*2:], u)
	}
	c := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.StdEncoding.EncodeToString(b))
	configureResidentDetached(c)
	return c.Start()
}
