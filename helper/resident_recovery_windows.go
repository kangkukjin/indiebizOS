package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"golang.org/x/sys/windows"
)

// A Run entry starts once per login. This parent owns the installed worker's
// lifetime instead; no admin service, new registry entry or power setting.
func startResidentManaged(cfg *Config) error {
	if residentWorkerInvocation(cfg.InstallationID, os.Args, os.Getenv(residentWorkerEnv)) {
		return startResident(cfg)
	}
	exe, err := os.Executable()
	self, e1 := os.Stat(exe)
	installed, e2 := os.Stat(residentExecutable(cfg.DataDir))
	if err != nil || e1 != nil || e2 != nil || !os.SameFile(self, installed) {
		return startResident(cfg)
	}
	if !residentValidID(cfg.InstallationID) || cfg.Generation == "" {
		return os.ErrInvalid
	}
	release, duplicate, err := residentRecoveryLock(cfg.InstallationID)
	if err != nil {
		return err
	}
	if duplicate {
		var control struct {
			URL string `json:"url"`
		}
		if b, e := os.ReadFile(filepath.Join(cfg.DataDir, "control.json")); e == nil && json.Unmarshal(b, &control) == nil && control.URL != "" && residentOldHelperRunning(cfg) {
			residentOpen(control.URL)
		}
		return nil
	}
	defer release()
	return residentRecoveryLoop(cfg, residentSelfDigest(), func() error { return residentRunWorker(cfg) }, time.Sleep, time.Now)
}

// A named kernel object remains exclusive while this parent's handle lives;
// Windows releases it even if the parent crashes. No stale PID/lock file.
func residentRecoveryLock(id string) (func(), bool, error) {
	name, err := windows.UTF16PtrFromString(`Local\IndieBizResidentRecovery-` + id)
	if err != nil {
		return nil, false, err
	}
	handle, err := windows.CreateMutex(nil, false, name)
	if errors.Is(err, windows.ERROR_ALREADY_EXISTS) {
		if handle != 0 {
			windows.CloseHandle(handle)
		}
		return nil, true, nil
	}
	if err != nil {
		if handle != 0 {
			windows.CloseHandle(handle)
		}
		return nil, false, err
	}
	return func() { windows.CloseHandle(handle) }, false, nil
}
