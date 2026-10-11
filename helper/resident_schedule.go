package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

// Observation has its own bounded slot. Never guess whether shell text is
// read-only: callers explicitly request observe with a short execution deadline.
func residentObservation(j Job) bool {
	var c struct {
		Op      string `json:"op"`
		Mode    string `json:"mode"`
		Timeout int    `json:"timeout"`
	}
	if json.Unmarshal([]byte(j.Code), &c) != nil {
		return false
	}
	return c.Op == "screen" || c.Op == "info" || c.Op == "list" || c.Op == "read" ||
		(c.Op == "shell" && c.Mode == "observe" && c.Timeout >= 1 && c.Timeout <= 10)
}

func (r *residentRuntime) schedule() error {
	// The random job ID is not submission order. Persist receipt order so it
	// survives reconnect/restart, including a fallback for old queued records.
	paths, _ := filepath.Glob(filepath.Join(r.cfg.DataDir, "spool", "jobs", "*.json"))
	queued := []residentRecord{}
	for _, p := range paths {
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var v residentRecord
		if err = json.Unmarshal(b, &v); err != nil {
			return err
		}
		if v.State != "queued" {
			continue
		}
		if v.QueuedAt == 0 {
			info, err := os.Stat(p)
			if err != nil {
				return err
			}
			v.QueuedAt = info.ModTime().UnixNano()
		}
		queued = append(queued, v)
	}
	sort.SliceStable(queued, func(i, j int) bool { return queued[i].QueuedAt < queued[j].QueuedAt })
	for _, v := range queued {
		r.mu.Lock()
		if r.stopping || r.localPaused || r.updating {
			r.mu.Unlock()
			break
		}
		observation := residentObservation(v.Job)
		if (observation && r.observing >= 1) || (!observation && len(r.active)-r.observing >= 2) {
			r.mu.Unlock()
			continue // A full work lane must not hide checks later in the queue.
		}
		v.State = "running"
		if err := r.record(v); err != nil {
			r.mu.Unlock()
			return err
		}
		if err := r.event(v.Job.ID, "started", map[string]interface{}{}); err != nil {
			r.mu.Unlock()
			return err
		}
		ctx, cancel := context.WithCancel(context.Background())
		r.active[v.Job.ID] = cancel
		if observation {
			r.observing++
		}
		r.wg.Add(1)
		r.mu.Unlock()
		go func(v residentRecord, observation bool) {
			defer r.wg.Done()
			defer cancel()
			result := r.execute(ctx, v.Job)
			v.State, v.Result = "done", result
			// Keep the running record on persistence failure; recovery reports unknown.
			if err := r.event(v.Job.ID, "result", result); err == nil {
				_ = r.record(v)
			}
			r.mu.Lock()
			delete(r.active, v.Job.ID)
			if observation {
				r.observing--
			}
			r.mu.Unlock()
		}(v, observation)
	}
	return nil
}
