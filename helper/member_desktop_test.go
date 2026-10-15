package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDesktopWriteConflictUndoAndScope(t *testing.T) {
	m := testMember(t)
	m.cfg.Desktop = true
	root := m.workspace()
	addLocalTask(t, m, "task", root)
	c := Command{TaskID: "task", Op: "write", Path: filepath.Join(root, "file.txt"), Content: "first", ExpectedHash: "missing"}
	if r := m.safeWrite(c); r["success"] != true {
		t.Fatal(r)
	}
	if e := os.Chmod(c.Path, 0755); e != nil {
		t.Fatal(e)
	}
	c.Content = "second"
	c.ExpectedHash = memberDigest([]byte("first"))
	r := m.safeWrite(c)
	if r["success"] != true {
		t.Fatal(r)
	}
	info, _ := os.Stat(c.Path)
	if info.Mode().Perm() != 0755 {
		t.Fatal("file mode lost")
	}
	if r := m.safeWrite(c); r["error"] != "file_changed" {
		t.Fatal(r)
	}
	if r := m.undoChange(r["change_id"].(string), "other"); r["error"] == nil {
		t.Fatal("cross task undo", r)
	}
	if out := m.undoChange(r["change_id"].(string), "task"); out["success"] != true {
		t.Fatal(out)
	}
	b, _ := os.ReadFile(c.Path)
	if string(b) != "first" {
		t.Fatal(string(b))
	}
	if out := m.localFile(map[string]interface{}{"op": "resolve", "path": "../private", "task_id": "task"}); out["error"] == nil {
		t.Fatal(out)
	}
}
func TestDesktopEnvelopeSessionTaskAndLease(t *testing.T) {
	m := testMember(t)
	m.cfg.Desktop = true
	m.runningTask = "task"
	setBodySession("now")
	m.contact()
	c := Command{TaskID: "task", BodySession: "now"}
	if !m.desktopValid(c) {
		t.Fatal("valid denied")
	}
	c.BodySession = "old"
	if m.desktopValid(c) {
		t.Fatal("old session accepted")
	}
	c.BodySession = "now"
	c.TaskID = "other"
	if m.desktopValid(c) {
		t.Fatal("other task accepted")
	}
	c.TaskID = "task"
	m.lastContact = time.Now().Add(-91 * time.Second)
	if m.desktopValid(c) {
		t.Fatal("expired lease accepted")
	}
}
func TestDesktopImportNeverRestoresKeysPermissionsOrTraverses(t *testing.T) {
	m := testMember(t)
	var archive map[string]interface{}
	_ = json.Unmarshal([]byte(`{"format":"indiebiz-member-browser","version":1,"tables":{"files":[{"id":"../escape","data":"eA=="}]}}`), &archive)
	if r := m.restoreArchive(map[string]interface{}{"archive": archive}); r["error"] == nil {
		t.Fatal(r)
	}
	_ = json.Unmarshal([]byte(`{"format":"indiebiz-member-browser","version":1,"tables":{"files":[{"id":"good.txt","data":"eA=="}],"memories":[{"id":"one","content":"mine"}]}}`), &archive)
	r := m.restoreArchive(map[string]interface{}{"archive": archive})
	if r["success"] != true {
		t.Fatal(r)
	}
	b, e := os.ReadFile(filepath.Join(r["path"].(string), "good.txt"))
	if e != nil || string(b) != "x" {
		t.Fatal(e, string(b))
	}
	second := m.restoreArchive(map[string]interface{}{"archive": archive})
	if second["path"] == r["path"] {
		t.Fatal("overwrote import")
	}
	archive["tables"].(map[string]interface{})["member_settings"] = []interface{}{}
	if r := m.restoreArchive(map[string]interface{}{"archive": archive}); r["error"] == nil {
		t.Fatal("restored permissions")
	}
}

func TestDesktopArtifactIntegrityAndLocalDelivery(t *testing.T) {
	m := testMember(t)
	m.cfg.Desktop = true
	m.runningTask = "task"
	m.contact()
	setBodySession("artifact-session")
	addLocalTask(t, m, "task", m.workspace())
	makeResult := func(hash string) map[string]interface{} {
		return map[string]interface{}{"success": true, "artifacts": []interface{}{map[string]interface{}{"id": "artifact", "name": "report.txt", "data": "bG9jYWw=", "sha256": hash, "size": float64(5)}}}
	}
	if r := m.receiveArtifacts("task", "request", makeResult("tampered")); r["error"] != "artifact_integrity" {
		t.Fatal(r)
	}
	r := m.receiveArtifacts("task", "request", makeResult(memberDigest([]byte("local"))))
	if r["saved"] != true {
		t.Fatal(r)
	}
	b, err := os.ReadFile(filepath.Join(m.workspace(), "results/request/report.txt"))
	if err != nil || string(b) != "local" {
		t.Fatal(err, string(b))
	}
	r = m.receiveArtifacts("task", "request", makeResult(memberDigest([]byte("local"))))
	if r["saved"] != true {
		t.Fatal("duplicate receipt failed", r)
	}
}
