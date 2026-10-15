package main

import (
	"encoding/base64"
	"encoding/json"
	"path/filepath"
	"strings"
)

// Published app artifacts become actual local files only after integrity and local approval.
func (m *MemberRuntime) receiveArtifacts(task, rid string, result map[string]interface{}) map[string]interface{} {
	artifacts, ok := result["artifacts"].([]interface{})
	if !ok || len(artifacts) == 0 {
		return result
	}
	delivered := []map[string]interface{}{}
	for _, value := range artifacts {
		artifact, ok := value.(map[string]interface{})
		if !ok {
			return errResult("artifact", "잘못된 산출물")
		}
		name, _ := artifact["name"].(string)
		id, _ := artifact["id"].(string)
		encoded, _ := artifact["data"].(string)
		digest, _ := artifact["sha256"].(string)
		size, _ := artifact["size"].(float64)
		data, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil || len(data) > 16*1024*1024 || len(data) != int(size) || memberDigest(data) != digest || name == "" || name == "." || name == ".." || strings.ContainsAny(name, "/\\:\x00") || id == "" {
			return errResult("artifact_integrity", "산출물 파일 지문·이름을 확인하지 못했습니다")
		}
		c := Command{Member: true, TaskID: task, BodySession: bodySession(), RequestKey: rid + ":" + id, Op: "write", Path: filepath.Join("results", rid, name), Content: encoded, Encoding: "base64", ExpectedHash: "missing"}
		raw, _ := json.Marshal(c)
		saved := m.run(Job{ID: "artifact-" + id, Code: string(raw)})
		if saved["success"] != true {
			return saved
		}
		delivered = append(delivered, saved)
		var receipt map[string]interface{}
		_ = postJSON(m.cfg.Base+"/m/receipts", map[string]interface{}{"key": m.cfg.Key, "body_session": bodySession(), "epoch": result["epoch"], "request_id": rid, "artifact_id": id, "sha256": digest, "size": len(data)}, &receipt)
		artifact["path"] = saved["path"]
		artifact["saved"] = true
		delete(artifact, "data")
	}
	result["files"] = delivered
	result["saved"] = true
	result["delivery"] = "delivered"
	return result
}
