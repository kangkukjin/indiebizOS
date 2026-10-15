package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"time"
	"unicode/utf8"
)

func memberDigest(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }
func memberRead(c Command) map[string]interface{} {
	info, err := os.Stat(c.Path)
	if err != nil || !info.Mode().IsRegular() || info.Size() > 4*1024*1024 {
		return errResult("read_limit", "텍스트 편집기는 4MB 이하 일반 파일을 읽습니다. 큰 파일은 승인한 명령으로 처리하세요")
	}
	data, err := os.ReadFile(c.Path)
	if err != nil {
		return errResult("read_failed", err.Error())
	}
	if len(data) > 4*1024*1024 || !utf8.Valid(data) {
		return errResult("text_required", "UTF-8 텍스트 전체를 읽을 수 없습니다. 기본 앱에서 열어 확인하세요")
	}
	// Never pair a full-file hash with clipped content: saving that view would truncate the file.
	return map[string]interface{}{"success": true, "op": "read", "path": c.Path, "content": string(data), "sha256": memberDigest(data)}
}

func (m *MemberRuntime) safeWrite(c Command) map[string]interface{} {
	if !m.cfg.Desktop {
		return memberWrite(c)
	}
	m.fileMu.Lock()
	defer m.fileMu.Unlock()
	if info, e := os.Stat(c.Path); e == nil && (!info.Mode().IsRegular() || info.Size() > 32*1024*1024) {
		return errResult("size_limit", "32MB 이하 일반 파일만 편집합니다")
	}
	old, err := os.ReadFile(c.Path)
	exists := err == nil
	if err != nil && !os.IsNotExist(err) {
		return errResult("read", err.Error())
	}
	if len(old) > 32*1024*1024 {
		return errResult("size_limit", "편집 가능한 파일 크기는 32MB입니다")
	}
	if exists && (c.ExpectedHash == "" || c.ExpectedHash != memberDigest(old)) {
		return errResult("file_changed", "파일을 다시 읽은 뒤 해당 sha256으로 저장하세요")
	}
	if !exists && c.ExpectedHash != "" && c.ExpectedHash != "missing" {
		return errResult("file_changed", "파일이 삭제되었습니다")
	}
	id := randomToken()[:24]
	hash := memberDigest([]byte(c.Content))
	present := 0
	if exists {
		present = 1
	}
	if _, err = m.store.db.Exec("INSERT INTO file_changes VALUES(?,?,?,?,?,?,?)", id, c.TaskID, c.Path, old, present, hash, time.Now().Unix()); err != nil {
		return errResult("backup", err.Error())
	}
	result := memberWrite(c)
	if result["success"] == true {
		result["change_id"] = id
		result["sha256"] = hash
		result["saved"] = true
		result["size"] = len(c.Content)
	} else {
		_, _ = m.store.db.Exec("DELETE FROM file_changes WHERE id=?", id)
	}
	return result
}
func (m *MemberRuntime) changes(task string) []map[string]interface{} {
	rows, err := m.store.db.Query("SELECT id,task,path,created FROM file_changes WHERE task=? ORDER BY created DESC LIMIT 100", task)
	if err != nil {
		return nil
	}
	defer rows.Close()
	out := []map[string]interface{}{}
	for rows.Next() {
		var id, t, p string
		var created int64
		_ = rows.Scan(&id, &t, &p, &created)
		out = append(out, map[string]interface{}{"id": id, "task_id": t, "path": p, "created": created})
	}
	return out
}
func (m *MemberRuntime) undoChange(id, task string) map[string]interface{} {
	var path, hash string
	var before []byte
	var existed int
	if err := m.store.db.QueryRow("SELECT path,before,existed,after_hash FROM file_changes WHERE id=? AND task=?", id, task).Scan(&path, &before, &existed, &hash); err != nil {
		return errResult("change", "변경 기록을 찾을 수 없습니다")
	}
	c, err := m.scopeCommand(Command{Op: "write", Path: path, TaskID: task, Content: string(before), ExpectedHash: hash})
	if err != nil {
		return errResult("workspace", err.Error())
	}
	if existed == 1 {
		return m.safeWrite(c)
	}
	m.fileMu.Lock()
	defer m.fileMu.Unlock()
	now, err := os.ReadFile(c.Path)
	if err != nil || memberDigest(now) != hash {
		return errResult("file_changed", "파일이 변경되어 되돌리지 않았습니다")
	}
	if err = os.Remove(c.Path); err != nil {
		return errResult("undo", err.Error())
	}
	return map[string]interface{}{"success": true, "path": c.Path}
}
func (m *MemberRuntime) screenAllowed() bool {
	var v string
	_ = m.store.db.QueryRow("SELECT value FROM member_settings WHERE key='screen'").Scan(&v)
	return v == "true"
}
func (m *MemberRuntime) permissions(body map[string]interface{}) map[string]interface{} {
	v, ok := body["screen"].(bool)
	if !ok {
		return errResult("permission", "화면 권한 값이 필요합니다")
	}
	_, err := m.store.db.Exec("INSERT OR REPLACE INTO member_settings VALUES('screen',?)", fmt.Sprint(v))
	if err != nil {
		return errResult("storage", err.Error())
	}
	if !v {
		m.stopLocalWork()
	}
	return map[string]interface{}{"success": true, "screen": v}
}
