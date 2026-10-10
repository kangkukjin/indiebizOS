package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func residentReadRecord(t *testing.T, r *residentRuntime, j Job) residentRecord {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(r.cfg.DataDir, "spool", "jobs", j.ID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	var v residentRecord
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatal(err)
	}
	return v
}

func TestResidentObservationBypassesWorkButRemainsBounded(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX command fixture")
	}
	r := residentTestRuntime(t)
	// Fill both lanes without depending on shell launch timing.
	r.active["work1"], r.active["work2"] = func() {}, func() {}
	r.active["check"] = func() {}
	r.observing = 1
	work := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "echo work"})
	first := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "echo first", "mode": "observe", "timeout": 1})
	second := residentTestJob(t, map[string]interface{}{"op": "list"})
	// Reverse lexical IDs prove scheduling follows receipt order, not UUID order.
	first.ID, second.ID = "ffffffffffffffffffffffffffffffff", "00000000000000000000000000000000"
	for i, j := range []Job{work, first, second} {
		if err := r.record(residentRecord{Job: j, State: "queued", QueuedAt: int64(i + 1)}); err != nil {
			t.Fatal(err)
		}
	}
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	if residentReadRecord(t, r, first).State != "queued" {
		t.Fatal("observation exceeded limit")
	}
	delete(r.active, "check")
	r.observing = 0
	r.localPaused = true
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	if residentReadRecord(t, r, first).State != "queued" {
		t.Fatal("pause bypassed")
	}
	r.localPaused = false
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	r.wg.Wait()
	if residentReadRecord(t, r, first).State != "done" {
		t.Fatal("check blocked by work")
	}
	if residentReadRecord(t, r, work).State != "queued" {
		t.Fatal("work exceeded limit")
	}
	// A second check may start in the same scan if the first finished already;
	// only assert the persisted start events keep FIFO order.
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	r.wg.Wait()
	if residentReadRecord(t, r, second).State != "done" {
		t.Fatal("next check not scheduled")
	}
	paths, _ := filepath.Glob(filepath.Join(r.cfg.DataDir, "spool", "events", "*.json"))
	var started []string
	for _, path := range paths {
		b, _ := os.ReadFile(path)
		var ev residentEvent
		_ = json.Unmarshal(b, &ev)
		if ev.Kind == "started" {
			started = append(started, ev.JobID)
		}
	}
	if len(started) != 2 || started[0] != first.ID || started[1] != second.ID {
		t.Fatal(started)
	}
}

func TestResidentObservationValidationAndTimeout(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX command fixture")
	}
	r := residentTestRuntime(t)
	for _, body := range []map[string]interface{}{
		{"op": "shell", "mode": "observe", "cmd": "echo bad"},
		{"op": "shell", "mode": "observe", "timeout": 11, "cmd": "echo bad"},
		{"op": "write", "mode": "observe", "timeout": 1},
	} {
		j := residentTestJob(t, body)
		if residentObservation(j) {
			t.Fatal("invalid check got reserved slot")
		}
		if r.execute(context.Background(), j)["error"] != "invalid_observation" {
			t.Fatal("invalid check executed")
		}
	}
	j := residentTestJob(t, map[string]interface{}{"op": "shell", "mode": "observe", "timeout": 1, "cmd": "sleep 20"})
	start := time.Now()
	if got := r.execute(context.Background(), j); got["timeout"] != true {
		t.Fatal(got)
	}
	if time.Since(start) > 3*time.Second {
		t.Fatal("observation deadline was not enforced")
	}
}
