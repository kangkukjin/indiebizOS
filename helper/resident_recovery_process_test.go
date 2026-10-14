//go:build !windows

package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRecoveryWorkerRunsIsolatedAndRecordsExitWithoutKey(t *testing.T) {
	cfg := recoveryFixture(t)
	cfg.Key = "limb_private_test_value"
	script := "#!/bin/sh\n[ \"$INDIEBIZ_WINDOWS_WORKER\" = \"" + cfg.InstallationID + "\" ] || exit 99\n[ \"$INDIEBIZ_SERVICE\" = \"" + cfg.InstallationID + "\" ] || exit 98\nprintf 'worker failed: " + cfg.Key + "' >&2\nexit 7\n"
	if err := os.WriteFile(residentExecutable(cfg.DataDir), []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	if err := residentRunWorker(cfg); exitCode(err) != 7 {
		t.Fatal(err)
	}
	b, err := os.ReadFile(filepath.Join(cfg.DataDir, "recovery-last-exit.json"))
	if err != nil {
		t.Fatal(err)
	}
	var rec residentRecoveryRecord
	if err = json.Unmarshal(b, &rec); err != nil || rec.ExitCode != 7 || strings.Contains(string(b), cfg.Key) || !strings.Contains(rec.Output, "[redacted]") {
		t.Fatal(string(b), err)
	}
}
