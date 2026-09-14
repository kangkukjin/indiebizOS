package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	_ "modernc.org/sqlite"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type MemberStore struct {
	db *sql.DB
	mu sync.Mutex
}

func openMemberStore(dir string) (*MemberStore, error) {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", filepath.Join(dir, "member.db"))
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	schema := `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
 CREATE TABLE IF NOT EXISTS jobs(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,state TEXT NOT NULL,result TEXT,updated INTEGER);
 CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user TEXT,assistant TEXT,created INTEGER);
 CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,data TEXT);
 CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,content TEXT);
 CREATE TABLE IF NOT EXISTS scripts(id TEXT PRIMARY KEY,path TEXT,interpreter TEXT,description TEXT);
 CREATE TABLE IF NOT EXISTS sentences(id TEXT PRIMARY KEY,code TEXT);
 CREATE TABLE IF NOT EXISTS hippocampus_examples(id TEXT PRIMARY KEY,data TEXT);
 CREATE TABLE IF NOT EXISTS forage(id TEXT PRIMARY KEY,data TEXT);
 UPDATE jobs SET state='unknown' WHERE state='running';`
	if _, err = db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	// 기존 회원 DB에도 자원·의존성 메타를 추가한다.
	_, _ = db.Exec("ALTER TABLE jobs ADD COLUMN command TEXT")
	_, _ = db.Exec("ALTER TABLE scripts ADD COLUMN resources TEXT NOT NULL DEFAULT '[]'")
	_, _ = db.Exec("ALTER TABLE scripts ADD COLUMN dependencies TEXT NOT NULL DEFAULT '[]'")
	return &MemberStore{db: db}, nil
}
func (s *MemberStore) claim(key, fp string) (map[string]interface{}, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var old, state, result string
	err := s.db.QueryRow("SELECT fingerprint,state,coalesce(result,'{}') FROM jobs WHERE key=?", key).Scan(&old, &state, &result)
	if err == nil {
		if old != fp {
			return errResult("key_conflict", "같은 작업 키의 내용이 다릅니다"), false, nil
		}
		out := map[string]interface{}{}
		_ = json.Unmarshal([]byte(result), &out)
		out["state"] = state
		out["request_key"] = key
		if state == "received" {
			return nil, true, nil
		}
		if state != "completed" {
			out["success"] = false
			out["error"] = "result_" + state
		}
		return out, false, nil
	}
	if err != sql.ErrNoRows {
		return nil, false, err
	}
	_, err = s.db.Exec("INSERT INTO jobs(key,fingerprint,state,result,updated) VALUES(?,?,'received',NULL,?)", key, fp, time.Now().Unix())
	return nil, err == nil, err
}
func (s *MemberStore) running(key string) error {
	r, err := s.db.Exec("UPDATE jobs SET state='running',updated=? WHERE key=? AND state='received'", time.Now().Unix(), key)
	if err != nil {
		return err
	}
	n, err := r.RowsAffected()
	if err == nil && n != 1 {
		return fmt.Errorf("작업이 이미 실행 중이거나 결과 불명입니다")
	}
	return err
}
func (s *MemberStore) complete(key string, out map[string]interface{}) error {
	b, err := json.Marshal(out)
	if err != nil {
		return err
	}
	_, err = s.db.Exec("UPDATE jobs SET state='completed',result=?,updated=? WHERE key=?", string(b), time.Now().Unix(), key)
	return err
}
func (s *MemberStore) query(key string) map[string]interface{} {
	var state, result string
	if err := s.db.QueryRow("SELECT state,coalesce(result,'{}') FROM jobs WHERE key=?", key).Scan(&state, &result); err != nil {
		return errResult("not_found", "기록이 없습니다")
	}
	out := map[string]interface{}{}
	_ = json.Unmarshal([]byte(result), &out)
	out["state"] = state
	out["request_key"] = key
	if state != "completed" {
		out["success"] = false
		out["error"] = "result_" + state
	}
	return out
}
func (s *MemberStore) save(record map[string]interface{}) map[string]interface{} {
	id, _ := record["id"].(string)
	if id == "" {
		return errResult("id_required", "기억 ID가 필요합니다")
	}
	tx, err := s.db.Begin()
	if err != nil {
		return errResult("storage", err.Error())
	}
	defer tx.Rollback()
	if content, ok := record["content"].(string); ok {
		_, err = tx.Exec("INSERT OR REPLACE INTO memories VALUES(?,?)", id, content)
	} else {
		_, err = tx.Exec("INSERT OR IGNORE INTO conversations(id,user,assistant,created) VALUES(?,?,?,?)", id, record["user"], record["assistant"], time.Now().Unix())
		if err == nil {
			var b []byte
			b, err = json.Marshal(record["episode"])
			if err == nil {
				_, err = tx.Exec("INSERT OR IGNORE INTO episodes VALUES(?,?)", id, string(b))
			}
		}
	}
	if err != nil {
		return errResult("storage", err.Error())
	}
	if err = tx.Commit(); err != nil {
		return errResult("storage", err.Error())
	}
	return map[string]interface{}{"success": true, "saved": true, "id": id}
}
func (s *MemberStore) recall(query string, limit int) map[string]interface{} {
	if limit < 1 || limit > 100 {
		limit = 40
	}
	history := []map[string]interface{}{}
	memories := []map[string]interface{}{}
	rows, err := s.db.Query("SELECT user,assistant FROM (SELECT rowid,user,assistant FROM conversations ORDER BY rowid DESC LIMIT ?) ORDER BY rowid", limit)
	if err != nil {
		return errResult("storage", err.Error())
	}
	for rows.Next() {
		var u, a string
		if rows.Scan(&u, &a) == nil {
			history = append(history, map[string]interface{}{"role": "user", "content": u}, map[string]interface{}{"role": "assistant", "content": a})
		}
	}
	rows.Close()
	rows, err = s.db.Query("SELECT id,content FROM memories WHERE instr(content,?)>0 OR ?='' LIMIT ?", query, query, limit)
	if err == nil {
		for rows.Next() {
			var id, c string
			if rows.Scan(&id, &c) == nil {
				memories = append(memories, map[string]interface{}{"id": id, "content": c})
			}
		}
		rows.Close()
	}
	sentences := []map[string]interface{}{}
	rows, err = s.db.Query("SELECT id,code FROM sentences ORDER BY id LIMIT 100")
	if err == nil {
		for rows.Next() {
			var id, code string
			if rows.Scan(&id, &code) == nil {
				sentences = append(sentences, map[string]interface{}{"id": id, "code": code})
			}
		}
		rows.Close()
	}
	return map[string]interface{}{"success": true, "history": history, "memories": memories, "sentences": sentences, "recent_results": s.pendingResults()}
}
func (s *MemberStore) pendingResults() []map[string]interface{} {
	rows, err := s.db.Query("SELECT key,state,coalesce(result,'{}'),coalesce(command,'{}') FROM jobs WHERE state IN ('unknown','completed') ORDER BY updated DESC LIMIT 40")
	if err != nil {
		return nil
	}
	defer rows.Close()
	out := []map[string]interface{}{}
	for rows.Next() {
		var k, st, r, cmd string
		if rows.Scan(&k, &st, &r, &cmd) == nil {
			out = append(out, map[string]interface{}{"key": k, "state": st, "result": json.RawMessage(r), "command": json.RawMessage(cmd)})
		}
	}
	return out
}
func (s *MemberStore) scripts() map[string]interface{} {
	rows, err := s.db.Query("SELECT id,path,interpreter,description FROM scripts ORDER BY id")
	if err != nil {
		return errResult("storage", err.Error())
	}
	defer rows.Close()
	items := []map[string]interface{}{}
	for rows.Next() {
		var id, p, i, d string
		if rows.Scan(&id, &p, &i, &d) == nil {
			items = append(items, map[string]interface{}{"id": id, "path": p, "interpreter": i, "description": d})
		}
	}
	return map[string]interface{}{"items": items}
}
func (s *MemberStore) register(c Command) map[string]interface{} {
	if c.ScriptID == "" || c.Path == "" {
		return errResult("invalid_script", "id와 path가 필요합니다")
	}
	absolute, err := filepath.Abs(c.Path)
	if err != nil {
		return errResult("invalid_script", err.Error())
	}
	c.Path = absolute
	if _, err := os.Stat(c.Path); err != nil {
		return errResult("invalid_script", err.Error())
	}
	if c.Interpreter == "" {
		switch filepath.Ext(c.Path) {
		case ".py":
			c.Interpreter = "python3"
		case ".sh":
			c.Interpreter = "bash"
		case ".js":
			c.Interpreter = "node"
		case ".ibl":
			c.Interpreter = "ibl"
		}
	}
	if c.Interpreter == "ibl" {
		b, err := os.ReadFile(c.Path)
		if err != nil {
			return errResult("read", err.Error())
		}
		_, err = s.db.Exec("INSERT OR REPLACE INTO sentences VALUES(?,?)", c.ScriptID, string(b))
		if err != nil {
			return errResult("storage", err.Error())
		}
		return map[string]interface{}{"success": true, "id": c.ScriptID}
	}
	if c.Interpreter != "python3" && c.Interpreter != "bash" && c.Interpreter != "node" {
		return errResult("interpreter", "python3/bash/node만 지원합니다")
	}
	resources, _ := json.Marshal(c.Resources)
	dependencies, _ := json.Marshal(c.Dependencies)
	_, err = s.db.Exec("INSERT OR REPLACE INTO scripts(id,path,interpreter,description,resources,dependencies) VALUES(?,?,?,?,?,?)", c.ScriptID, c.Path, c.Interpreter, c.Text, string(resources), string(dependencies))
	if err != nil {
		return errResult("storage", err.Error())
	}
	return map[string]interface{}{"success": true, "id": c.ScriptID}
}
func (s *MemberStore) script(c Command) map[string]interface{} {
	var path, interpreter string
	if err := s.db.QueryRow("SELECT path,interpreter FROM scripts WHERE id=?", c.ScriptID).Scan(&path, &interpreter); err != nil {
		return errResult("script_missing", fmt.Sprint(err))
	}
	return runMemberProgramContext(c.ctx, path, interpreter, c.Args, c.Timeout)
}
