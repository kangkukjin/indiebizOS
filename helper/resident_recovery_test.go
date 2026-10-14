package main

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func recoveryFixture(t *testing.T) *Config {
	t.Helper()
	cfg := &Config{Mode: "resident", DataDir: t.TempDir(), InstallationID: strings.Repeat("a", 32), Generation: "g1"}
	if err := residentSave(filepath.Join(cfg.DataDir, "indiebiz-helper.json"), cfg); err != nil {
		t.Fatal(err)
	}
	return cfg
}
func TestRecoveryRestartsUnexpectedExitAndStopsOnCleanExit(t *testing.T) {
	cfg := recoveryFixture(t)
	runs := 0
	var waits []time.Duration
	err := residentRecoveryLoop(cfg, "old", func() error {
		runs++
		if runs < 3 {
			return errors.New("crash")
		}
		return nil
	}, func(d time.Duration) { waits = append(waits, d) }, time.Now)
	if err != nil || runs != 3 || !reflect.DeepEqual(waits, []time.Duration{5 * time.Second, 10 * time.Second}) {
		t.Fatal(runs, waits, err)
	}
}
func TestRecoveryStopsRepeatedImmediateFailures(t *testing.T) {
	cfg := recoveryFixture(t)
	runs, waits := 0, 0
	err := residentRecoveryLoop(cfg, "old", func() error { runs++; return errors.New("crash") }, func(time.Duration) { waits++ }, time.Now)
	if err == nil || runs != 5 || waits != 4 {
		t.Fatal(runs, waits, err)
	}
	b, _ := os.ReadFile(filepath.Join(cfg.DataDir, "recovery.json"))
	if !strings.Contains(string(b), `"state":"failed"`) {
		t.Fatal(string(b))
	}
}
func TestRecoveryResetsBurstAfterStableRun(t *testing.T) {
	cfg := recoveryFixture(t)
	runs := 0
	stamp := time.Unix(100, 0)
	var waits []time.Duration
	err := residentRecoveryLoop(cfg, "old", func() error {
		runs++
		if runs == 5 {
			stamp = stamp.Add(time.Minute)
		}
		if runs == 6 {
			return nil
		}
		return errors.New("crash")
	}, func(d time.Duration) { waits = append(waits, d) }, func() time.Time { return stamp })
	if err != nil || runs != 6 || waits[4] != 5*time.Second {
		t.Fatal(runs, waits, err)
	}
}
func TestRecoveryHandsOffOldGenerationButStartsUpdateCandidate(t *testing.T) {
	cfg := recoveryFixture(t)
	if err := residentSave(residentUpdatePath(cfg.DataDir), residentUpdateState{From: "old", To: "new"}); err != nil {
		t.Fatal(err)
	}
	for _, self := range []string{"old", "new"} {
		runs := 0
		err := residentRecoveryLoop(cfg, self, func() error { runs++; return nil }, func(time.Duration) { t.Fatal("unexpected wait") }, time.Now)
		want := 0
		if self == "new" {
			want = 1
		}
		if err != nil || runs != want {
			t.Fatal(self, runs, err)
		}
	}
}
func TestRecoveryDoesNotRaceUpdateWatcherAfterExit(t *testing.T) {
	cfg := recoveryFixture(t)
	runs := 0
	err := residentRecoveryLoop(cfg, "old", func() error {
		runs++
		if err := residentSave(residentUpdatePath(cfg.DataDir), residentUpdateState{To: "new"}); err != nil {
			t.Fatal(err)
		}
		return errors.New("restarting into updated helper")
	}, func(time.Duration) { t.Fatal("old supervisor must exit") }, time.Now)
	if err != nil || runs != 1 {
		t.Fatal(runs, err)
	}
}
func TestRecoveryDoesNotUndoRemovalOrReenrollment(t *testing.T) {
	for _, kind := range []string{"cleanup", "removed", "generation", "corrupt"} {
		t.Run(kind, func(t *testing.T) {
			cfg := recoveryFixture(t)
			path := filepath.Join(cfg.DataDir, "indiebiz-helper.json")
			switch kind {
			case "removed":
				_ = os.Remove(path)
			case "corrupt":
				_ = os.WriteFile(path, []byte("{"), 0600)
			default:
				changed := *cfg
				if kind == "cleanup" {
					changed.Mode = "cleanup"
				} else {
					changed.Generation = "g2"
				}
				_ = residentSave(path, changed)
			}
			err := residentRecoveryLoop(cfg, "old", func() error { t.Fatal("must not restart"); return nil }, func(time.Duration) { t.Fatal("must not wait") }, time.Now)
			if (err != nil) != (kind == "corrupt") {
				t.Fatal(err)
			}
		})
	}
}
func TestRecoveryDoesNotKillLiveWorkerForSlowNetwork(t *testing.T) {
	cfg := recoveryFixture(t)
	entered, finish, done := make(chan struct{}), make(chan struct{}), make(chan error, 1)
	go func() {
		done <- residentRecoveryLoop(cfg, "old", func() error { close(entered); <-finish; return nil }, func(time.Duration) {}, time.Now)
	}()
	<-entered
	select {
	case err := <-done:
		t.Fatalf("returned while child lives: %v", err)
	case <-time.After(30 * time.Millisecond):
	}
	close(finish)
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}
func TestRecoveryTailAndChildEnvironmentAreBounded(t *testing.T) {
	var w residentRecoveryTail
	_, _ = w.Write([]byte(strings.Repeat("x", 9000)))
	_, _ = w.Write([]byte("end"))
	if len(w.data) != 8192 || !w.truncated || !strings.HasSuffix(string(w.data), "end") {
		t.Fatal(len(w.data), w.truncated)
	}
	env := residentWorkerEnvironment([]string{"PATH=test", "indiebiz_windows_worker=old", "INDIEBIZ_SERVICE=old"}, "new")
	want := []string{"PATH=test", residentWorkerEnv + "=new", residentServiceEnv + "=new"}
	if !reflect.DeepEqual(env, want) {
		t.Fatal(env)
	}
}

// The update watcher inherits worker environment. Its new default executable
// must enter the supervisor, not silently bypass recovery after every update.
func TestRecoveryWorkerMarkerAloneCannotBypassSupervisor(t *testing.T) {
	for _, args := range [][]string{{"helper"}, {"helper", "--resident-update-watch", "root"}} {
		if residentWorkerInvocation("one", args, "one") {
			t.Fatal(args)
		}
	}
	if residentWorkerInvocation("one", []string{"helper", "--resident-worker"}, "other") {
		t.Fatal("wrong installation")
	}
	if !residentWorkerInvocation("one", []string{"helper", "--resident-worker"}, "one") {
		t.Fatal("explicit worker rejected")
	}
}
