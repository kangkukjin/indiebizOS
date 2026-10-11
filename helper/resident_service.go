package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// A resident helper must be restarted by something that outlives it. That is the
// OS service manager (launchd / systemd user), never a script the helper started:
// on 2026-10-11 a swap script failed to start either binary and the PC stayed
// offline until someone logged in again. The autostart entry therefore restarts
// on abnormal exit, and a helper that was started outside the service manager
// (installer, swap script) hands itself over at startup.

const residentServiceEnv = "INDIEBIZ_SERVICE"

func residentServiceName(cfg *Config) string { return "indiebiz-resident-" + cfg.InstallationID }

func residentLaunchAgentBody(name, id, exe string) string {
	return `<?xml version="1.0"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>` + name +
		`</string><key>ProgramArguments</key><array><string>` + xmlText(exe) +
		`</string></array><key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict><key>EnvironmentVariables</key><dict><key>` + residentServiceEnv + `</key><string>` + xmlText(id) +
		`</string></dict><key>ProcessType</key><string>Background</string></dict></plist>`
}

func residentSystemdUnitBody(id, exe string) string {
	return "[Unit]\nDescription=IndieBiz registered PC\n[Service]\nExecStart=" + strconv.Quote(exe) +
		"\nRestart=on-failure\nRestartSec=10\nEnvironment=" + residentServiceEnv + "=" + id + "\n[Install]\nWantedBy=default.target\n"
}

// residentWriteIfChanged reports whether the file was (re)written.
func residentWriteIfChanged(path string, body []byte) (bool, error) {
	if old, e := os.ReadFile(path); e == nil && bytes.Equal(old, body) {
		return false, nil
	}
	return true, os.WriteFile(path, body, 0600)
}

// residentServiceStarted is true for a process the new autostart entry launched
// (or a child that inherited its environment — also not a hand-over candidate).
func residentServiceStarted(cfg *Config) bool {
	return os.Getenv(residentServiceEnv) == cfg.InstallationID
}

var launchdPIDPattern = regexp.MustCompile(`(?m)^\s*pid = (\d+)\s*$`)

func launchdJobPID(printed string) int {
	m := launchdPIDPattern.FindStringSubmatch(printed)
	if m == nil {
		return 0
	}
	pid, _ := strconv.Atoi(m[1])
	return pid
}

// residentAutostartEntry is the autostart file of this installation ("" where
// the OS keeps it elsewhere, i.e. the Windows scheduled task).
func residentAutostartEntry(cfg *Config) string {
	home, e := os.UserHomeDir()
	if e != nil {
		return ""
	}
	switch runtime.GOOS {
	case "darwin":
		return filepath.Join(home, "Library", "LaunchAgents", residentServiceName(cfg)+".plist")
	case "windows":
		return ""
	default:
		return filepath.Join(home, ".config", "systemd", "user", residentServiceName(cfg)+".service")
	}
}

// residentServiceMaintain upgrades the autostart entry of an installed helper and
// hands it to the service manager; true means the caller must exit. It only ever
// touches an entry the installer already created for this very executable — a
// helper run from anywhere else (a build folder, a test) installs nothing.
func residentServiceMaintain(cfg *Config) bool {
	exe, e := os.Executable()
	entry := residentAutostartEntry(cfg)
	if e != nil || entry == "" {
		return false
	}
	self, e1 := os.Stat(exe)
	installed, e2 := os.Stat(residentExecutable(cfg.DataDir))
	if e1 != nil || e2 != nil || !os.SameFile(self, installed) {
		return false
	}
	if _, e = os.Stat(entry); e != nil {
		return false
	}
	if residentAutostart(cfg, exe, false) != nil {
		return false
	}
	return residentServiceAdopt(cfg)
}

// residentServiceAdopt asks launchd to run this installation and reports whether
// the caller must exit so the launchd instance can take the control port.
// It never unloads a job that could be this very process: every ownership signal
// (new entry's environment, launchd's XPC_SERVICE_NAME, launchd's recorded pid)
// errs toward "already owned", where the only cost is waiting for the next login.
func residentServiceAdopt(cfg *Config) bool {
	if runtime.GOOS != "darwin" || strings.HasSuffix(os.Args[0], ".test") {
		return false
	}
	name := residentServiceName(cfg)
	if residentServiceStarted(cfg) || os.Getenv("XPC_SERVICE_NAME") == name {
		return false
	}
	plist := residentAutostartEntry(cfg)
	if _, e := os.Stat(plist); plist == "" || e != nil {
		return false
	}
	domain := "gui/" + strconv.Itoa(os.Getuid())
	if out, e := exec.Command("launchctl", "print", domain+"/"+name).Output(); e == nil && launchdJobPID(string(out)) == os.Getpid() {
		return false
	}
	// A loaded entry may be a stale definition without KeepAlive; reload it.
	_ = exec.Command("launchctl", "bootout", domain+"/"+name).Run()
	for attempt := 0; attempt < 5; attempt++ {
		if exec.Command("launchctl", "bootstrap", domain, plist).Run() == nil {
			return true
		}
		time.Sleep(time.Second)
	}
	return false
}
