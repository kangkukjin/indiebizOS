package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type residentEvent struct {
	EventID  string                 `json:"event_id"`
	JobID    string                 `json:"job_id"`
	Kind     string                 `json:"kind"`
	Payload  map[string]interface{} `json:"payload"`
	Occurred float64                `json:"occurred_at"`
}
type residentRecord struct {
	Job      Job                    `json:"job"`
	State    string                 `json:"state"`
	Result   map[string]interface{} `json:"result,omitempty"`
	QueuedAt int64                  `json:"queued_at,omitempty"`
}
type residentRuntime struct {
	cfg         *Config
	mu          sync.Mutex
	active      map[string]context.CancelFunc
	observing   int
	stopping    bool
	localPaused bool
	wg          sync.WaitGroup
}

func (r *residentRuntime) event(jid, kind string, payload map[string]interface{}) error {
	e := residentEvent{residentID(), jid, kind, payload, float64(time.Now().UnixNano()) / 1e9}
	path := filepath.Join(r.cfg.DataDir, "spool", "events", fmt.Sprintf("%020d-%s.json", time.Now().UnixNano(), e.EventID))
	return residentSave(path, e)
}
func (r *residentRuntime) record(v residentRecord) error {
	if v.State == "queued" && v.QueuedAt == 0 {
		v.QueuedAt = time.Now().UnixNano()
	}
	return residentSave(filepath.Join(r.cfg.DataDir, "spool", "jobs", v.Job.ID+".json"), v)
}
func (r *residentRuntime) capabilities() map[string]interface{} {
	hostname, _ := os.Hostname()
	mpv, _ := findMediaPlayer()
	_, afplay := exec.LookPath("afplay")
	return map[string]interface{}{"os": runtime.GOOS, "hostname": hostname, "arch": runtime.GOARCH, "kind": "pc", "adapter": "resident-v1", "shell": true, "transfer": true, "wake_relay": true, "media": mpv != "" || afplay == nil, "media_player": mpv, "interactive": true, "max_parallel": 2, "observation_parallel": 1, "screen_observation": true, "screen_cancel": true, "media_volume": true, "observation_shell_timeout": 10, "cpu_hard_limit": false, "memory_hard_limit": false, "service_scope": "user_login", "generation": r.cfg.Generation}
}
func startResident(cfg *Config) error {
	if len(cfg.InstallationID) != 32 || cfg.Generation == "" || cfg.DataDir == "" {
		return fmt.Errorf("invalid resident configuration")
	}
	if _, e := os.Stat(filepath.Join(cfg.DataDir, "removing.json")); e == nil {
		return residentRemove(cfg)
	}
	portValue, _ := strconv.ParseUint(cfg.InstallationID[:4], 16, 32)
	listener, e := net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(30000+int(portValue)%20000))
	if e != nil {
		b, _ := os.ReadFile(filepath.Join(cfg.DataDir, "control.json"))
		var old map[string]string
		_ = json.Unmarshal(b, &old)
		if old["url"] != "" {
			residentOpen(old["url"])
		}
		return fmt.Errorf("resident already running or control port unavailable: %w", e)
	}
	defer listener.Close()
	r := &residentRuntime{cfg: cfg, active: map[string]context.CancelFunc{}}
	if b, e := os.ReadFile(filepath.Join(cfg.DataDir, "paused.json")); e == nil {
		_ = json.Unmarshal(b, &r.localPaused)
	}
	r.localControl(listener)
	// Never retry a side effect whose process died before a durable result was saved.
	records, _ := filepath.Glob(filepath.Join(cfg.DataDir, "spool", "jobs", "*.json"))
	for _, path := range records {
		b, e := os.ReadFile(path)
		if e != nil {
			return e
		}
		var v residentRecord
		if e = json.Unmarshal(b, &v); e != nil {
			return e
		}
		if v.State == "running" {
			v.State = "done"
			v.Result = map[string]interface{}{"unknown": true, "error": "helper_restarted_during_execution"}
			if e = r.record(v); e != nil {
				return e
			}
			if e = r.event(v.Job.ID, "result", v.Result); e != nil {
				return e
			}
		}
	}
	transport := &residentTransport{base: cfg.Base}
	defer transport.close()
	backoff := time.Second
	for {
		if cfg.ExpiresAt > 0 && float64(time.Now().Unix()) >= cfg.ExpiresAt {
			r.stop()
			return residentRemove(cfg)
		}
		paths, _ := filepath.Glob(filepath.Join(cfg.DataDir, "spool", "events", "*.json"))
		sort.Strings(paths)
		if len(paths) > 64 {
			paths = paths[:64]
		}
		events := []residentEvent{}
		batchBytes := 0
		for _, p := range paths {
			b, e := os.ReadFile(p)
			if e != nil {
				return e
			}
			var ev residentEvent
			if e = json.Unmarshal(b, &ev); e != nil {
				return e
			}
			if batchBytes+len(b) > 4*1024*1024 && len(events) > 0 {
				break
			}
			batchBytes += len(b)
			events = append(events, ev)
		}
		r.mu.Lock()
		busy := len(r.active) > 0
		r.mu.Unlock()
		wait := 20
		if busy || len(events) > 0 {
			wait = 0
		}
		resp, e := transport.sync(map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID, "events": events, "capabilities": r.capabilities(), "wait": wait})
		if e != nil || resp["success"] != true {
			if e != nil && strings.Contains(e.Error(), "invalid_registration") {
				r.stop()
				return residentRemove(cfg)
			}
			time.Sleep(backoff)
			if backoff < 30*time.Second {
				backoff *= 2
			}
			continue
		}
		backoff = time.Second
		acks, _ := resp["ack"].([]interface{})
		acked := map[string]bool{}
		for _, a := range acks {
			if id, ok := a.(string); ok {
				acked[id] = true
			}
		}
		for i, ev := range events {
			if acked[ev.EventID] {
				_ = os.Remove(paths[i])
			}
		}
		if resp["state"] == "removal_pending" || resp["state"] == "removed" {
			r.stop()
			return residentRemove(cfg)
		}
		if resp["generation"] != cfg.Generation {
			r.stop()
			return fmt.Errorf("registration generation mismatch")
		}
		jobs, _ := resp["jobs"].([]interface{})
		for _, raw := range jobs {
			b, _ := json.Marshal(raw)
			var j Job
			if e = json.Unmarshal(b, &j); e != nil {
				return e
			}
			if !residentValidID(j.ID) {
				return fmt.Errorf("invalid job id")
			}
			path := filepath.Join(cfg.DataDir, "spool", "jobs", j.ID+".json")
			if _, e = os.Stat(path); os.IsNotExist(e) {
				if e = r.record(residentRecord{Job: j, State: "queued"}); e != nil {
					return e
				}
			}
		}
		r.mu.Lock()
		cancels, _ := resp["cancel"].([]interface{})
		for _, id := range cancels {
			jid, _ := id.(string)
			if cancel := r.active[jid]; cancel != nil {
				cancel()
			}
			r.cancelQueued(jid)
		}
		r.mu.Unlock()
		r.mu.Lock()
		localPaused := r.localPaused
		r.mu.Unlock()
		if resp["paused"] != true && !localPaused {
			if e = r.schedule(); e != nil {
				return e
			}
		}
		if wait == 0 || resp["paused"] == true {
			time.Sleep(500 * time.Millisecond)
		}
	}
}
func residentValidID(id string) bool {
	if len(id) != 32 {
		return false
	}
	for _, c := range id {
		if !strings.ContainsRune("0123456789abcdef", c) {
			return false
		}
	}
	return true
}
func (r *residentRuntime) cancelQueued(jid string) {
	if !residentValidID(jid) {
		return
	}
	path := filepath.Join(r.cfg.DataDir, "spool", "jobs", jid+".json")
	b, e := os.ReadFile(path)
	if e != nil {
		return
	}
	var v residentRecord
	if json.Unmarshal(b, &v) != nil || v.State != "queued" {
		return
	}
	v.State = "done"
	v.Result = map[string]interface{}{"cancelled": true}
	if r.record(v) == nil {
		_ = r.event(jid, "result", v.Result)
	}
}
func (r *residentRuntime) stop() {
	r.mu.Lock()
	r.stopping = true
	for _, cancel := range r.active {
		cancel()
	}
	r.mu.Unlock()
	r.wg.Wait()
}
func (r *residentRuntime) localControl(listener net.Listener) {
	token := residentID()
	url := "http://" + listener.Addr().String() + "/?token=" + token
	_ = residentSave(filepath.Join(r.cfg.DataDir, "control.json"), map[string]string{"url": url})
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Query().Get("token") != token {
			http.Error(w, "forbidden", 403)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		if req.Method == "POST" {
			action := req.FormValue("action")
			if action == "remove" {
				go func() {
					r.stop()
					if residentRemove(r.cfg) == nil {
						os.Exit(0)
					}
				}()
				fmt.Fprint(w, "로컬 제거를 시작했습니다. 중앙 기록 확인이 지연될 수 있습니다.")
				return
			}
			paused := action == "pause"
			if e := residentSave(filepath.Join(r.cfg.DataDir, "paused.json"), paused); e != nil {
				http.Error(w, e.Error(), 500)
				return
			}
			r.mu.Lock()
			r.localPaused = paused
			r.mu.Unlock()

		}
		fmt.Fprint(w, `<!doctype html><meta charset="utf-8"><title>IndieBiz PC 관리</title><h1>상주 헬퍼 실행 중</h1><p>중앙 기록에 모든 작업이 저장됩니다. 제거해도 작업 폴더는 보존합니다.</p><form method="post"><button name="action" value="pause">새 작업 중지</button><button name="action" value="resume">재개</button><button name="action" value="remove">이 PC 등록 해제 및 제거</button></form>`)
	})
	go (&http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second}).Serve(listener)
}
