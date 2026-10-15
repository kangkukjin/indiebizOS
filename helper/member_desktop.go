package main

import (
	"bufio"

	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

var memberVersion = "0.1.1"

var bodySessionMu sync.RWMutex

func bodySession() string         { bodySessionMu.RLock(); defer bodySessionMu.RUnlock(); return sessionID }
func setBodySession(value string) { bodySessionMu.Lock(); sessionID = value; bodySessionMu.Unlock() }

// Configuration arrives only over the parent pipe; it is never put in argv or a file.
func memberDesktopMain() int {
	reader := bufio.NewReader(os.Stdin)
	raw, err := reader.ReadString('\n')
	if err != nil || len(raw) > 65536 {
		return 1
	}
	var cfg Config
	if json.Unmarshal([]byte(raw), &cfg) != nil || !cfg.Desktop || cfg.Mode != "member" || cfg.PrivateKey == "" || cfg.DataDir == "" {
		return 1
	}
	hubCfg = &cfg
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error { return http.ErrUseLastResponse }
	if startMember(&cfg) != nil {
		return 1
	}
	m := memberRuntime
	_ = json.NewEncoder(os.Stdout).Encode(map[string]interface{}{"origin": m.localURL, "token": m.token, "protocol": 2, "version": memberVersion})
	// Only the first stdout line is read by Electron. No secret is sent to a renderer.
	go func() {
		_, _ = io.Copy(io.Discard, reader)
		m.stopLocalWork()
		m.execMu.Lock()
		m.execMu.Unlock()
		_ = m.server.Close()
		os.Exit(0)
	}()
	go func() {
		for range time.NewTicker(2 * time.Second).C {
			m.mu.Lock()
			expired := !m.lastContact.IsZero() && time.Since(m.lastContact) > 90*time.Second
			m.mu.Unlock()
			if expired {
				m.stopLocalWork()
			}
		}
	}()
	for {
		if connect(&cfg, hostLabel()) == nil {
			break
		}
		time.Sleep(3 * time.Second)
	}
	m.contact()
	go m.resumeDesktopTasks()
	loop(&cfg)
	m.stopLocalWork()
	return 0
}
func (m *MemberRuntime) contact() {
	m.mu.Lock()
	m.lastContact = time.Now()
	m.transportOnline = true
	m.mu.Unlock()
}
func signMember(req *http.Request, raw []byte, cfg *Config) error {
	if cfg == nil || !cfg.Desktop {
		return nil
	}
	seed, err := base64.StdEncoding.DecodeString(cfg.PrivateKey)
	if err != nil || len(seed) != ed25519.SeedSize {
		return fmt.Errorf("invalid installation key")
	}
	stamp := strconv.FormatInt(time.Now().Unix(), 10)
	nonce := randomToken()
	digest := sha256.Sum256(raw)
	message := req.Method + "\n" + req.URL.RequestURI() + "\n" + hex.EncodeToString(digest[:]) + "\n" + stamp + "\n" + nonce
	req.Header.Set("X-Member-Time", stamp)
	req.Header.Set("X-Member-Nonce", nonce)
	req.Header.Set("X-Member-Signature", base64.StdEncoding.EncodeToString(ed25519.Sign(ed25519.NewKeyFromSeed(seed), []byte(message))))
	return nil
}
func (m *MemberRuntime) desktopValid(c Command) bool {
	if !m.cfg.Desktop {
		return true
	}
	m.taskMu.Lock()
	active := m.runningTask == c.TaskID && c.TaskID != ""
	m.taskMu.Unlock()
	m.mu.Lock()
	live := m.transportOnline && !m.lastContact.IsZero() && time.Since(m.lastContact) <= 90*time.Second && !m.taskStopped
	m.mu.Unlock()
	return active && live && c.BodySession != "" && c.BodySession == bodySession()
}
func (m *MemberRuntime) desktopTask(id, message, code string) {
	m.desktopTaskBody(id, map[string]interface{}{"message": message, "code": code})
}
func (m *MemberRuntime) desktopTaskBody(id string, body map[string]interface{}) {
	rid := randomToken()[:32]
	_, err := m.store.db.Exec("INSERT INTO desktop_requests VALUES(?,?,0,'pending')", rid, id)
	if err != nil {
		m.finishDesktop(id, "failed", errResult("storage", err.Error()))
		return
	}
	m.mu.Lock()
	m.requestID = rid
	m.taskStopped = false
	m.mu.Unlock()
	// Do not retry submit after an uncertain response. Status is safe to retry.
	var out map[string]interface{}
	payload := map[string]interface{}{"version": 2, "key": m.cfg.Key, "body_session": bodySession(), "task_id": id, "request_id": rid}
	for _, k := range []string{"message", "code", "action_id", "args"} {
		if v, ok := body[k]; ok {
			payload[k] = v
		}
	}
	if payload["action_id"] != nil {
		apps := m.localApps(map[string]interface{}{}, id)
		payload["local_apps"] = apps["instruments"]
		if payload["local_apps"] == nil {
			delete(payload, "local_apps")
		}
	}
	err = postJSON(m.cfg.Base+"/m/desktop/submit", payload, &out)
	if err == nil && out["success"] != true {
		m.finishDesktop(id, "failed", out)
		return
	}
	m.watchDesktop(id, rid)
}
func (m *MemberRuntime) watchDesktop(id, rid string) {
	cursor := 0
	_ = m.store.db.QueryRow("SELECT cursor FROM desktop_requests WHERE request=?", rid).Scan(&cursor)
	failures := 0
	for {
		m.mu.Lock()
		stopped := m.taskStopped
		m.mu.Unlock()
		if stopped {
			m.finishDesktop(id, "cancelled", errResult("cancelled", "작업을 중단했습니다"))
			return
		}
		var out map[string]interface{}
		err := postJSON(m.cfg.Base+"/m/desktop/status", map[string]interface{}{"key": m.cfg.Key, "request_id": rid, "after": cursor}, &out)
		if err != nil {
			failures++
			if failures >= 45 {
				m.stopLocalWork()
				m.finishDesktop(id, "unknown", errResult("connection", "연결을 확인하세요. 요청을 자동 재실행하지 않았습니다"))
				return
			}
			time.Sleep(2 * time.Second)
			continue
		}
		failures = 0
		if out["success"] != true {
			m.finishDesktop(id, "unknown", out)
			return
		}
		if events, ok := out["events"].([]interface{}); ok {
			for _, v := range events {
				e, _ := v.(map[string]interface{})
				if e != nil {
					m.taskEvent(id, "progress", e["event"])
				}
			}
		}
		if n, ok := out["cursor"].(float64); ok {
			cursor = int(n)
			_, _ = m.store.db.Exec("UPDATE desktop_requests SET cursor=? WHERE request=?", cursor, rid)
		}
		state, _ := out["state"].(string)
		if state != "running" && state != "accepted" {
			result, _ := out["result"].(map[string]interface{})
			if result == nil {
				result = out
			}
			if state == "completed" {
				result = m.receiveArtifacts(id, rid, result)
				if result["error"] != nil || result["success"] == false {
					state = "failed"
				}
			}
			if result["input_required"] != nil {
				state = "input_required"
			}
			m.finishDesktop(id, state, result)
			return
		}
		time.Sleep(time.Second)
	}
}
func (m *MemberRuntime) finishDesktop(id, state string, result map[string]interface{}) {
	b, _ := json.Marshal(result)
	_, _ = m.store.db.Exec("UPDATE tasks SET state=?,result=?,updated=? WHERE id=?", state, string(b), time.Now().Unix(), id)
	_, _ = m.store.db.Exec("UPDATE desktop_requests SET state=? WHERE task=? AND state='pending'", state, id)
	answer := result["response"]
	if answer == nil {
		answer = result["error"]
	}
	m.taskEvent(id, "assistant", answer)
	m.mu.Lock()
	m.requestID = ""
	m.mu.Unlock()
}
func (m *MemberRuntime) resumeDesktopTasks() {
	// A restarted executor does not revive old commands; only reconcile final metadata.
	rows, err := m.store.db.Query("SELECT request,task FROM desktop_requests WHERE state='pending'")
	if err != nil {
		return
	}
	pairs := [][2]string{}
	for rows.Next() {
		var r, t string
		_ = rows.Scan(&r, &t)
		pairs = append(pairs, [2]string{r, t})
	}
	rows.Close()
	for _, p := range pairs {
		var out map[string]interface{}
		if postJSON(m.cfg.Base+"/m/desktop/status", map[string]interface{}{"key": m.cfg.Key, "request_id": p[0]}, &out) == nil {
			state, _ := out["state"].(string)
			if state == "running" || state == "accepted" {
				_ = postJSON(m.cfg.Base+"/m/desktop/cancel", map[string]interface{}{"key": m.cfg.Key, "request_id": p[0]}, nil)
				state = "unknown"
			}
			if state == "" {
				state = "unknown"
			}
			result, _ := out["result"].(map[string]interface{})
			if result == nil {
				result = out
			}
			m.finishDesktop(p[1], state, result)
		}
	}
}
func (m *MemberRuntime) cancelDesktop() {
	m.mu.Lock()
	rid := m.requestID
	m.mu.Unlock()
	if rid != "" {
		go func() {
			_ = postJSON(m.cfg.Base+"/m/desktop/cancel", map[string]interface{}{"key": m.cfg.Key, "request_id": rid}, nil)
		}()
	}
}
