package main

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Browser backups are data, never connection credentials or execution permissions.
func (m *MemberRuntime) restoreArchive(body map[string]interface{}) map[string]interface{} {
	if raw, ok := body["zip_base64"].(string); ok {
		return m.restoreNative(raw)
	}
	a, ok := body["archive"].(map[string]interface{})
	if !ok || a["format"] != "indiebiz-member-browser" || a["version"] != float64(1) {
		return errResult("archive", "회원 웹앱 JSON 백업(version 1)이 필요합니다")
	}
	tables, ok := a["tables"].(map[string]interface{})
	if !ok {
		return errResult("archive", "백업 표가 없습니다")
	}
	allowed := map[string]bool{"tasks": true, "jobs": true, "files": true, "conversations": true, "memories": true, "episodes": true, "scripts": true, "sentences": true, "hippocampus_examples": true, "forage": true}
	type importedFile struct {
		path string
		data []byte
		dir  bool
	}
	files := []importedFile{}
	seen := map[string]bool{}
	total := 0
	for table, rows := range tables {
		if !allowed[table] {
			return errResult("archive", "알 수 없는 백업 표")
		}
		values, ok := rows.([]interface{})
		if !ok {
			return errResult("archive", "잘못된 백업 표")
		}
		for _, v := range values {
			row, ok := v.(map[string]interface{})
			if !ok {
				return errResult("archive", "잘못된 백업 기록")
			}
			id, ok := row["id"].(string)
			if !ok || id == "" || len(id) > 512 || seen[table+"\x00"+id] {
				return errResult("archive", "중복되거나 잘못된 ID")
			}
			seen[table+"\x00"+id] = true
			if table == "files" {
				name := strings.ReplaceAll(id, "\\", "/")
				if strings.ContainsAny(name, ":\x00") || strings.HasPrefix(name, "/") {
					return errResult("archive", "잘못된 파일 경로")
				}
				for _, part := range strings.Split(name, "/") {
					if part == ".." {
						return errResult("archive", "작업 폴더 밖의 경로")
					}
				}
				text, _ := row["data"].(string)
				data, e := base64.StdEncoding.DecodeString(text)
				if e != nil {
					return errResult("archive", "파일 인코딩 오류")
				}
				total += len(data)
				if total > 32*1024*1024 {
					return errResult("archive", "백업 파일 합계는 32MB 이하여야 합니다")
				}
				directory, _ := row["directory"].(bool)
				files = append(files, importedFile{name, data, directory})
			}
		}
	}
	root, err := os.MkdirTemp(m.workspace(), "member-import-")
	if err != nil {
		return errResult("archive", err.Error())
	}
	for _, f := range files {
		p := filepath.Join(root, f.path)
		if f.dir {
			err = os.MkdirAll(p, 0700)
		} else {
			err = os.MkdirAll(filepath.Dir(p), 0700)
			if err == nil {
				err = os.WriteFile(p, f.data, 0600)
			}
		}
		if err != nil {
			return errResult("archive", err.Error())
		}
	}
	raw, _ := json.Marshal(a)
	if err = os.WriteFile(filepath.Join(root, "browser-backup.json"), raw, 0600); err != nil {
		return errResult("archive", err.Error())
	}
	prefix := randomToken()[:12] + "-"
	tx, err := m.store.db.Begin()
	if err != nil {
		return errResult("archive", err.Error())
	}
	defer tx.Rollback()
	count := 0
	for table, rows := range tables {
		for _, v := range rows.([]interface{}) {
			row := v.(map[string]interface{})
			id := prefix + row["id"].(string)
			switch table {
			case "memories":
				_, err = tx.Exec("INSERT INTO memories VALUES(?,?)", id, row["content"])
			case "sentences":
				_, err = tx.Exec("INSERT INTO sentences VALUES(?,?)", id, row["code"])
			case "conversations":
				_, err = tx.Exec("INSERT INTO conversations(id,user,assistant,created) VALUES(?,?,?,?)", id, row["user"], row["assistant"], time.Now().Unix())
			case "episodes", "hippocampus_examples", "forage":
				data, _ := json.Marshal(row)
				_, err = tx.Exec("INSERT INTO "+table+" VALUES(?,?)", id, string(data))
			case "tasks":
				result, _ := json.Marshal(row["result"])
				_, err = tx.Exec("INSERT INTO tasks VALUES(?,?,?,'unknown',?,?,?)", id, row["title"], root, string(result), time.Now().Unix(), time.Now().Unix())
				if events, ok := row["events"].([]interface{}); ok && err == nil {
					for _, e := range events {
						event, ok := e.(map[string]interface{})
						if !ok {
							continue
						}
						data, _ := json.Marshal(event["value"])
						_, err = tx.Exec("INSERT INTO task_events(task_id,kind,content) VALUES(?,?,?)", id, event["kind"], string(data))
						if err != nil {
							break
						}
					}
				}
			default:
				continue
			}
			if err != nil {
				return errResult("archive", err.Error())
			}
			count++
		}
	}
	if err = tx.Commit(); err != nil {
		return errResult("archive", err.Error())
	}
	if err = m.migrateTaskRoots(); err != nil {
		return errResult("archive", err.Error())
	}
	return map[string]interface{}{"success": true, "path": root, "records": count, "files": len(files), "notice": "새 폴더에 보존했습니다. 프로그램과 과거 실행은 자동 등록하거나 재실행하지 않습니다."}
}
