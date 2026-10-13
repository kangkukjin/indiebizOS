package main

import (
	"encoding/base64"
	"encoding/binary"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"unicode/utf16"
)

func configureResidentDetached(c *exec.Cmd) {
	if c.SysProcAttr == nil {
		c.SysProcAttr = &syscall.SysProcAttr{}
	}
	c.SysProcAttr.HideWindow = true
	c.SysProcAttr.CreationFlags |= 0x08000000
}
func configureResidentProcess(c *exec.Cmd) { configureMemberProcess(c); configureResidentDetached(c) }

func residentPowerShell(script string) *exec.Cmd {
	units := utf16.Encode([]rune(script))
	b := make([]byte, len(units)*2)
	for i, u := range units {
		binary.LittleEndian.PutUint16(b[i*2:], u)
	}
	c := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.StdEncoding.EncodeToString(b))
	configureResidentDetached(c)
	return c
}
func residentPowerShellQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
func residentDeleteSelf(path string) error {
	return residentPowerShell("Start-Sleep -Seconds 2; Remove-Item -LiteralPath " + residentPowerShellQuote(path) + " -Force").Start()
}

// residentExecutablePIDs lists the processes running one executable file.
func residentExecutablePIDs(exe string) []int {
	out, _ := residentPowerShell("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq " + residentPowerShellQuote(exe) + " } | ForEach-Object { $_.ProcessId }").Output()
	var pids []int
	for _, field := range strings.Fields(string(out)) {
		if pid, e := strconv.Atoi(field); e == nil && pid != os.Getpid() {
			pids = append(pids, pid)
		}
	}
	return pids
}
func residentKillPID(pid int) {
	c := exec.Command("taskkill", "/T", "/F", "/PID", strconv.Itoa(pid))
	configureResidentDetached(c)
	_ = c.Run()
}
