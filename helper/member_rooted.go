//go:build go1.25 && !legacy

package main

import (
	"encoding/base64"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf8"
)

// All desktop file I/O stays on this directory handle, including temp-file rename.
// A path replaced after validation cannot redirect an operation outside the root.
func (m *MemberRuntime) desktopFileOp(c Command) (map[string]interface{}, bool) {
	switch c.Op {
	case "read", "write", "file_edit", "list", "file_find", "grep", "mkdir", "file_move", "undo_new":
	default:
		return nil, false
	}
	fail := func(err error) (map[string]interface{}, bool) { return errResult("workspace", err.Error()), true }
	root, err := m.taskRoot(c.TaskID)
	if err != nil {
		return fail(err)
	}
	before, err := os.Stat(root)
	if err != nil {
		return fail(err)
	}
	r, err := os.OpenRoot(root)
	if err != nil {
		return fail(err)
	}
	defer r.Close()
	handle, err := r.Open(".")
	if err != nil {
		return fail(err)
	}
	identity, err := memberFileIdentity(handle)
	handle.Close()
	if err != nil {
		return fail(err)
	}
	if err = m.checkTaskIdentity(c.TaskID, identity); err != nil {
		return fail(err)
	}
	after, err := r.Stat(".")
	if err != nil {
		return fail(err)
	}
	if !os.SameFile(before, after) {
		return fail(fmt.Errorf("작업 폴더가 교체되었습니다"))
	}
	relative := func(p string) (string, error) {
		if p == "" {
			return ".", nil
		}
		if !filepath.IsAbs(p) {
			return p, nil
		}
		return filepath.Rel(root, p)
	}
	name, err := relative(c.Path)
	if err != nil {
		return fail(err)
	}
	read := func(limit int64) ([]byte, error) {
		f, e := r.Open(name)
		if e != nil {
			return nil, e
		}
		defer f.Close()
		info, e := f.Stat()
		if e != nil {
			return nil, e
		}
		if !info.Mode().IsRegular() || info.Size() > limit {
			return nil, fmt.Errorf("파일 크기 또는 형식 제한")
		}
		b, e := io.ReadAll(io.LimitReader(f, limit+1))
		if int64(len(b)) > limit {
			return nil, fmt.Errorf("파일 크기 제한")
		}
		return b, e
	}
	if c.Op == "read" {
		limit := int64(4 * 1024 * 1024)
		if c.Encoding == "base64" {
			limit = 32 * 1024 * 1024
		}
		b, e := read(limit)
		if e != nil {
			return fail(e)
		}
		content := string(b)
		if c.Encoding == "base64" {
			content = base64.StdEncoding.EncodeToString(b)
		} else if !utf8.Valid(b) {
			return errResult("text_required", "UTF-8 텍스트 파일이 아닙니다"), true
		}
		return map[string]interface{}{"success": true, "op": "read", "path": c.Path, "content": content, "encoding": c.Encoding, "sha256": memberDigest(b)}, true
	}
	if c.Op == "mkdir" {
		if e := r.MkdirAll(name, 0755); e != nil {
			return fail(e)
		}
		return map[string]interface{}{"success": true, "path": c.Path}, true
	}
	if c.Op == "file_move" {
		dest, e := relative(c.Dest)
		if e != nil {
			return fail(e)
		}
		if _, e = r.Lstat(dest); !os.IsNotExist(e) {
			return errResult("exists", "대상 파일이 이미 있거나 확인할 수 없습니다"), true
		}
		if e = r.Rename(name, dest); e != nil {
			return fail(e)
		}
		return map[string]interface{}{"success": true, "path": c.Dest}, true
	}
	if c.Op == "list" {
		f, e := r.Open(name)
		if e != nil {
			return fail(e)
		}
		defer f.Close()
		entries, e := f.ReadDir(-1)
		if e != nil {
			return fail(e)
		}
		items := []map[string]interface{}{}
		for _, entry := range entries {
			info, e := entry.Info()
			if e != nil {
				continue
			}
			items = append(items, map[string]interface{}{"name": entry.Name(), "path": filepath.Join(c.Path, entry.Name()), "dir": entry.IsDir(), "bytes": info.Size(), "mtime": info.ModTime().Format(time.RFC3339)})
		}
		return map[string]interface{}{"success": true, "path": c.Path, "files": items}, true
	}
	if c.Op == "file_find" || c.Op == "grep" {
		items := []map[string]interface{}{}
		walked := 0
		truncated := false
		err = fs.WalkDir(r.FS(), filepath.ToSlash(name), func(p string, d fs.DirEntry, e error) error {
			if e != nil {
				return nil
			}
			walked++
			if walked > 20000 || len(items) >= 500 {
				truncated = true
				return fs.SkipAll
			}
			if d.IsDir() {
				if d.Name() == ".git" || d.Name() == "node_modules" {
					return fs.SkipDir
				}
				return nil
			}
			if d.Type()&os.ModeSymlink != 0 {
				return nil
			}
			if c.Op == "file_find" {
				ok, _ := filepath.Match(c.Pattern, d.Name())
				if ok || c.Pattern == "" {
					items = append(items, map[string]interface{}{"path": filepath.Join(root, p), "name": d.Name()})
				}
				return nil
			}
			name = p
			b, e := func() ([]byte, error) {
				f, e := r.Open(name)
				if e != nil {
					return nil, e
				}
				defer f.Close()
				info, e := f.Stat()
				if e != nil || !info.Mode().IsRegular() || info.Size() > 2*1024*1024 {
					return nil, fmt.Errorf("limit")
				}
				return io.ReadAll(io.LimitReader(f, 2*1024*1024+1))
			}()
			if e != nil || len(b) > 2*1024*1024 {
				return nil
			}
			for n, line := range strings.Split(string(b), "\n") {
				if strings.Contains(line, c.Pattern) {
					items = append(items, map[string]interface{}{"path": filepath.Join(root, p), "line": n + 1, "text": line})
					if len(items) >= 500 {
						truncated = true
						return fs.SkipAll
					}
				}
			}
			return nil
		})
		if err != nil {
			return fail(err)
		}
		return map[string]interface{}{"success": true, "items": items, "truncated": truncated}, true
	}
	m.fileMu.Lock()
	defer m.fileMu.Unlock()
	old, err := read(32 * 1024 * 1024)
	exists := err == nil
	if err != nil && !os.IsNotExist(err) {
		return fail(err)
	}
	content := []byte(c.Content)
	if c.Encoding == "base64" {
		content, err = base64.StdEncoding.DecodeString(c.Content)
		if err != nil {
			return fail(err)
		}
	}
	if c.Op == "file_edit" {
		n := strings.Count(string(old), c.OldString)
		if !exists || c.OldString == "" || n == 0 || (n > 1 && !c.ReplaceAll) {
			return errResult("match", "old_string은 고유해야 합니다. 전체 치환은 replace_all을 사용하세요"), true
		}
		count := 1
		if c.ReplaceAll {
			count = -1
		}
		content = []byte(strings.Replace(string(old), c.OldString, c.NewString, count))
		c.ExpectedHash = memberDigest(old)
	}
	if len(content) > 32*1024*1024 {
		return errResult("size_limit", "32MB 이하 파일만 편집합니다"), true
	}
	if (exists && (c.ExpectedHash == "" || c.ExpectedHash != memberDigest(old))) || (!exists && c.ExpectedHash != "" && c.ExpectedHash != "missing") {
		return errResult("file_changed", "파일을 다시 읽고 해당 sha256으로 저장하세요"), true
	}
	if c.Op == "undo_new" {
		if !exists {
			return errResult("file_changed", "파일이 없습니다"), true
		}
		if err = r.Remove(name); err != nil {
			return fail(err)
		}
		return map[string]interface{}{"success": true, "path": c.Path}, true
	}
	id := randomToken()[:24]
	hash := memberDigest(content)
	present := 0
	if exists {
		present = 1
	}
	if _, err = m.store.db.Exec("INSERT INTO file_changes VALUES(?,?,?,?,?,?,?)", id, c.TaskID, c.Path, old, present, hash, time.Now().Unix()); err != nil {
		return fail(err)
	}
	success := false
	defer func() {
		if !success {
			m.store.db.Exec("DELETE FROM file_changes WHERE id=?", id)
		}
	}()
	if err = r.MkdirAll(filepath.Dir(name), 0755); err != nil {
		return fail(err)
	}
	temp := filepath.Join(filepath.Dir(name), ".indiebiz-write-"+randomToken())
	f, err := r.OpenFile(temp, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return fail(err)
	}
	defer r.Remove(temp)
	if info, e := r.Stat(name); e == nil {
		err = f.Chmod(info.Mode().Perm())
	}
	if err == nil {
		_, err = f.Write(content)
	}
	if err == nil {
		err = f.Sync()
	}
	e := f.Close()
	if err == nil {
		err = e
	}
	if err != nil {
		return fail(err)
	}
	// Re-read before replacing to detect ordinary concurrent edits during preparation.
	current, e := read(32 * 1024 * 1024)
	if (exists && (e != nil || memberDigest(current) != memberDigest(old))) || (!exists && !os.IsNotExist(e)) {
		return errResult("file_changed", "저장 중 파일이 변경되었습니다"), true
	}
	if err = r.Rename(temp, name); err != nil {
		return fail(err)
	}
	success = true
	return map[string]interface{}{"success": true, "op": "write", "path": c.Path, "change_id": id, "sha256": hash, "size": len(content), "bytes": len(content), "saved": true}, true
}
