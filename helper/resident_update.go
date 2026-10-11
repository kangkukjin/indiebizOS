package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
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
// service manager starts the new one. Whether the new one is good is decided by
// a process that survives both: a watcher run from a copy of the old executable.
// The new helper confirms by deleting update.json after its first good sync; if
// that does not happen in time the watcher restores the old executable and asks
// the service manager to restart. If the watcher itself dies, the service manager
// still keeps whatever executable is in place alive.

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

// Only an instance the service manager restarts can replace itself by exiting.
func residentCanSelfUpdate(cfg *Config) bool {
	return runtime.GOOS != "windows" && residentServiceStarted(cfg)
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
		e = os.Rename(staged, exe)
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
	if runtime.GOOS == "darwin" {
		return exec.Command("launchctl", "kickstart", "-k", "gui/"+strconv.Itoa(os.Getuid())+"/"+name).Run()
	}
	return exec.Command("systemctl", "--user", "restart", name).Run()
}

// residentUpdateWatch runs from the backup executable. It returns when the new
// helper confirmed, or after restoring the old executable.
func residentUpdateWatch(root string, poll time.Duration, restart func(*Config) error) error {
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
		if float64(time.Now().UnixNano())/1e9 < st.Deadline {
			time.Sleep(poll)
			continue
		}
		exe := residentExecutable(root)
		if e = residentCopy(st.Backup, exe+".restore"); e != nil {
			return e
		}
		if e = os.Rename(exe+".restore", exe); e != nil {
			return e
		}
		st.Outcome = "rolled_back"
		if e = residentSave(residentUpdatePath(root), st); e != nil {
			return e
		}
		b, e := os.ReadFile(filepath.Join(root, "indiebiz-helper.json"))
		if e != nil {
			return e
		}
		var cfg Config
		if e = json.Unmarshal(b, &cfg); e != nil {
			return e
		}
		return restart(&cfg)
	}
}

func (r *residentRuntime) selfUpdate(ctx context.Context, c Command, tid, want string) map[string]interface{} {
	if !residentCanSelfUpdate(r.cfg) {
		return errResult("self_update_unsupported", "서비스 관리자가 재기동하는 설치(macOS launchd·Linux systemd)에서만 스스로 교체합니다")
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
	return pendingEvents == 0 || time.Since(r.restartAt) > 30*time.Second
}
