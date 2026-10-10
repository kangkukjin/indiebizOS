package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"github.com/gorilla/websocket"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"
)

func residentTestRuntime(t *testing.T) *residentRuntime {
	t.Helper()
	return &residentRuntime{cfg: &Config{DataDir: t.TempDir(), InstallationID: residentID(), Generation: "generation"}, active: map[string]context.CancelFunc{}}
}
func residentTestJob(t *testing.T, body map[string]interface{}) Job {
	t.Helper()
	body["resident"] = true
	body["generation"] = "generation"
	b, e := json.Marshal(body)
	if e != nil {
		t.Fatal(e)
	}
	return Job{residentID(), string(b)}
}
func TestResidentIsolationAndDuplicateExecution(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX shell fixture")
	}
	r := residentTestRuntime(t)
	a := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "printf '%s' \"$RESIDENT_TEST_VALUE\"; pwd", "env": map[string]string{"RESIDENT_TEST_VALUE": "private"}})
	result := r.execute(context.Background(), a)
	if result["exit"] != 0 || !strings.Contains(result["output"].(string), "private") {
		t.Fatal(result)
	}
	b := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "printf '%s' \"${RESIDENT_TEST_VALUE-unset}\"; pwd"})
	other := r.execute(context.Background(), b)
	if !strings.Contains(other["output"].(string), "unset") || result["cwd"] == other["cwd"] {
		t.Fatal(result, other)
	}
	count := filepath.Join(r.cfg.DataDir, "count")
	j := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "echo one >> '" + count + "'"})
	if e := r.record(residentRecord{Job: j, State: "queued"}); e != nil {
		t.Fatal(e)
	}
	if e := r.schedule(); e != nil {
		t.Fatal(e)
	}
	if e := r.schedule(); e != nil {
		t.Fatal(e)
	}
	r.wg.Wait()
	if e := r.schedule(); e != nil {
		t.Fatal(e)
	}
	r.wg.Wait()
	content, e := os.ReadFile(count)
	if e != nil || string(content) != "one\n" {
		t.Fatalf("replayed: %q %v", content, e)
	}
}
func TestResidentCancellationKillsChildren(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX process tree fixture")
	}
	r := residentTestRuntime(t)
	marker := filepath.Join(r.cfg.DataDir, "escaped")
	j := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "(sleep 0.6; echo child > '" + marker + "') & wait"})
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	got := r.execute(ctx, j)
	if got["timeout"] != true {
		t.Fatal(got)
	}
	time.Sleep(700 * time.Millisecond)
	if _, e := os.Stat(marker); !os.IsNotExist(e) {
		t.Fatal("child survived cancellation")
	}
}
func TestResidentGenerationAndInteractiveGates(t *testing.T) {
	r := residentTestRuntime(t)
	j := residentTestJob(t, map[string]interface{}{"op": "click"})
	if r.execute(context.Background(), j)["error"] != "needs_interactive" {
		t.Fatal("interactive gate bypassed")
	}
	j.Code = strings.ReplaceAll(j.Code, "generation\"}", "wrong\"}")
	j = Job{residentID(), `{"op":"shell","cmd":"echo should-not-run","resident":true,"generation":"old"}`}
	if r.execute(context.Background(), j)["error"] != "stale_registration" {
		t.Fatal("stale generation accepted")
	}
}
func TestResidentTransferResumeAndNoClobber(t *testing.T) {
	r := residentTestRuntime(t)
	data := []byte{0, 255, 128, 1, 0, 7}
	hash := sha256.Sum256(data)
	tid := residentID()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]interface{}
		_ = json.NewDecoder(req.Body).Decode(&body)
		if body["key"] != "key" || body["installation_id"] != r.cfg.InstallationID {
			t.Error("missing scoped credentials")
		}
		var out interface{} = map[string]interface{}{"direction": "to_pc", "state": "committed", "size": len(data), "sha256": hex.EncodeToString(hash[:])}
		if body["action"] == "read" {
			off := int(body["offset"].(float64))
			out = map[string]interface{}{"data": base64.StdEncoding.EncodeToString(data[off:]), "offset": len(data)}
		}
		_ = json.NewEncoder(w).Encode(out)
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	r.cfg.Key = "key"
	dest := filepath.Join(r.cfg.DataDir, "file.bin")
	_ = os.WriteFile(dest+".indiebiz-"+tid+".part", data[:3], 0600)
	got, e := r.transferFile(context.Background(), Command{Path: dest}, tid)
	if e != nil || got["state"] != "committed" {
		t.Fatal(got, e)
	}
	b, _ := os.ReadFile(dest)
	if string(b) != string(data) {
		t.Fatal(b)
	}
	_ = os.WriteFile(dest, []byte("user edit"), 0600)
	if _, e = r.transferFile(context.Background(), Command{Path: dest}, tid); e == nil {
		t.Fatal("overwrote user file")
	}
}
func TestResidentWebsocketReuseAndHTTPFallback(t *testing.T) {
	var mu sync.Mutex
	connections := 0
	fallback := 0
	upgrader := websocket.Upgrader{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/limb/resident/ws" {
			mu.Lock()
			connections++
			mu.Unlock()
			c, e := upgrader.Upgrade(w, req, nil)
			if e != nil {
				return
			}
			defer c.Close()
			for {
				var v map[string]interface{}
				if c.ReadJSON(&v) != nil {
					return
				}
				if c.WriteJSON(map[string]interface{}{"success": true}) != nil {
					return
				}
			}
		} else {
			mu.Lock()
			fallback++
			mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"success": true})
		}
	}))
	defer server.Close()
	tr := &residentTransport{base: server.URL}
	defer tr.close()
	for i := 0; i < 3; i++ {
		got, e := tr.sync(map[string]interface{}{})
		if e != nil || got["success"] != true {
			t.Fatal(got, e)
		}
	}
	tr.close()
	tr.retry = time.Now().Add(time.Hour)
	if _, e := tr.sync(map[string]interface{}{}); e != nil {
		t.Fatal(e)
	}
	mu.Lock()
	defer mu.Unlock()
	if connections != 1 || fallback != 1 {
		t.Fatal(connections, fallback)
	}
}

func TestResidentWakeAcceptsHubCompactMAC(t *testing.T) {
	r := residentTestRuntime(t)
	j := residentTestJob(t, map[string]interface{}{"op": "wake", "mac": "001122334455", "broadcast": "127.0.0.1"})
	got := r.execute(context.Background(), j)
	if got["state"] != "signal_sent" || got["ready"] != false {
		t.Fatal(got)
	}
}

func TestResidentCancelledBeforeLaunchDoesNotExecute(t *testing.T) {
	r := residentTestRuntime(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	j := residentTestJob(t, map[string]interface{}{"op": "write", "path": filepath.Join(r.cfg.DataDir, "unexpected"), "content": "should not write"})
	got := r.execute(ctx, j)
	if got["cancelled"] != true {
		t.Fatal(got)
	}
	if _, e := os.Stat(filepath.Join(r.cfg.DataDir, "unexpected")); !os.IsNotExist(e) {
		t.Fatal("cancelled work ran")
	}
}
