package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"time"
)

// Self-update of an installed helper, driven by one hub job.
//
// The helper downloads the new executable, puts it in place and exits; the
// service manager (or the Windows watcher) starts the new one. Its health is checked by
// a process that survives both: a watcher run from a copy of the old executable.
// The new helper confirms by deleting update.json after its first good sync; if
// that does not happen in time the watcher restores the old executable and asks
// the service manager to restart. Windows starts the installed file directly, or uses an existing legacy login task.

type residentUpdateState struct {
	From     string  `json:"from"`
	To       string  `json:"to"`
	Backup   string  `json:"backup"`
	Started  float64 `json:"started"`
	Deadline float64 `json:"deadline"`
	Outcome  string  `json:"outcome,omitempty"` // "" while pending, then "rolled_back"
}

var residentUpdateWindow = 5 * time.Minute

func residentUpdatePath(root string) string { return filepath.Join(root, "update.json") }

func residentLoadUpdate(root string) (*residentUpdateState, error) {
	b, e := os.ReadFile(residentUpdatePath(root))
	if e != nil {
		return nil, e
	}
	var st residentUpdateState
	if e = json.Unmarshal(b, &st); e != nil {
		return nil, e
	}
	return &st, nil
}

var (
	selfDigestOnce  sync.Once
	selfDigestValue string
)

// residentSelfDigest is the SHA-256 of the running executable ("" if unreadable).
func residentSelfDigest() string {
	selfDigestOnce.Do(func() {
		if exe, e := os.Executable(); e == nil {
			selfDigestValue, _, _ = fileDigest(exe)
		}
	})
	return selfDigestValue
}

// residentWatchStarts: on Windows logon startup does not restart an exited
// helper, so the update watcher starts the new one itself once the old one let go
// of the control port (a var so tests can exercise that path on any OS).
var residentWatchStarts = runtime.GOOS == "windows"

// Only an instance something restarts can replace itself by exiting: the service
// manager on macOS/Linux; on Windows the watcher, through the installation's Run entry or legacy task.
func residentCanSelfUpdate(cfg *Config) bool {
	if runtime.GOOS != "windows" {
		return residentServiceStarted(cfg)
	}
	exe, e := os.Executable()
	self, e1 := os.Stat(exe)
	installed, e2 := os.Stat(residentExecutable(cfg.DataDir))
	if e != nil || e1 != nil || e2 != nil || !os.SameFile(self, installed) {
		return false
	}
	return residentWindowsCanRestart(cfg)
}

// residentPlaceExecutable renames src over dest. Windows will not replace a
// running executable but lets it be renamed, so there it is moved aside first.
func residentPlaceExecutable(src, dest string) error {
	if runtime.GOOS != "windows" {
		return os.Rename(src, dest)
	}
	aside := dest + ".replaced"
	_ = os.Remove(aside) // still running from an earlier update: left for next time
	if e := os.Rename(dest, aside); e != nil && !os.IsNotExist(e) {
		return e
	}
	if e := os.Rename(src, dest); e != nil {
		_ = os.Rename(aside, dest)
		return e
	}
	return nil
}

func residentValidDigest(s string) bool {
	b, e := hex.DecodeString(s)
	return e == nil && len(b) == 32 && s == hex.EncodeToString(b)
}

// residentApplyUpdate swaps a verified staged executable into place. Order:
// backup, pending record, watcher, rename — every earlier failure leaves the
// running installation untouched.
func residentApplyUpdate(root, staged, want string, now time.Time, watch func(backup, root string) error) (string, error) {
	got, _, e := fileDigest(staged)
	if e != nil {
		return "", e
	}
	if got != want {
		_ = os.Remove(staged)
		return "", fmt.Errorf("hash_mismatch")
	}
	exe := residentExecutable(root)
	from, _, e := fileDigest(exe)
	if e != nil {
		return "", e
	}
	if e = os.Chmod(staged, 0700); e != nil {
		return "", e
	}
	backup := exe + ".previous"
	if e = residentCopy(exe, backup+".tmp"); e != nil {
		return "", e
	}
	if e = os.Rename(backup+".tmp", backup); e != nil {
		return "", e
	}
	started := float64(now.UnixNano()) / 1e9
	st := residentUpdateState{From: from, To: want, Backup: backup, Started: started, Deadline: started + residentUpdateWindow.Seconds()}
	if e = residentSave(residentUpdatePath(root), st); e != nil {
		return "", e
	}
	if e = watch(backup, root); e == nil {
		e = residentPlaceExecutable(staged, exe)
	}
	if e != nil {
		_ = os.Remove(residentUpdatePath(root)) // the watcher exits when the record is gone
		return "", e
	}
	return from, nil
}

func residentStartUpdateWatcher(backup, root string) error {
	cmd := exec.Command(backup, "--resident-update-watch", root)
	configureResidentDetached(cmd)
	return cmd.Start()
}

// residentConfirmUpdate is called by a helper that reached the hub.
func residentConfirmUpdate(root, self string) {
	if st, e := residentLoadUpdate(root); e == nil && st.Outcome == "" && st.To == self {
		_ = os.Remove(residentUpdatePath(root))
	}
}

func residentServiceRestart(cfg *Config) error {
	name := residentServiceName(cfg)
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("launchctl", "kickstart", "-k", "gui/"+strconv.Itoa(os.Getuid())+"/"+name).Run()
	case "windows":
		return residentWindowsRestart(cfg)
	}
	return exec.Command("systemctl", "--user", "restart", name).Run()
}

// residentUpdateWatch runs from the backup executable. It returns when the new
// helper confirmed, or after restoring the old executable.
//
// Where nothing restarts an exited helper (residentWatchStarts) the watcher first
// waits for the old helper to release the control port, then starts the new one.
func residentUpdateWatch(root string, poll time.Duration, restart func(*Config) error) error {
	var cfg *Config
	for {
		st, e := residentLoadUpdate(root)
		if os.IsNotExist(e) {
			return nil
		}
		if e != nil {
			return e
		}
		if st.Outcome != "" {
			return nil
		}
		if cfg == nil {
			b, e := os.ReadFile(filepath.Join(root, "indiebiz-helper.json"))
			if e != nil {
				return e
			}
			cfg = &Config{}
			if e = json.Unmarshal(b, cfg); e != nil {
				return e
			}
		}
		if float64(time.Now().UnixNano())/1e9 < st.Deadline {
			if residentWatchStarts && !residentOldHelperRunning(cfg) {
				// A released port does not mean the scheduler has retired the old
				// task yet. Retry until a helper actually owns the port or time runs out.
				_ = restart(cfg)
			}
			time.Sleep(poll)
			continue
		}
		exe := residentExecutable(root)
		var unconfirmed []int
		if residentWatchStarts { // nothing else will stop the build that never confirmed
			unconfirmed = residentExecutablePIDs(exe)
		}
		if e = residentCopy(st.Backup, exe+".restore"); e != nil {
			return e
		}
		if e = residentPlaceExecutable(exe+".restore", exe); e != nil {
			return e
		}
		st.Outcome = "rolled_back"
		if e = residentSave(residentUpdatePath(root), st); e != nil {
			return e
		}
		for _, pid := range unconfirmed {
			residentKillPID(pid)
		}
		if residentWatchStarts {
			for attempt := 0; attempt < 30 && residentOldHelperRunning(cfg); attempt++ {
				time.Sleep(poll)
			}
		}
		return restart(cfg)
	}
}

// residentOldHelperRunning: a helper of this installation still holds its control port.
var residentOldHelperRunning = func(cfg *Config) bool {
	c, e := net.DialTimeout("tcp", residentControlAddress(cfg.InstallationID), time.Second)
	if e != nil {
		return false
	}
	_ = c.Close()
	return true
}

func (r *residentRuntime) selfUpdate(ctx context.Context, c Command, tid, want string) map[string]interface{} {
	if !residentCanSelfUpdate(r.cfg) {
		return errResult("self_update_unsupported", "설치된 헬퍼(macOS launchd·Linux systemd·Windows 로그인 예약 작업)만 스스로 교체합니다")
	}
	if !residentValidDigest(want) {
		return errResult("invalid_sha256", "")
	}
	exe := residentExecutable(r.cfg.DataDir)
	if current, _, e := fileDigest(exe); e == nil && current == want {
		return map[string]interface{}{"updated": false, "sha256": want}
	}
	r.mu.Lock()
	busy := len(r.active) > 1
	if !busy {
		r.updating = true
	}
	r.mu.Unlock()
	if busy {
		return errResult("helper_busy", "실행 중인 다른 작업이 끝난 뒤 다시 시도하세요")
	}
	applied := false
	defer func() {
		if !applied {
			r.mu.Lock()
			r.updating = false
			r.mu.Unlock()
		}
	}()
	staged := exe + ".new"
	_ = os.Remove(staged)
	c.Path = staged
	if res := r.transfer(ctx, c, tid); res["error"] != nil {
		_ = os.Remove(staged)
		return res
	}
	from, e := residentApplyUpdate(r.cfg.DataDir, staged, want, time.Now(), residentStartUpdateWatcher)
	if e != nil {
		_ = os.Remove(staged)
		return errResult("update_failed", e.Error())
	}
	applied = true
	r.mu.Lock()
	r.restartAt = time.Now()
	r.mu.Unlock()
	return map[string]interface{}{"updated": true, "restarting": true, "from": from, "to": want}
}

// restartDue reports that the update job finished and its result reached the hub
// (or 30 seconds passed); the caller then exits so the service manager restarts.
func (r *residentRuntime) restartDue(pendingEvents int) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.restartAt.IsZero() || len(r.active) > 0 {
		return false
	}
	// The caller's spool snapshot may predate the final event and active removal.
	// Under mu, an empty active map implies every worker already persisted its result.
	if pendingEvents == 0 {
		paths, err := filepath.Glob(filepath.Join(r.cfg.DataDir, "spool", "events", "*.json"))
		if err != nil {
			return time.Since(r.restartAt) > 30*time.Second
		}
		pendingEvents = len(paths)
	}
	return pendingEvents == 0 || time.Since(r.restartAt) > 30*time.Second
}
