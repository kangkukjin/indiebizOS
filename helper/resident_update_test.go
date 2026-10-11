package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func updateFixture(t *testing.T) (root, exe, staged, want string) {
	t.Helper()
	root = t.TempDir()
	exe = residentExecutable(root)
	staged = exe + ".new"
	if e := os.WriteFile(exe, []byte("old helper"), 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(staged, []byte("new helper"), 0600); e != nil {
		t.Fatal(e)
	}
	want, _, _ = fileDigest(staged)
	return
}

func read(t *testing.T, path string) string {
	t.Helper()
	b, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	return string(b)
}

func TestApplyUpdatePutsNewInPlaceAfterBackupRecordAndWatcher(t *testing.T) {
	root, exe, staged, want := updateFixture(t)
	old, _, _ := fileDigest(exe)
	watched := false
	from, e := residentApplyUpdate(root, staged, want, time.Now(), func(backup, r string) error {
		// The watcher must start while the old executable is still in place.
		if read(t, exe) != "old helper" || read(t, backup) != "old helper" || r != root {
			t.Fatal("watcher started after the swap or without a backup")
		}
		if st, e := residentLoadUpdate(root); e != nil || st.To != want || st.From != old || st.Outcome != "" {
			t.Fatalf("pending record missing: %+v %v", st, e)
		}
		watched = true
		return nil
	})
	if e != nil || !watched || from != old {
		t.Fatal(e, watched, from)
	}
	if read(t, exe) != "new helper" {
		t.Fatal("new executable not in place")
	}
	if info, _ := os.Stat(exe); info.Mode().Perm()&0100 == 0 {
		t.Fatal("new executable is not executable")
	}
}

func TestApplyUpdateRejectsWrongBytesAndLeavesInstallationUntouched(t *testing.T) {
	root, exe, staged, _ := updateFixture(t)
	other, _, _ := fileDigest(exe)
	if _, e := residentApplyUpdate(root, staged, other, time.Now(), func(string, string) error {
		t.Fatal("watcher started for a rejected file")
		return nil
	}); e == nil {
		t.Fatal("hash mismatch accepted")
	}
	if read(t, exe) != "old helper" {
		t.Fatal("installation changed")
	}
	if _, e := os.Stat(residentUpdatePath(root)); e == nil {
		t.Fatal("pending record left behind")
	}
}

func TestApplyUpdateWithoutWatcherChangesNothing(t *testing.T) {
	root, exe, staged, want := updateFixture(t)
	if _, e := residentApplyUpdate(root, staged, want, time.Now(), func(string, string) error { return os.ErrPermission }); e == nil {
		t.Fatal("applied without a watcher")
	}
	if read(t, exe) != "old helper" {
		t.Fatal("swapped although nobody can roll back")
	}
	if _, e := os.Stat(residentUpdatePath(root)); e == nil {
		t.Fatal("pending record left behind")
	}
}

func TestWatcherLeavesConfirmedUpdateAlone(t *testing.T) {
	root, exe, staged, want := updateFixture(t)
	if _, e := residentApplyUpdate(root, staged, want, time.Now(), func(string, string) error { return nil }); e != nil {
		t.Fatal(e)
	}
	residentConfirmUpdate(root, "someone-else") // a helper with other bytes must not confirm
	if _, e := os.Stat(residentUpdatePath(root)); e != nil {
		t.Fatal("confirmed by the wrong executable")
	}
	residentConfirmUpdate(root, want)
	if e := residentUpdateWatch(root, time.Millisecond, func(*Config) error {
		t.Fatal("restart requested after confirmation")
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	if read(t, exe) != "new helper" {
		t.Fatal("confirmed update was rolled back")
	}
}

func TestWatcherRestoresOldExecutableWhenNobodyConfirms(t *testing.T) {
	root, exe, staged, want := updateFixture(t)
	old := residentUpdateWindow
	residentUpdateWindow = 30 * time.Millisecond
	defer func() { residentUpdateWindow = old }()
	if e := os.WriteFile(filepath.Join(root, "indiebiz-helper.json"), []byte(`{"mode":"resident","installation_id":"abc"}`), 0600); e != nil {
		t.Fatal(e)
	}
	if _, e := residentApplyUpdate(root, staged, want, time.Now(), func(string, string) error { return nil }); e != nil {
		t.Fatal(e)
	}
	restarted := ""
	if e := residentUpdateWatch(root, 5*time.Millisecond, func(cfg *Config) error {
		if read(t, exe) != "old helper" {
			t.Fatal("restart requested before the old executable was restored")
		}
		restarted = cfg.InstallationID
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	if restarted != "abc" {
		t.Fatal("service restart not requested")
	}
	st, e := residentLoadUpdate(root)
	if e != nil || st.Outcome != "rolled_back" || st.To != want {
		t.Fatalf("rollback not recorded: %+v %v", st, e)
	}
	residentConfirmUpdate(root, want) // a late confirmation must not erase the rollback record
	if _, e = os.Stat(residentUpdatePath(root)); e != nil {
		t.Fatal("rollback record erased")
	}
}

func TestSelfUpdateRefusedOutsideServiceManager(t *testing.T) {
	r := &residentRuntime{cfg: &Config{InstallationID: "x", DataDir: t.TempDir()}}
	res := r.selfUpdate(nil, Command{}, "t", "s")
	if res["error"] != "self_update_unsupported" {
		t.Fatal(res)
	}
}
