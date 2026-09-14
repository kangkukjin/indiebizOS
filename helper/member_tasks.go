package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func (m *MemberRuntime) initTasks() error {
	_, err := m.store.db.Exec(`CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,workspace TEXT,state TEXT,result TEXT,created INTEGER,updated INTEGER);
 CREATE TABLE IF NOT EXISTS task_events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,kind TEXT,content TEXT);
 CREATE TABLE IF NOT EXISTS member_settings(key TEXT PRIMARY KEY,value TEXT);
 UPDATE tasks SET state='unknown' WHERE state='running';`)
	_, _ = m.store.db.Exec("ALTER TABLE conversations ADD COLUMN task_id TEXT NOT NULL DEFAULT ''")
	return err
}
func (m *MemberRuntime) workspace() string {
	var root string
	_ = m.store.db.QueryRow("SELECT value FROM member_settings WHERE key='workspace'").Scan(&root)
	if root == "" {
		root = filepath.Join(m.dir, "workspace")
		_ = os.MkdirAll(root, 0755)
	}
	if resolved, err := filepath.EvalSymlinks(root); err == nil {
		return resolved
	}
	return root
}
func (m *MemberRuntime) setWorkspace(raw string) map[string]interface{} {
	root, err := filepath.Abs(raw)
	if err != nil {
		return errResult("workspace", "작업 폴더를 확인하세요")
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return errResult("workspace", "존재하는 폴더를 선택하세요")
	}
	info, err := os.Stat(root)
	if err != nil || !info.IsDir() {
		return errResult("workspace", "폴더가 아닙니다")
	}
	_, err = m.store.db.Exec("INSERT OR REPLACE INTO member_settings VALUES('workspace',?)", root)
	if err != nil {
		return errResult("storage", err.Error())
	}
	return map[string]interface{}{"success": true, "workspace": root}
}
func (m *MemberRuntime) taskRoot(id string) (string, error) {
	if id == "" {
		return "", fmt.Errorf("작업 ID가 없습니다")
	}
	var root string
	err := m.store.db.QueryRow("SELECT workspace FROM tasks WHERE id=?", id).Scan(&root)
	if err != nil {
		return "", err
	}
	return filepath.EvalSymlinks(root)
}
func (m *MemberRuntime) taskEvent(id, kind string, value interface{}) {
	b, _ := json.Marshal(value)
	_, _ = m.store.db.Exec("INSERT INTO task_events(task_id,kind,content) VALUES(?,?,?)", id, kind, string(b))
}
func (m *MemberRuntime) tasks() []map[string]interface{} {
	rows, err := m.store.db.Query("SELECT id,title,workspace,state,updated FROM tasks WHERE id!='local-browser' ORDER BY updated DESC LIMIT 100")
	if err != nil {
		return nil
	}
	defer rows.Close()
	out := []map[string]interface{}{}
	for rows.Next() {
		var id, title, root, state string
		var updated int64
		_ = rows.Scan(&id, &title, &root, &state, &updated)
		out = append(out, map[string]interface{}{"id": id, "title": title, "workspace": root, "state": state, "updated": updated})
	}
	return out
}
func (m *MemberRuntime) task(id string) map[string]interface{} {
	var state, result, root, title string
	if err := m.store.db.QueryRow("SELECT state,coalesce(result,'{}'),workspace,title FROM tasks WHERE id=?", id).Scan(&state, &result, &root, &title); err != nil {
		return errResult("not_found", "작업이 없습니다")
	}
	rows, err := m.store.db.Query("SELECT kind,content FROM (SELECT id,kind,content FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT 500) ORDER BY id", id)
	if err != nil {
		return errResult("storage", err.Error())
	}
	defer rows.Close()
	events := []map[string]interface{}{}
	for rows.Next() {
		var kind, raw string
		_ = rows.Scan(&kind, &raw)
		var content interface{}
		_ = json.Unmarshal([]byte(raw), &content)
		events = append(events, map[string]interface{}{"kind": kind, "value": content})
	}
	var value interface{}
	_ = json.Unmarshal([]byte(result), &value)
	return map[string]interface{}{"success": true, "id": id, "title": title, "workspace": root, "state": state, "result": value, "events": events}
}
func (m *MemberRuntime) startTask(body map[string]interface{}) map[string]interface{} {
	message, _ := body["message"].(string)
	code, _ := body["code"].(string)
	id, _ := body["task_id"].(string)
	if strings.TrimSpace(message) == "" && code == "" {
		return errResult("input", "요청을 입력하세요")
	}
	m.taskMu.Lock()
	defer m.taskMu.Unlock()
	if m.runningTask != "" {
		return errResult("busy", "진행 중인 작업을 완료하거나 중단하세요")
	}
	now := time.Now().Unix()
	if id == "" {
		id = randomToken()[:24]
		title := message
		if title == "" {
			title = "앱 실행"
		}
		runes := []rune(title)
		if len(runes) > 60 {
			title = string(runes[:60])
		}
		if _, err := m.store.db.Exec("INSERT INTO tasks VALUES(?,?,?,'idle','{}',?,?)", id, title, m.workspace(), now, now); err != nil {
			return errResult("storage", err.Error())
		}
	}
	if _, err := m.taskRoot(id); err != nil {
		return errResult("task", err.Error())
	}
	r, err := m.store.db.Exec("UPDATE tasks SET state='running',updated=? WHERE id=? AND state!='running'", now, id)
	if err != nil {
		return errResult("storage", err.Error())
	}
	n, _ := r.RowsAffected()
	if n != 1 {
		return errResult("busy", "이미 진행 중인 작업입니다")
	}
	m.runningTask = id
	m.taskEvent(id, "user", message)
	go m.runTask(id, message, code)
	return map[string]interface{}{"success": true, "queued": true, "task_id": id}
}
func (m *MemberRuntime) runTask(id, message, code string) {
	defer func() { m.taskMu.Lock(); m.runningTask = ""; m.taskMu.Unlock() }()
	body := map[string]interface{}{"key": m.cfg.Key, "task_id": id, "message": message}
	if code != "" {
		body["code"] = code
	}
	raw, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST", m.cfg.Base+"/m/run", bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	c := *client
	c.Timeout = 35 * time.Minute
	resp, err := c.Do(req)
	result := map[string]interface{}{"success": false, "error": "연결이 끊겼습니다. 실행 결과를 확인하세요"}
	state := "unknown"
	if err == nil {
		defer resp.Body.Close()
		scan := bufio.NewScanner(resp.Body)
		scan.Buffer(make([]byte, 4096), 8*1024*1024)
		for scan.Scan() {
			var event map[string]interface{}
			if json.Unmarshal(scan.Bytes(), &event) != nil {
				continue
			}
			if event["type"] == "result" {
				if v, ok := event["result"].(map[string]interface{}); ok {
					result = v
					state = "completed"
					if v["success"] != true {
						state = "failed"
					}
				}
			} else if event["type"] == "event" {
				m.taskEvent(id, "progress", event["event"])
			} else if event["error"] != nil {
				result = event
				state = "failed"
			}
		}
	}
	answer := result["response"]
	if answer == nil {
		answer = result["error"]
	}
	m.taskEvent(id, "assistant", answer)
	b, _ := json.Marshal(result)
	_, _ = m.store.db.Exec("UPDATE tasks SET state=?,result=?,updated=? WHERE id=?", state, string(b), time.Now().Unix(), id)
}
func (m *MemberRuntime) recallTask(c Command) map[string]interface{} {
	out := m.store.recall(c.Query, c.Limit)
	if c.TaskID == "" {
		return out
	}
	root, err := m.taskRoot(c.TaskID)
	if err != nil {
		return errResult("task", err.Error())
	}
	rows, err := m.store.db.Query("SELECT user,assistant FROM conversations WHERE task_id=? ORDER BY rowid DESC LIMIT 40", c.TaskID)
	if err != nil {
		return errResult("storage", err.Error())
	}
	defer rows.Close()
	pairs := [][2]string{}
	for rows.Next() {
		var user, assistant string
		_ = rows.Scan(&user, &assistant)
		pairs = append(pairs, [2]string{user, assistant})
	}
	history := []map[string]interface{}{}
	for i := len(pairs) - 1; i >= 0; i-- {
		history = append(history, map[string]interface{}{"role": "user", "content": pairs[i][0]}, map[string]interface{}{"role": "assistant", "content": pairs[i][1]})
	}
	out["history"] = history
	out["workspace"] = root
	out["shell_available"] = true
	return out
}
func (m *MemberRuntime) scopeCommand(c Command) (Command, error) {
	if c.TaskID == "" {
		return c, nil
	} // 기존 회원 채팅 계약 호환
	root, err := m.taskRoot(c.TaskID)
	if err != nil {
		return c, err
	}
	resolve := func(raw string) (string, error) {
		if raw == "" {
			raw = "."
		}
		if !filepath.IsAbs(raw) {
			raw = filepath.Join(root, raw)
		}
		raw = filepath.Clean(raw)
		existing := raw
		tail := []string{}
		for {
			if _, e := os.Lstat(existing); e == nil {
				break
			}
			parent := filepath.Dir(existing)
			if parent == existing {
				return "", fmt.Errorf("경로 확인 실패")
			}
			tail = append(tail, filepath.Base(existing))
			existing = parent
		}
		resolved, e := filepath.EvalSymlinks(existing)
		if e != nil {
			return "", e
		}
		for i := len(tail) - 1; i >= 0; i-- {
			resolved = filepath.Join(resolved, tail[i])
		}
		rel, e := filepath.Rel(root, resolved)
		if e != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			return "", fmt.Errorf("선택한 작업 폴더 밖입니다")
		}
		return resolved, nil
	}
	switch c.Op {
	case "read", "write", "list", "mkdir", "file_move", "file_edit", "file_find", "grep":
		c.Path, err = resolve(c.Path)
		if err != nil {
			return c, err
		}
		if c.Dest != "" {
			c.Dest, err = resolve(c.Dest)
		}
	case "script", "script_register":
		if c.Path != "" {
			c.Path, err = resolve(c.Path)
		}
	case "shell":
		c.Cwd = root
		c.Reset = true
	}
	return c, err
}
