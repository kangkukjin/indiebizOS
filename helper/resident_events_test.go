package main

import (
	"context"
	"encoding/json"
	"github.com/gorilla/websocket"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func eventEventually(t *testing.T, check func() bool) {
	t.Helper()
	end := time.Now().Add(4 * time.Second)
	for time.Now().Before(end) {
		if check() {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("event condition did not complete")
}
func eventReply(w http.ResponseWriter, req *http.Request, generation string) []residentEvent {
	var body struct {
		Events []residentEvent `json:"events"`
	}
	_ = json.NewDecoder(req.Body).Decode(&body)
	ids := []string{}
	for _, event := range body.Events {
		ids = append(ids, event.EventID)
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "generation": generation, "ack": ids, "state": "active"})
	return body.Events
}

func TestEventsCompleteDuringBlockedReceive(t *testing.T) {
	r := residentTestRuntime(t)
	blocked, delivered := make(chan struct{}), make(chan struct{}, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/limb/resident/sync" {
			_, _ = io.Copy(io.Discard, req.Body)
			close(blocked)
			<-req.Context().Done()
			return
		}
		eventReply(w, req, r.cfg.Generation)
		delivered <- struct{}{}
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	r.startEvents()
	defer r.stop()
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	transport := residentTransport{base: server.URL, retry: time.Now().Add(time.Hour)}
	receiveDone := make(chan struct{})
	go func() {
		defer close(receiveDone)
		_, _ = transport.syncContext(r.ctx, map[string]interface{}{"wait": 20})
	}()
	<-blocked
	if err := r.event(residentID(), "result", map[string]interface{}{"ok": true}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-delivered:
	case <-time.After(time.Second):
		t.Fatal("result waited for receive")
	}
	eventEventually(t, func() bool { b, _ := r.eventBatch(); return b.pending == 0 })
	r.stop()
	select {
	case <-receiveDone:
	case <-time.After(time.Second):
		t.Fatal("receive not cancelled")
	}
}

func TestEventsAckLossRetainsIDAnd404Backoff(t *testing.T) {
	r := residentTestRuntime(t)
	var calls atomic.Int32
	ids := make(chan string, 3)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body struct {
			Events []residentEvent `json:"events"`
		}
		_ = json.NewDecoder(req.Body).Decode(&body)
		ids <- body.Events[0].EventID
		if calls.Add(1) == 1 {
			http.Error(w, "lost acknowledgement", 500)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "generation": r.cfg.Generation, "ack": []string{body.Events[0].EventID}, "state": "active"})
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	// Persistence before publisher startup models both merged/lost notifications and restart.
	if err := r.event(residentID(), "result", nil); err != nil {
		t.Fatal(err)
	}
	r.startEvents()
	defer r.stop()
	time.Sleep(30 * time.Millisecond)
	if calls.Load() != 0 {
		t.Fatal("sent before capability negotiation")
	}
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	eventEventually(t, func() bool { b, _ := r.eventBatch(); return b.pending == 0 })
	if a, b := <-ids, <-ids; a != b {
		t.Fatal("retry changed event ID")
	}
	if calls.Load() != 2 {
		t.Fatal("unexpected duplicate attempts")
	}
}

func TestEvents404FallsBackWithoutRenegotiationLoop(t *testing.T) {
	r := residentTestRuntime(t)
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) { calls.Add(1); http.NotFound(w, req) }))
	defer server.Close()
	r.cfg.Base = server.URL
	r.startEvents()
	defer r.stop()
	_ = r.event(residentID(), "result", nil)
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	eventEventually(t, func() bool { r.mu.Lock(); defer r.mu.Unlock(); return !r.pushRetry.IsZero() })
	for i := 0; i < 100; i++ {
		r.negotiateEvents(map[string]interface{}{"event_push": 1})
	}
	if r.pushEnabled() {
		t.Fatal("404 cooldown was ignored")
	}
	batch, _ := r.eventBatch()
	if len(batch.events) != 1 {
		t.Fatal("404 lost durable event")
	}
	resp := map[string]interface{}{"ack": []interface{}{batch.events[0].EventID}}
	var wg sync.WaitGroup
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); batch.ack(resp, batch.events) }()
	}
	wg.Wait()
	batch, _ = r.eventBatch()
	if batch.pending != 0 {
		t.Fatal("concurrent ack failed")
	}
}

func TestEventsStopCancelsInflightAndRetainsSpool(t *testing.T) {
	r := residentTestRuntime(t)
	started := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		_, _ = io.Copy(io.Discard, req.Body)
		close(started)
		<-req.Context().Done()
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	r.startEvents()
	_ = r.event(residentID(), "result", nil)
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	<-started
	done := make(chan struct{})
	go func() { r.stop(); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("publisher not joined")
	}
	b, _ := r.eventBatch()
	if b.pending != 1 {
		t.Fatal("unacknowledged event deleted")
	}
}

func TestEventsGenerationAndRemovalStopWithoutAck(t *testing.T) {
	for _, state := range []string{"removed", "active"} {
		t.Run(state, func(t *testing.T) {
			r := residentTestRuntime(t)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				_ = json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "generation": "different", "state": state})
			}))
			defer server.Close()
			r.cfg.Base = server.URL
			r.startEvents()
			defer r.stop()
			_ = r.event(residentID(), "result", nil)
			r.negotiateEvents(map[string]interface{}{"event_push": 1})
			eventEventually(t, func() bool { return r.ctx.Err() != nil })
			err, remove := r.runtimeFailure()
			if err == nil || remove != (state == "removed") {
				t.Fatal("wrong terminal state")
			}
			b, _ := r.eventBatch()
			if b.pending != 1 {
				t.Fatal("wrong generation acknowledged event")
			}
		})
	}
}

func TestEventsBatchLimitsAndUpdateAck(t *testing.T) {
	r := residentTestRuntime(t)
	for i := 0; i < 70; i++ {
		if err := r.event(residentID(), "result", nil); err != nil {
			t.Fatal(err)
		}
	}
	b, err := r.eventBatch()
	if err != nil || len(b.events) != 64 || b.pending != 70 {
		t.Fatal("batch limits", b, err)
	}
	r.restartAt = time.Now()
	if r.restartDue(0) {
		t.Fatal("stale empty snapshot allowed restart")
	}
	if r.restartDue(b.pending) {
		t.Fatal("restart before ack")
	}
	ids := []interface{}{}
	for _, ev := range b.events {
		ids = append(ids, ev.EventID)
	}
	b.ack(map[string]interface{}{"ack": ids}, nil) // unrelated ACKs cannot erase unsent files
	b, _ = r.eventBatch()
	if b.pending != 70 {
		t.Fatal("unsent events erased")
	}
	b.ack(map[string]interface{}{"ack": ids}, b.events)
	b, _ = r.eventBatch()
	if b.pending != 6 {
		t.Fatal("batch ACK deleted other events")
	}
	for _, path := range b.paths {
		_ = os.Remove(path)
	}
	b, _ = r.eventBatch()
	if !r.restartDue(b.pending) {
		t.Fatal("ack did not permit restart")
	}
	r.restartAt = time.Now().Add(-31 * time.Second)
	if !r.restartDue(1) {
		t.Fatal("30s upper bound changed")
	}
}

func TestEventsCancellationAndIdle(t *testing.T) {
	r := residentTestRuntime(t)
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) { calls.Add(1); eventReply(w, req, r.cfg.Generation) }))
	defer server.Close()
	r.cfg.Base = server.URL
	r.startEvents()
	defer r.stop()
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	time.Sleep(100 * time.Millisecond)
	if calls.Load() != 0 {
		t.Fatal("idle network spin")
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	id := residentID()
	r.active[id] = cancel
	if err := r.responseControls(map[string]interface{}{"generation": r.cfg.Generation, "cancel": []interface{}{id}, "paused": true}); err != nil {
		t.Fatal(err)
	}
	if ctx.Err() == nil {
		t.Fatal("publisher cancellation ignored")
	}
}

func TestEventsIndependentOfBlockedWebSocket(t *testing.T) {
	r := residentTestRuntime(t)
	received, release, delivered := make(chan struct{}), make(chan struct{}), make(chan struct{}, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/limb/resident/ws" {
			conn, err := (&websocket.Upgrader{}).Upgrade(w, req, nil)
			if err != nil {
				return
			}
			defer conn.Close()
			var body map[string]interface{}
			if conn.ReadJSON(&body) != nil {
				return
			}
			close(received)
			<-release
			return
		}
		eventReply(w, req, r.cfg.Generation)
		delivered <- struct{}{}
	}))
	defer server.Close()
	defer close(release)
	r.cfg.Base = server.URL
	r.startEvents()
	defer r.stop()
	r.negotiateEvents(map[string]interface{}{"event_push": 1})
	receiver := residentTransport{base: server.URL}
	done := make(chan struct{})
	go func() {
		defer close(done)
		defer receiver.close()
		_, _ = receiver.syncContext(r.ctx, map[string]interface{}{"wait": 20})
	}()
	select {
	case <-received:
	case <-time.After(time.Second):
		t.Fatal("WS receive never started")
	}
	_ = r.event(residentID(), "result", nil)
	select {
	case <-delivered:
	case <-time.After(time.Second):
		t.Fatal("event blocked behind WS")
	}
	r.stop()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("WS not cancelled")
	}
}
