package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func (m *MemberRuntime) localFile(body map[string]interface{}) map[string]interface{} {
	raw, _ := body["path"].(string)
	op, _ := body["op"].(string)
	content, _ := body["content"].(string)
	if body["encoding"] == "base64" {
		b, e := base64.StdEncoding.DecodeString(content)
		if e != nil {
			return errResult("encoding", e.Error())
		}
		content = string(b)
	}
	id, _ := body["task_id"].(string)
	if op != "read" && op != "write" && op != "list" && op != "resolve" && op != "undo" && op != "diff" {
		return errResult("op", "지원하지 않는 파일 작업")
	}
	if id == "" {
		id = "local-browser"
		_, _ = m.store.db.Exec("INSERT OR REPLACE INTO tasks VALUES(?, '파일 탐색',?,'idle','{}',0,0)", id, m.workspace())
		if e := m.bindTaskRoot(id, m.workspace()); e != nil {
			return errResult("workspace", e.Error())
		}
	}
	if op == "diff" {
		return m.gitDiff(id)
	}
	if op == "undo" {
		change, _ := body["change_id"].(string)
		return m.undoChange(change, id)
	}
	scopeOp := op
	if op == "resolve" {
		scopeOp = "read"
	}
	expected, _ := body["expected_hash"].(string)
	c, err := m.scopeCommand(Command{Op: scopeOp, Path: raw, Content: content, TaskID: id, ExpectedHash: expected})
	if err != nil {
		return errResult("workspace", err.Error())
	}
	switch op {
	case "resolve":
		return map[string]interface{}{"success": true, "path": c.Path}
	case "list":
		return m.execute(c)
	case "read":
		return m.execute(c)
	default:
		return m.safeWrite(c)
	}
}
func (m *MemberRuntime) editFile(c Command) map[string]interface{} {
	if m.cfg.Desktop {
		result, _ := m.desktopFileOp(c)
		return result
	}
	info, e := os.Stat(c.Path)
	if e != nil || !info.Mode().IsRegular() || info.Size() > 32*1024*1024 {
		return errResult("read_limit", "32MB 이하 일반 파일만 편집합니다")
	}
	b, err := os.ReadFile(c.Path)
	if err != nil {
		return errResult("read", err.Error())
	}
	text := string(b)
	n := strings.Count(text, c.OldString)
	if c.OldString == "" || n == 0 || (n > 1 && !c.ReplaceAll) {
		return errResult("match", "old_string은 파일 안에서 고유해야 합니다. 전부 바꾸려면 replace_all을 사용하세요")
	}
	count := 1
	if c.ReplaceAll {
		count = -1
	}
	c.ExpectedHash = memberDigest(b)
	c.Content = strings.Replace(text, c.OldString, c.NewString, count)
	return m.safeWrite(c)
}
func (m *MemberRuntime) findFiles(c Command) map[string]interface{} {
	items := []map[string]interface{}{}
	walked := 0
	truncated := false
	err := filepath.WalkDir(c.Path, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		walked++
		if walked > 20000 || len(items) >= 500 {
			truncated = true
			return filepath.SkipAll
		}
		if d.IsDir() {
			if d.Name() == ".git" || d.Name() == "node_modules" {
				return filepath.SkipDir
			}
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			return nil
		}
		if c.Op == "file_find" {
			ok := c.Pattern == ""
			if !ok {
				ok, _ = filepath.Match(c.Pattern, d.Name())
			}
			if ok {
				items = append(items, map[string]interface{}{"path": path, "name": d.Name()})
			}
			return nil
		}
		info, e := d.Info()
		if e != nil || info.Size() > 2*1024*1024 {
			return nil
		}
		b, e := os.ReadFile(path)
		if e != nil {
			return nil
		}
		for n, line := range strings.Split(string(b), "\n") {
			if strings.Contains(line, c.Pattern) {
				items = append(items, map[string]interface{}{"path": path, "line": n + 1, "text": line})
				if len(items) >= 500 {
					truncated = true
					return filepath.SkipAll
				}
			}
		}
		return nil
	})
	if err != nil {
		return errResult("search", fmt.Sprint(err))
	}
	return map[string]interface{}{"success": true, "items": items, "truncated": truncated}
}

// 회원이 자기 작업 폴더에 작성한 선언형 앱. 실행은 같은 회원 IBL 관문을 지난다.
func (m *MemberRuntime) localApps(remote map[string]interface{}, id string) map[string]interface{} {
	if id == "" {
		id = "local-browser"
		_, _ = m.store.db.Exec("INSERT OR REPLACE INTO tasks VALUES('local-browser','파일 탐색',?,'idle','{}',0,0)", m.workspace())
		if e := m.bindTaskRoot(id, m.workspace()); e != nil {
			remote["local_error"] = e.Error()
			return remote
		}
	}
	c, err := m.scopeCommand(Command{Op: "read", Path: "apps.json", TaskID: id})
	if err != nil {
		return remote
	}
	info, err := os.Stat(c.Path)
	if os.IsNotExist(err) {
		return remote
	}
	if err != nil || info.Size() > 512*1024 {
		remote["local_error"] = "apps.json은 512KB 이하 파일이어야 합니다"
		return remote
	}
	var data []byte
	if m.cfg.Desktop {
		result := m.execute(c)
		content, ok := result["content"].(string)
		if !ok || result["success"] != true {
			remote["local_error"] = "앱 선언을 읽지 못했습니다"
			return remote
		}
		data = []byte(content)
	} else {
		data, err = os.ReadFile(c.Path)
		if err != nil {
			return remote
		}
	}
	if len(data) > 512*1024 {
		remote["local_error"] = "apps.json 크기 제한"
		return remote
	}
	var apps []map[string]interface{}
	if json.Unmarshal(data, &apps) != nil {
		remote["local_error"] = "apps.json은 선언형 앱 배열이어야 합니다"
		return remote
	}
	list, _ := remote["instruments"].([]interface{})
	for _, app := range apps {
		if app["id"] == nil || app["name"] == nil || app["renderer"] != nil {
			continue
		}
		list = append(list, app)
	}
	remote["instruments"] = list
	return remote
}
