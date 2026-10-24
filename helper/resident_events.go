package main

// Disk is the queue; channels only coalesce wakeups. No receive-WebSocket writes.
import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type residentEventBatch struct {
	events  []residentEvent
	paths   map[string]string
	pending int
}

func residentNotify(ch chan struct{}) {
	select {
	case ch <- struct{}{}:
	default:
	}
}
func (r *residentRuntime) startEvents() {
	r.ctx, r.cancel = context.WithCancel(context.Background())
	r.eventsWake, r.syncWake = make(chan struct{}, 1), make(chan struct{}, 1)
	r.eventsWG.Add(1)
	go func() { defer r.eventsWG.Done(); r.publishEvents() }()
}
func (r *residentRuntime) eventBatch() (residentEventBatch, error) {
	paths, err := filepath.Glob(filepath.Join(r.cfg.DataDir, "spool", "events", "*.json"))
	batch := residentEventBatch{events: []residentEvent{}, paths: map[string]string{}, pending: len(paths)}
	if err != nil {
		return batch, err
	}
	sort.Strings(paths)
	size := 0
	for _, path := range paths {
		if len(batch.events) == 64 {
			break
		}
		raw, err := os.ReadFile(path)
		if os.IsNotExist(err) {
			continue
		}
		if err != nil {
			return batch, err
		}
		var ev residentEvent
		if err = json.Unmarshal(raw, &ev); err != nil {
			return batch, err
		}
		if size+len(raw) > 4*1024*1024 && len(batch.events) > 0 {
			break
		}
		size += len(raw)
		batch.events = append(batch.events, ev)
		batch.paths[ev.EventID] = path
	}
	return batch, nil
}
func (b residentEventBatch) ack(resp map[string]interface{}, sent []residentEvent) int {
	removed := 0
	allowed := map[string]bool{}
	for _, ev := range sent {
		allowed[ev.EventID] = true
	}
	acks, _ := resp["ack"].([]interface{})
	for _, raw := range acks {
		id, _ := raw.(string)
		if allowed[id] {
			if err := os.Remove(b.paths[id]); err == nil {
				removed++
			}
		}
	}
	return removed
}
func (r *residentRuntime) pushEnabled() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.eventPush
}
func (r *residentRuntime) negotiateEvents(resp map[string]interface{}) {
	r.mu.Lock()
	advertised := resp["event_push"] == float64(1) || resp["event_push"] == 1
	r.eventPush = advertised && !time.Now().Before(r.pushRetry)
	r.mu.Unlock()
	residentNotify(r.eventsWake)
}
func (r *residentRuntime) runtimeFailure() (error, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.failure != nil {
		return r.failure, r.remove
	}
	return r.ctx.Err(), false
}
func (r *residentRuntime) fail(err error, remove bool) {
	r.mu.Lock()
	if r.failure == nil {
		r.failure, r.remove = err, remove
	}
	r.stopping = true
	r.cancel()
	for _, cancel := range r.active {
		cancel()
	}
	r.mu.Unlock()
}
func (r *residentRuntime) responseState(resp map[string]interface{}) error {
	if resp["state"] == "removal_pending" || resp["state"] == "removed" {
		err := fmt.Errorf("registration removed")
		r.fail(err, true)
		return err
	}
	if resp["generation"] != r.cfg.Generation {
		err := fmt.Errorf("registration generation mismatch")
		r.fail(err, false)
		return err
	}
	return nil
}
func (r *residentRuntime) responseControls(resp map[string]interface{}) error {
	if err := r.responseState(resp); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	cancels, _ := resp["cancel"].([]interface{})
	for _, id := range cancels {
		jid, _ := id.(string)
		if cancel := r.active[jid]; cancel != nil {
			cancel()
		}
		r.cancelQueued(jid)
	}
	return nil
}
func (r *residentRuntime) wait(delay time.Duration) {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-r.ctx.Done():
	case <-r.syncWake:
	case <-timer.C:
	}
}
func (r *residentRuntime) waitRetry(delay time.Duration) {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-r.ctx.Done():
	case <-timer.C:
	}
}
func (r *residentRuntime) publishEvents() {
	delay := time.Duration(0)
	backoff := time.Second
	for {
		if delay > 0 {
			timer := time.NewTimer(delay)
			var wake <-chan struct{}
			if backoff == time.Second {
				wake = r.eventsWake
			}
			select {
			case <-r.ctx.Done():
				timer.Stop()
				return
			case <-wake:
				timer.Stop()
			case <-timer.C:
			}
		}
		if r.ctx.Err() != nil {
			return
		}
		delay = time.Second
		if !r.pushEnabled() {
			continue
		}
		batch, err := r.eventBatch()
		if err != nil {
			r.fail(err, false)
			return
		}
		if len(batch.events) == 0 {
			continue
		}
		resp, err := residentPostContext(r.ctx, r.cfg.Base+"/limb/resident/events", map[string]interface{}{
			"key": r.cfg.Key, "installation_id": r.cfg.InstallationID, "events": batch.events,
		})
		if r.ctx.Err() != nil {
			return
		}
		if err != nil || resp["success"] != true {
			if err != nil && strings.Contains(err.Error(), "invalid_registration") {
				r.fail(err, true)
				return
			}
			var httpErr *residentHTTPError
			if errors.As(err, &httpErr) && httpErr.status == 404 {
				r.mu.Lock()
				r.eventPush = false
				r.pushRetry = time.Now().Add(time.Minute)
				r.mu.Unlock()
				residentNotify(r.syncWake)
			}
			delay = backoff
			if backoff < 30*time.Second {
				backoff *= 2
			}
			continue
		}
		if r.responseControls(resp) != nil {
			return
		}
		removed := batch.ack(resp, batch.events)
		residentNotify(r.syncWake)
		backoff = time.Second
		if removed > 0 {
			delay = 0
		}
	}
}
