package main

import (
	"archive/zip"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"strings"
)

func (m *MemberRuntime) restoreNative(encoded string) map[string]interface{} {
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(data) > 32*1024*1024 {
		return errResult("archive", "ZIP은 32MB 이하여야 합니다")
	}
	z, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return errResult("archive", err.Error())
	}
	contents := map[string][]byte{}
	total := 0
	for _, f := range z.File {
		if f.FileInfo().IsDir() {
			continue
		}
		if len(contents) >= 10000 {
			return errResult("archive", "백업 파일 수 제한")
		}
		name := strings.ReplaceAll(f.Name, "\\", "/")
		if strings.HasPrefix(name, "/") || strings.ContainsAny(name, ":\x00") {
			return errResult("archive", "잘못된 ZIP 경로")
		}
		for _, part := range strings.Split(name, "/") {
			if part == ".." {
				return errResult("archive", "ZIP 경로가 폴더 밖입니다")
			}
		}
		if _, ok := contents[name]; ok {
			return errResult("archive", "중복 ZIP 경로")
		}
		if !f.Mode().IsRegular() {
			return errResult("archive", "일반 파일만 가져올 수 있습니다")
		}
		r, e := f.Open()
		if e != nil {
			return errResult("archive", e.Error())
		}
		b, e := io.ReadAll(io.LimitReader(r, 32*1024*1024+1))
		r.Close()
		total += len(b)
		if e != nil || total > 32*1024*1024 {
			return errResult("archive", "압축 해제 크기 제한")
		}
		contents[name] = b
	}
	var a map[string]interface{}
	if json.Unmarshal(contents["manifest.json"], &a) != nil || a["format"] != "indiebiz-member" || a["version"] != float64(1) {
		return errResult("archive", "지원하지 않는 네이티브 백업")
	}
	tables, ok := a["tables"].(map[string]interface{})
	if !ok {
		return errResult("archive", "잘못된 백업 표")
	}
	// Keep the original manifest as a file. Restore only non-executable local data.
	delete(tables, "member_settings")
	delete(tables, "scripts")
	events, _ := tables["task_events"].([]interface{})
	delete(tables, "task_events")
	if tasks, ok := tables["tasks"].([]interface{}); ok {
		for _, value := range tasks {
			t, ok := value.(map[string]interface{})
			if !ok {
				continue
			}
			list := []interface{}{}
			for _, v := range events {
				e, ok := v.(map[string]interface{})
				if ok && e["task_id"] == t["id"] {
					var content interface{}
					if raw, ok := e["content"].(string); ok {
						_ = json.Unmarshal([]byte(raw), &content)
					}
					list = append(list, map[string]interface{}{"kind": e["kind"], "value": content})
				}
			}
			t["events"] = list
		}
	}
	files := []interface{}{}
	for name, b := range contents {
		files = append(files, map[string]interface{}{"id": name, "data": base64.StdEncoding.EncodeToString(b)})
	}
	tables["files"] = files
	a["format"] = "indiebiz-member-browser"
	return m.restoreArchive(map[string]interface{}{"archive": a})
}
