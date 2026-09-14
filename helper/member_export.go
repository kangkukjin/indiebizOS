package main

import (
	"archive/zip"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func (m *MemberRuntime) export(path string) map[string]interface{} {
	if path == "" {
		path = filepath.Join(m.dir, "member-export-"+time.Now().Format("20060102-150405")+".zip")
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return errResult("export", err.Error())
	}
	ok := false
	defer func() {
		file.Close()
		if !ok {
			os.Remove(path)
		}
	}()
	z := zip.NewWriter(file)
	seen := map[string]bool{}
	tx, err := m.store.db.BeginTx(context.Background(), nil)
	if err != nil {
		return errResult("export", err.Error())
	}
	defer tx.Rollback()
	manifest := map[string]interface{}{"version": 1, "format": "indiebiz-member", "tables": map[string]interface{}{}}
	tables := manifest["tables"].(map[string]interface{})
	for _, table := range []string{"conversations", "episodes", "memories", "scripts", "sentences", "hippocampus_examples", "forage", "tasks", "task_events", "member_settings"} {
		rows, e := tx.Query("SELECT * FROM " + table)
		if e != nil {
			return errResult("export", e.Error())
		}
		cols, _ := rows.Columns()
		items := []map[string]interface{}{}
		for rows.Next() {
			values := make([]interface{}, len(cols))
			ptr := make([]interface{}, len(cols))
			for i := range values {
				ptr[i] = &values[i]
			}
			if e = rows.Scan(ptr...); e != nil {
				rows.Close()
				return errResult("export", e.Error())
			}
			item := map[string]interface{}{}
			for i, c := range cols {
				item[c] = values[i]
			}
			if table == "scripts" {
				p, _ := item["path"].(string)
				b, e := os.ReadFile(p)
				if e != nil {
					rows.Close()
					return errResult("export", e.Error())
				}
				name := fmt.Sprintf("programs/%d/%s", len(items), filepath.Base(p))
				seen[name] = true
				w, e := z.Create(name)
				if e != nil {
					rows.Close()
					return errResult("export", e.Error())
				}
				if _, e = w.Write(b); e != nil {
					rows.Close()
					return errResult("export", e.Error())
				}
				item["path"] = name
				var resources []string
				_ = json.Unmarshal([]byte(fmt.Sprint(item["resources"])), &resources)
				archived := []string{}
				for _, resource := range resources {
					if !filepath.IsAbs(resource) {
						resource = filepath.Join(filepath.Dir(p), resource)
					}
					data, e := os.ReadFile(resource)
					if e != nil {
						rows.Close()
						return errResult("export", e.Error())
					}
					relative, e := filepath.Rel(filepath.Dir(p), resource)
					if e != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
						rows.Close()
						return errResult("export", "자원 파일은 프로그램 폴더 안에 있어야 합니다")
					}
					rn := fmt.Sprintf("programs/%d/%s", len(items), filepath.ToSlash(relative))
					if seen[rn] {
						rows.Close()
						return errResult("export", "중복 자원 경로")
					}
					seen[rn] = true
					rw, e := z.Create(rn)
					if e != nil {
						rows.Close()
						return errResult("export", e.Error())
					}
					if _, e = rw.Write(data); e != nil {
						rows.Close()
						return errResult("export", e.Error())
					}
					archived = append(archived, rn)
				}
				item["resources"] = archived
				var deps []string
				_ = json.Unmarshal([]byte(fmt.Sprint(item["dependencies"])), &deps)
				item["dependencies"] = deps
			}
			items = append(items, item)
		}
		if e = rows.Err(); e != nil {
			rows.Close()
			return errResult("export", e.Error())
		}
		rows.Close()
		tables[table] = items
	}
	w, err := z.Create("manifest.json")
	if err == nil {
		err = json.NewEncoder(w).Encode(manifest)
	}
	if err == nil {
		err = z.Close()
	}
	if err == nil {
		err = file.Sync()
	}
	if err != nil {
		return errResult("export", err.Error())
	}
	ok = true
	return map[string]interface{}{"success": true, "path": path}
}
