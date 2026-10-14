package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const residentWorkerEnv = "INDIEBIZ_WINDOWS_WORKER"

func residentWorkerInvocation(id string, args []string, marker string) bool {
	return len(args) == 2 && args[1] == "--resident-worker" && marker == id
}

type residentRecoveryRecord struct {
	State     string `json:"state"`
	At        int64  `json:"at"`
	Attempt   int    `json:"attempt"`
	ExitCode  int    `json:"exit_code"`
	Detail    string `json:"detail,omitempty"`
	Output    string `json:"output,omitempty"`
	Truncated bool   `json:"truncated,omitempty"`
}

// The parent waits for process exit, never kills a live helper for a slow hub.
// Update and removal keep their existing owners. Rapid repeated failures stop
// after five attempts; a minute of running resets that burst counter.
func residentRecoveryLoop(cfg *Config, self string, run func() error, sleep func(time.Duration), now func() time.Time) error {
	failures := 0
	record := func(state string, code int, detail string) {
		_ = residentSave(filepath.Join(cfg.DataDir, "recovery.json"), residentRecoveryRecord{
			State: state, At: now().Unix(), Attempt: failures, ExitCode: code, Detail: detail})
	}
	for {
		allowed, err := residentRecoveryAllowed(cfg, self)
		if err != nil {
			record("stopped", -1, err.Error())
			return err
		}
		if !allowed {
			record("handoff", 0, "update or removal owns the next step")
			return nil
		}
		start := now()
		record("running", 0, "")
		err = run()
		if err == nil {
			record("stopped", 0, "clean exit")
			return nil
		}
		if now().Sub(start) >= time.Minute {
			failures = 0
		}
		failures++
		allowed, stateErr := residentRecoveryAllowed(cfg, self)
		if stateErr != nil {
			record("stopped", exitCode(err), stateErr.Error())
			return stateErr
		}
		if !allowed {
			record("handoff", exitCode(err), "update or removal owns the next step")
			return nil
		}
		if failures >= 5 {
			record("failed", exitCode(err), "five consecutive short-lived failures; manual restart required")
			return fmt.Errorf("resident recovery stopped after %d failures: %w", failures, err)
		}
		record("retrying", exitCode(err), "unexpected process exit")
		sleep(time.Duration(failures) * 5 * time.Second)
	}
}

func residentRecoveryAllowed(cfg *Config, self string) (bool, error) {
	b, err := os.ReadFile(filepath.Join(cfg.DataDir, "indiebiz-helper.json"))
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	var current Config
	if err = json.Unmarshal(b, &current); err != nil {
		return false, err
	}
	if current.Mode != "resident" || current.InstallationID != cfg.InstallationID || current.Generation != cfg.Generation {
		return false, nil
	}
	if _, err = os.Stat(filepath.Join(cfg.DataDir, "removing.json")); err == nil {
		return false, nil
	} else if !os.IsNotExist(err) {
		return false, err
	}
	st, err := residentLoadUpdate(cfg.DataDir)
	if err == nil {
		return st.Outcome != "" || st.To == self, nil
	}
	if !os.IsNotExist(err) {
		return false, err
	}
	return true, nil
}

type residentRecoveryTail struct {
	mu        sync.Mutex
	data      []byte
	truncated bool
}

func (w *residentRecoveryTail) Write(b []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.data = append(w.data, b...)
	if len(w.data) > 8192 {
		w.data = append([]byte(nil), w.data[len(w.data)-8192:]...)
		w.truncated = true
	}
	return len(b), nil
}

func residentWorkerEnvironment(env []string, id string) []string {
	clean := make([]string, 0, len(env)+2)
	for _, entry := range env {
		key, _, _ := strings.Cut(entry, "=")
		if !strings.EqualFold(key, residentWorkerEnv) && !strings.EqualFold(key, residentServiceEnv) {
			clean = append(clean, entry)
		}
	}
	return append(clean, residentWorkerEnv+"="+id, residentServiceEnv+"="+id)
}

func residentRunWorker(cfg *Config) error {
	cmd := exec.Command(residentExecutable(cfg.DataDir), "--resident-worker")
	cmd.Dir = cfg.DataDir
	cmd.Env = residentWorkerEnvironment(os.Environ(), cfg.InstallationID)
	configureResidentDetached(cmd)
	cmd.WaitDelay = 2 * time.Second
	var tail residentRecoveryTail
	cmd.Stdout = &tail
	cmd.Stderr = &tail
	err := cmd.Run()
	// No registration key in diagnostics. Keep only the last 8 KiB, with an
	// explicit truncation marker, instead of an unbounded background log.
	detail := ""
	if err != nil {
		detail = err.Error()
	}
	output := string(bytes.ToValidUTF8(tail.data, []byte("�")))
	if cfg.Key != "" {
		output = strings.ReplaceAll(output, cfg.Key, "[redacted]")
		detail = strings.ReplaceAll(detail, cfg.Key, "[redacted]")
	}
	_ = residentSave(filepath.Join(cfg.DataDir, "recovery-last-exit.json"), residentRecoveryRecord{
		State: "exited", At: time.Now().Unix(), ExitCode: exitCode(err), Detail: detail, Output: output, Truncated: tail.truncated})
	return err
}

var _ io.Writer = (*residentRecoveryTail)(nil)
