package main

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"
)

func TestMemberUpdateBackupIncludesWALAndRefusesOverwrite(t *testing.T) {
	m := testMember(t)
	source := filepath.Join(m.dir, "member.db")
	target := filepath.Join(t.TempDir(), "snapshot.db")
	if _, e := m.store.db.Exec("INSERT INTO memories VALUES('before','committed WAL')"); e != nil {
		t.Fatal(e)
	}
	if e := memberDatabaseBackup(source, target); e != nil {
		t.Fatal(e)
	}
	if e := memberDatabaseBackup(source, target); e == nil {
		t.Fatal("overwrote snapshot")
	}
	db, e := sql.Open("sqlite", target)
	if e != nil {
		t.Fatal(e)
	}
	defer db.Close()
	var value string
	if e = db.QueryRow("SELECT content FROM memories WHERE id='before'").Scan(&value); e != nil || value != "committed WAL" {
		t.Fatal(e, value)
	}
	if stat, e := os.Stat(target); e != nil || stat.Size() == 0 {
		t.Fatal(e)
	}
}

func TestMemberUpdatePauseRejectsNewTask(t *testing.T) {
	m := testMember(t)
	m.maintenance = true
	if r := m.startTask(map[string]interface{}{"message": "new"}); r["error"] != "updating" {
		t.Fatal(r)
	}
	if tasks := m.tasks(); len(tasks) != 0 {
		t.Fatal(tasks)
	}
}
