package main

import (
	"archive/zip"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestMemberExportProgramResources(t *testing.T) {
	m := testMember(t)
	dir := t.TempDir()
	program := filepath.Join(dir, "main.py")
	os.WriteFile(program, []byte("print('portable')"), 0600)
	os.WriteFile(filepath.Join(dir, "template.txt"), []byte("resource"), 0600)
	if r := m.store.register(Command{ScriptID: "portable", Path: program, Resources: []string{"template.txt"}, Dependencies: []string{"example==1.0"}}); r["success"] != true {
		t.Fatal(r)
	}
	out := m.export("")
	if out["success"] != true {
		t.Fatal(out)
	}
	z, e := zip.OpenReader(out["path"].(string))
	if e != nil {
		t.Fatal(e)
	}
	defer z.Close()
	found := map[string]bool{}
	for _, f := range z.File {
		found[f.Name] = true
	}
	if !found["programs/0/main.py"] || !found["programs/0/template.txt"] || !found["manifest.json"] {
		t.Fatal(found)
	}
}

func TestMemberRunningCanOnlyBeClaimedOnce(t *testing.T) {
	m := testMember(t)
	m.store.claim("once", "fp")
	if e := m.store.running("once"); e != nil {
		t.Fatal(e)
	}
	if e := m.store.running("once"); e == nil {
		t.Fatal("duplicate running claim")
	}
}

func testMember(t *testing.T) *MemberRuntime {
	t.Helper()
	dir := t.TempDir()
	s, e := openMemberStore(dir)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { s.db.Close() })
	m := &MemberRuntime{store: s, dir: dir, cfg: &Config{AutoAllow: []string{"write", "file_move"}}, approvals: map[string]*Approval{}}
	if err := m.initTasks(); err != nil {
		t.Fatal(err)
	}
	return m
}
func job(c Command) Job { b, _ := json.Marshal(c); return Job{ID: "test", Code: string(b)} }
func TestMemberRetryAndConflict(t *testing.T) {
	m := testMember(t)
	p := filepath.Join(t.TempDir(), "a")
	c := Command{Op: "write", Path: p, Content: "A", Member: true, RequestKey: "one"}
	r := m.run(job(c))
	if r["success"] != true {
		t.Fatal(r)
	}
	os.WriteFile(p, []byte("B"), 0600)
	r = m.run(job(c))
	b, _ := os.ReadFile(p)
	if string(b) != "B" || r["state"] != "completed" {
		t.Fatal("retry executed", r)
	}
	c.Content = "C"
	if m.run(job(c))["error"] != "key_conflict" {
		t.Fatal("conflict accepted")
	}
}
func TestMemberApproval(t *testing.T) {
	m := testMember(t)
	m.cfg.AutoAllow = nil
	p := filepath.Join(t.TempDir(), "a")
	c := Command{Op: "write", Path: p, Content: "A", Member: true, RequestKey: "approval"}
	out := make(chan map[string]interface{}, 1)
	go func() { out <- m.run(job(c)) }()
	var a *Approval
	for i := 0; i < 200; i++ {
		m.mu.Lock()
		a = m.approvals[c.RequestKey]
		m.mu.Unlock()
		if a != nil {
			break
		}
		time.Sleep(time.Millisecond)
	}
	if a == nil {
		t.Fatal("no approval")
	}
	if _, e := os.Stat(p); e == nil {
		t.Fatal("unapproved write")
	}
	a.answer <- false
	if r := <-out; r["error"] != "permission_denied" {
		t.Fatal(r)
	}
}
func TestMemberCrashUnknown(t *testing.T) {
	dir := t.TempDir()
	s, e := openMemberStore(dir)
	if e != nil {
		t.Fatal(e)
	}
	s.claim("crash", "fp")
	s.running("crash")
	s.db.Close()
	s, e = openMemberStore(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer s.db.Close()
	r, run, e := s.claim("crash", "fp")
	if e != nil || run || r["state"] != "unknown" {
		t.Fatal(r, run, e)
	}
}
func TestMemberMemoryIsolation(t *testing.T) {
	a, b := testMember(t), testMember(t)
	r := a.store.save(map[string]interface{}{"id": "turn1", "user": "A-private", "assistant": "done", "episode": map[string]interface{}{"success": true}})
	if r["success"] != true {
		t.Fatal(r)
	}
	ar, _ := json.Marshal(a.store.recall("", 40))
	br, _ := json.Marshal(b.store.recall("", 40))
	if string(ar) == string(br) {
		t.Fatal("mixed stores")
	}
	if len(b.store.recall("", 40)["history"].([]map[string]interface{})) != 0 {
		t.Fatal("B saw A")
	}
}
func TestMemberNoLegacyExecution(t *testing.T) {
	m := testMember(t)
	if m.run(job(Command{Op: "shell", Cmd: "echo must-not-run"}))["error"] != "member_envelope_required" {
		t.Fatal("legacy command allowed")
	}
}

func TestMemberApprovalShellIsBundled(t *testing.T) {
	m := testMember(t)
	t.Setenv("INDIEBIZ_MEMBER_NO_BROWSER", "1")
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("approval shell fetched from hub")
		w.Write([]byte("malicious-hub-script"))
	}))
	defer hub.Close()
	m.cfg.Base = hub.URL
	m.token = "synthetic-ui-token"
	if e := m.serve(); e != nil {
		t.Fatal(e)
	}
	defer m.server.Close()
	r, e := http.Get(m.localURL + "/")
	if e != nil {
		t.Fatal(e)
	}
	b, _ := io.ReadAll(r.Body)
	r.Body.Close()
	if !strings.Contains(string(b), "memberApprovals") || strings.Contains(string(b), "malicious-hub-script") {
		t.Fatal("untrusted shell")
	}
	for _, origin := range []string{"", "http://attacker.invalid"} {
		req, _ := http.NewRequest("GET", m.localURL+"/member/history", nil)
		if origin != "" {
			req.Header.Set("X-Member-Token", m.token)
			req.Header.Set("Origin", origin)
		}
		resp, e := http.DefaultClient.Do(req)
		if e != nil {
			t.Fatal(e)
		}
		resp.Body.Close()
		if resp.StatusCode != 403 {
			t.Fatal("local gate bypassed")
		}
	}
}

func TestMemberMediaRequiresApprovalAndSingleClaim(t *testing.T) {
	m := testMember(t)
	command := Command{Op: "media", Action: "play", URL: "https://example.test/audio.mp3", Member: true, RequestKey: "media-one"}
	out := make(chan map[string]interface{}, 1)
	go func() { out <- m.run(job(command)) }()
	var approval *Approval
	for i := 0; i < 1000; i++ {
		m.mu.Lock()
		approval = m.approvals[command.RequestKey]
		pending := m.mediaPending
		m.mu.Unlock()
		if pending != nil {
			t.Fatal("media dispatched before approval")
		}
		if approval != nil {
			break
		}
		time.Sleep(time.Millisecond)
	}
	if approval == nil {
		t.Fatal("no media approval")
	}
	approval.answer <- true
	for i := 0; i < 1000; i++ {
		m.mu.Lock()
		pending := m.mediaPending
		m.mu.Unlock()
		if pending != nil {
			break
		}
		time.Sleep(time.Millisecond)
	}
	if result := m.claimMedia(command.RequestKey).(map[string]interface{}); result["success"] != true {
		t.Fatal(result)
	}
	if result := m.claimMedia(command.RequestKey).(map[string]interface{}); result["success"] == true {
		t.Fatal("duplicate media claim")
	}
	if err := m.mediaResult(command.RequestKey, map[string]interface{}{"success": false, "error": "unsupported_codec"}); err != nil {
		t.Fatal(err)
	}
	if result := <-out; result["success"] != false {
		t.Fatal("false playback success", result)
	}
	if result := m.run(job(command)); result["error"] != "unsupported_codec" {
		t.Fatal("replayed media", result)
	}
}

func TestMemberMediaRejectsFileScheme(t *testing.T) {
	m := testMember(t)
	result := m.media(Command{Action: "play", URL: "file:///owner/key"})
	if result["error"] != "url" {
		t.Fatal(result)
	}
}
