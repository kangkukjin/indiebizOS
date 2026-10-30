package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMachineUpdateRejectsLegacyWorkerWithoutExecutingIt(t *testing.T) {
	path := filepath.Join(t.TempDir(), "worker.exe")
	for _, tc := range []struct {
		body      string
		supported bool
	}{
		{"legacy executable", false},
		{"executable prefix" + residentMachineProtocol + "suffix", true},
	} {
		if err := os.WriteFile(path, []byte(tc.body), 0600); err != nil {
			t.Fatal(err)
		}
		if err := residentMachineCheckUpdate(path); (err == nil) != tc.supported {
			t.Fatalf("supported=%v, error=%v", tc.supported, err)
		}
	}
}

func TestMachineManagementDoesNotClaimDesktop(t *testing.T) {
	for _, op := range []string{"shell", "python", "read", "write", "list", "info", "transfer", "update", "wake"} {
		if !residentMachineOperation(op) {
			t.Fatalf("management operation rejected: %s", op)
		}
	}
	for _, op := range []string{"screen", "click", "type", "media_session", "terminal", "unknown"} {
		if residentMachineOperation(op) {
			t.Fatalf("session operation accepted: %s", op)
		}
	}
	if residentMachineActive(&Config{}) {
		t.Fatal("ordinary helper became a machine service")
	}
}
