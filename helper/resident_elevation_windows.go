//go:build windows

package main

import "os/exec"

func elevatedWindowsCommand(exe, address, token string) *exec.Cmd {
	return residentPowerShell("$p = Start-Process -FilePath " + residentPowerShellQuote(exe) + " -ArgumentList @('--resident-elevated'," + residentPowerShellQuote(address) + "," + residentPowerShellQuote(token) + ") -Verb RunAs -PassThru -Wait; exit $p.ExitCode")
}
