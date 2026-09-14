package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func addLocalTask(t *testing.T, m *MemberRuntime, id, root string) {
	t.Helper()
	_, e := m.store.db.Exec("INSERT INTO tasks VALUES(?,?,?,'idle','{}',0,0)", id, id, root)
	if e != nil {
		t.Fatal(e)
	}
}
func TestMemberWorkspaceScopesRelativeAndSymlinkPaths(t *testing.T) {
	m := testMember(t)
	root := m.workspace()
	addLocalTask(t, m, "local", root)
	c := Command{Member: true, RequestKey: "write", TaskID: "local", Op: "write", Path: "sub/file.txt", Content: "member-only"}
	if r := m.run(job(c)); r["success"] != true {
		t.Fatal(r)
	}
	if b, e := os.ReadFile(filepath.Join(root, "sub/file.txt")); e != nil || string(b) != "member-only" {
		t.Fatal(e, string(b))
	}
	outside := t.TempDir()
	if e := os.Symlink(outside, filepath.Join(root, "link")); e != nil {
		t.Fatal(e)
	}
	for _, p := range []string{"../outside", "link/file", filepath.Join(outside, "file")} {
		c.Path = p
		c.RequestKey = p
		if r := m.run(job(c)); r["error"] == nil {
			t.Fatal("escaped workspace", r)
		}
	}
	if _, e := os.Stat(filepath.Join(outside, "file")); !os.IsNotExist(e) {
		t.Fatal(e)
	}
}
func TestMemberTaskConversationsRemainSeparate(t *testing.T) {
	m := testMember(t)
	for _, id := range []string{"a", "b"} {
		addLocalTask(t, m, id, m.workspace())
		r := m.run(job(Command{Member: true, RequestKey: id, TaskID: id, Op: "memory_save", Record: map[string]interface{}{"id": id, "user": "private-" + id, "assistant": "answer"}}))
		if r["success"] != true {
			t.Fatal(r)
		}
	}
	out := m.recallTask(Command{TaskID: "a"})
	raw, _ := json.Marshal(out["history"])
	if string(raw) == "null" || !strings.Contains(string(raw), "private-a") || strings.Contains(string(raw), "private-b") {
		t.Fatal(string(raw))
	}
}
func TestMemberTaskStreamsPersistAndRestartNeverReplays(t *testing.T) {
	m := testMember(t)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)
		if r.URL.Path != "/m/run" || body["task_id"] == nil {
			t.Error(body)
		}
		fmt.Fprintln(w, `{"type":"event","event":{"type":"text","content":"progress"}}`)
		fmt.Fprintln(w, `{"type":"result","result":{"success":true,"response":"finished"}}`)
	}))
	defer hub.Close()
	m.cfg.Base = hub.URL
	m.cfg.Key = "synthetic"
	r := m.startTask(map[string]interface{}{"message": "local task"})
	if r["success"] != true {
		t.Fatal(r)
	}
	id := r["task_id"].(string)
	deadline := time.Now().Add(5 * time.Second)
	for m.task(id)["state"] == "running" && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	task := m.task(id)
	if task["state"] != "completed" {
		t.Fatal(task)
	}
	if len(task["events"].([]map[string]interface{})) != 3 {
		t.Fatal(task)
	}
	m.taskMu.Lock()
	m.taskMu.Unlock()
	m.store.db.Exec("UPDATE tasks SET state='running' WHERE id=?", id)
	if e := m.initTasks(); e != nil {
		t.Fatal(e)
	}
	if m.task(id)["state"] != "unknown" {
		t.Fatal(m.task(id))
	}
}
func TestMemberShellRunsOnlyInLocalWorkspaceAndReportsFailure(t *testing.T) {
	m := testMember(t)
	m.cfg.AutoAllow = []string{"shell"}
	root := m.workspace()
	addLocalTask(t, m, "shell", root)
	r := m.run(job(Command{Member: true, RequestKey: "cmd", TaskID: "shell", Op: "shell", Cmd: "echo member > command.txt", Timeout: 3}))
	if r["success"] != true {
		t.Fatal(r)
	}
	if _, e := os.Stat(filepath.Join(root, "command.txt")); e != nil {
		t.Fatal(e)
	}
	r = m.run(job(Command{Member: true, RequestKey: "failure", TaskID: "shell", Op: "shell", Cmd: "exit 7", Timeout: 3}))
	if r["success"] != false || r["exit"] != 7 {
		t.Fatal(r)
	}
}

func TestMemberOwnAppsFollowSelectedWorkspace(t *testing.T) {
	m := testMember(t)
	root := m.workspace()
	os.WriteFile(filepath.Join(root, "apps.json"), []byte(`[{"id":"my-app","name":"내 앱","action":"[self:script]{op:run,id:mine}"}]`), 0600)
	out := m.localApps(map[string]interface{}{"instruments": []interface{}{}}, "")
	if len(out["instruments"].([]interface{})) != 1 {
		t.Fatal(out)
	}
	other := t.TempDir()
	m.setWorkspace(other)
	out = m.localApps(map[string]interface{}{"instruments": []interface{}{}}, "")
	if len(out["instruments"].([]interface{})) != 0 {
		t.Fatal("old workspace apps leaked", out)
	}
}
func TestMemberTruncatedTaskStreamIsUnknown(t *testing.T) {
	m := testMember(t)
	hub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, `{"type":"event","event":{"type":"text","content":"started"}}`)
	}))
	defer hub.Close()
	m.cfg.Base = hub.URL
	r := m.startTask(map[string]interface{}{"message": "incomplete"})
	id := r["task_id"].(string)
	deadline := time.Now().Add(5 * time.Second)
	for m.task(id)["state"] == "running" && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	if out := m.task(id); out["state"] != "unknown" {
		t.Fatal(out)
	}
}
func TestMemberCancelStopsShellChildren(t *testing.T) {
	m := testMember(t)
	m.cfg.AutoAllow = []string{"shell"}
	root := m.workspace()
	addLocalTask(t, m, "cancel", root)
	done := make(chan map[string]interface{}, 1)
	go func() {
		done <- m.run(job(Command{Member: true, RequestKey: "cancel", TaskID: "cancel", Op: "shell", Cmd: "echo started > started; sleep 30; echo late > late", Timeout: 40}))
	}()
	deadline := time.Now().Add(5 * time.Second)
	for {
		if _, e := os.Stat(filepath.Join(root, "started")); e == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("not started")
		}
		time.Sleep(10 * time.Millisecond)
	}
	m.stopLocalWork()
	select {
	case r := <-done:
		if r["success"] != false {
			t.Fatal(r)
		}
	case <-time.After(4 * time.Second):
		t.Fatal("shell did not stop")
	}
	if _, e := os.Stat(filepath.Join(root, "late")); !os.IsNotExist(e) {
		t.Fatal("child continued", e)
	}
}
