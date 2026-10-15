package main

import (
	"fmt"
	"os"
	"path/filepath"
)

func workspaceIdentity(root string) (string, error) {
	canonical, e := filepath.EvalSymlinks(root)
	if e != nil {
		return "", e
	}
	if filepath.Clean(canonical) != filepath.Clean(root) {
		return "", fmt.Errorf("작업 폴더가 교체되었습니다. 폴더를 다시 선택하세요")
	}
	file, e := os.Open(root)
	if e != nil {
		return "", e
	}
	defer file.Close()
	info, e := file.Stat()
	if e != nil || !info.IsDir() {
		return "", fmt.Errorf("작업 폴더를 확인하세요")
	}
	return memberFileIdentity(file)
}
func (m *MemberRuntime) bindTaskRoot(id, root string) error {
	var selected, expected string
	_ = m.store.db.QueryRow("SELECT value FROM member_settings WHERE key='workspace'").Scan(&selected)
	if selected == root {
		_ = m.store.db.QueryRow("SELECT value FROM member_settings WHERE key='workspace_identity'").Scan(&expected)
		actual, e := workspaceIdentity(root)
		if e != nil {
			return e
		}
		if actual != expected {
			return fmt.Errorf("선택 폴더가 교체되었습니다. 폴더를 다시 선택하세요")
		}
	}
	root, e := filepath.EvalSymlinks(root)
	if e != nil {
		return e
	}
	identity, e := workspaceIdentity(root)
	if e != nil {
		return e
	}
	tx, e := m.store.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if _, e = tx.Exec("UPDATE tasks SET workspace=? WHERE id=?", root, id); e != nil {
		return e
	}
	if _, e = tx.Exec("INSERT OR REPLACE INTO task_roots VALUES(?,?,?)", id, root, identity); e != nil {
		return e
	}
	return tx.Commit()
}
func (m *MemberRuntime) checkTaskIdentity(id, identity string) error {
	var expected string
	if e := m.store.db.QueryRow("SELECT identity FROM task_roots WHERE task=?", id).Scan(&expected); e != nil {
		return fmt.Errorf("작업 폴더 확인이 필요합니다. 폴더를 다시 선택하고 새 작업을 시작하세요")
	}
	if expected != identity {
		return fmt.Errorf("작업 폴더가 교체되었습니다. 새 작업을 시작하세요")
	}
	return nil
}

// One-time migration pins only unchanged, real directories. Symlink substitution
// in an older DB is rejected; it is never adopted as a new authorization.
func (m *MemberRuntime) migrateTaskRoots() error {
	rows, e := m.store.db.Query("SELECT id,workspace FROM tasks WHERE id NOT IN (SELECT task FROM task_roots)")
	if e != nil {
		return e
	}
	var pairs [][2]string
	for rows.Next() {
		var id, root string
		if e = rows.Scan(&id, &root); e != nil {
			rows.Close()
			return e
		}
		pairs = append(pairs, [2]string{id, root})
	}
	rows.Close()
	for _, pair := range pairs {
		if _, e := workspaceIdentity(pair[1]); e == nil {
			_ = m.bindTaskRoot(pair[0], pair[1])
		}
	}
	return nil
}
