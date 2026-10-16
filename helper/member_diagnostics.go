package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"runtime"
	"time"
)

// Local diagnostics intentionally exclude paths, commands, contents and credentials.
func (m *MemberRuntime) diagnostics() map[string]interface{} {
	m.mu.Lock()
	online := m.transportOnline
	last := m.lastContact
	m.mu.Unlock()
	var tasks, unknown int
	_ = m.store.db.QueryRow("SELECT count(*) FROM tasks WHERE id!='local-browser'").Scan(&tasks)
	_ = m.store.db.QueryRow("SELECT count(*) FROM tasks WHERE state='unknown'").Scan(&unknown)
	var size int64
	for _, name := range []string{"member.db", "member.db-wal", "member.db-shm"} {
		if info, e := os.Stat(filepath.Join(m.dir, name)); e == nil {
			size += info.Size()
		}
	}
	return map[string]interface{}{"version": memberVersion, "protocol": 2, "os": runtime.GOOS, "arch": runtime.GOARCH, "online": online, "last_contact": last.Unix(), "tasks": tasks, "unknown_tasks": unknown, "database_bytes": size, "screen": m.screenAllowed()}
}
func (m *MemberRuntime) gitDiff(task string) map[string]interface{} {
	root, err := m.taskRoot(task)
	if err != nil {
		return errResult("task", err.Error())
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := backgroundCommandContext(ctx, "git", "-C", root, "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", ".")
	var out bytes.Buffer
	cmd.Stdout = &limitedMemberOutput{target: &out, limit: 1024 * 1024}
	cmd.Stderr = &limitedMemberOutput{target: &out, limit: 1024 * 1024}
	if err = cmd.Run(); err != nil {
		return errResult("git", clip(out.String()))
	}
	return map[string]interface{}{"success": true, "diff": out.String(), "notice": "현재 Git HEAD와 작업 폴더의 차이입니다. 기존 사용자 변경도 포함되며 추적하지 않는 파일은 변경 목록에서 확인하세요."}
}

type limitedMemberOutput struct {
	target *bytes.Buffer
	limit  int
}

func (w *limitedMemberOutput) Write(b []byte) (int, error) {
	n := len(b)
	remaining := w.limit - w.target.Len()
	if remaining > 0 {
		if len(b) > remaining {
			b = b[:remaining]
		}
		_, _ = w.target.Write(b)
	}
	return n, nil
}
