package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type Approval struct {
	Key     string  `json:"key"`
	Command Command `json:"command"`
	answer  chan bool
}
type MemberRuntime struct {
	mediaPending *MemberMedia
	localURL     string
	server       *http.Server
	store        *MemberStore
	cfg          *Config
	dir          string
	execMu       sync.Mutex
	mu           sync.Mutex
	approvals    map[string]*Approval
	token        string
}

var memberRuntime *MemberRuntime

func startMember(cfg *Config) error {
	dir := cfg.DataDir
	if dir == "" {
		home, err := os.UserConfigDir()
		if err != nil {
			return err
		}
		identity := sha256.Sum256([]byte(cfg.Base + "|" + cfg.Key))
		dir = filepath.Join(home, "IndieBizMember", hex.EncodeToString(identity[:8]))
	}
	store, err := openMemberStore(dir)
	if err != nil {
		return err
	}
	memberRuntime = &MemberRuntime{store: store, cfg: cfg, dir: dir, approvals: map[string]*Approval{}, token: randomToken()}
	return memberRuntime.serve()
}
func memberEffect(op string) bool {
	switch op {
	case "read", "list", "info", "memory_recall", "script_list", "result_query":
		return false
	default:
		return true
	}
}
func (m *MemberRuntime) approve(c Command) bool {
	if (c.Op == "media" && c.Action == "status") || !memberEffect(c.Op) || (c.Op == "script" && (c.Action == "list" || c.Action == "")) {
		return true
	}
	// 대화의 로컬 보존은 회원이 채팅을 보내는 행위에 포함된다.
	if c.Op == "memory_save" && c.Record != nil && c.Record["user"] != nil {
		return true
	}
	for _, op := range m.cfg.AutoAllow {
		if op == c.Op {
			return true
		}
	}
	a := &Approval{Key: c.RequestKey, Command: c, answer: make(chan bool, 1)}
	m.mu.Lock()
	m.approvals[a.Key] = a
	m.mu.Unlock()
	defer func() { m.mu.Lock(); delete(m.approvals, a.Key); m.mu.Unlock() }()
	select {
	case ok := <-a.answer:
		return ok
	case <-time.After(120 * time.Second):
		return false
	}
}
func (m *MemberRuntime) run(j Job) map[string]interface{} {
	m.execMu.Lock()
	defer m.execMu.Unlock()
	var c Command
	if err := json.Unmarshal([]byte(j.Code), &c); err != nil {
		return errResult("bad_command", "봉투 파싱 실패")
	}
	if !c.Member || c.RequestKey == "" {
		return errResult("member_envelope_required", "회원 작업 봉투가 필요합니다")
	}
	if c.Op == "result_query" {
		return m.store.query(c.QueryKey)
	}
	b, _ := json.Marshal(c)
	sum := sha256.Sum256(b)
	fp := hex.EncodeToString(sum[:])
	previous, run, err := m.store.claim(c.RequestKey, fp)
	if err != nil {
		return errResult("storage", err.Error())
	}
	if !run {
		return previous
	}
	if _, err = m.store.db.Exec("UPDATE jobs SET command=? WHERE key=?", string(b), c.RequestKey); err != nil {
		return errResult("storage", err.Error())
	}
	var result map[string]interface{}
	if !m.approve(c) {
		result = errResult("permission_denied", "회원이 승인하지 않았습니다")
	} else {
		if err = m.store.running(c.RequestKey); err != nil {
			return errResult("storage", err.Error())
		}
		result = m.execute(c)
	}
	result["request_key"] = c.RequestKey
	if err = m.store.complete(c.RequestKey, result); err != nil {
		return errResult("result_unknown", "실행 뒤 결과 기록 실패 — 자동 재실행 금지")
	}
	return result
}
func (m *MemberRuntime) execute(c Command) map[string]interface{} {
	switch c.Op {
	case "memory_save":
		return m.store.save(c.Record)
	case "memory_recall":
		return m.store.recall(c.Query, c.Limit)
	case "script":
		switch c.Action {
		case "", "list":
			return m.store.scripts()
		case "run":
			return m.store.script(c)
		case "register":
			return m.store.register(c)
		default:
			return errResult("unsupported_op", "회원 프로그램에서는 list/register/run만 지원합니다")
		}
	case "mkdir":
		if err := os.MkdirAll(c.Path, 0755); err != nil {
			return errResult("mkdir_failed", err.Error())
		}
		return map[string]interface{}{"success": true, "path": c.Path}
	case "file_move":
		if c.Path == "" || c.Dest == "" {
			return errResult("path_required", "src와 dest가 필요합니다")
		}
		if _, err := os.Stat(c.Dest); err == nil {
			return errResult("exists", "대상 파일이 이미 있습니다")
		}
		if err := os.Rename(c.Path, c.Dest); err != nil {
			return errResult("move_failed", err.Error())
		}
		return map[string]interface{}{"success": true, "path": c.Dest}
	case "script_list":
		return m.store.scripts()
	case "script_register":
		return m.store.register(c)
	case "script_run":
		return m.store.script(c)
	case "export":
		return m.export(c.Path)
	case "read":
		if c.Encoding == "base64" {
			info, err := os.Stat(c.Path)
			if err != nil || !info.Mode().IsRegular() {
				return errResult("read_failed", "일반 파일을 읽을 수 없습니다")
			}
			if info.Size() > 32*1024*1024 {
				return errResult("size_limit", "파일이 32MB를 넘습니다")
			}
			b, err := os.ReadFile(c.Path)
			if err != nil {
				return errResult("read_failed", err.Error())
			}
			if len(b) > 32*1024*1024 {
				return errResult("size_limit", "파일이 32MB를 넘습니다")
			}
			return map[string]interface{}{"success": true, "content": base64.StdEncoding.EncodeToString(b), "encoding": "base64", "path": c.Path}
		}
		return doRead(c)
	case "write":
		if c.Encoding == "base64" {
			b, err := base64.StdEncoding.DecodeString(c.Content)
			if err != nil {
				return errResult("invalid_base64", err.Error())
			}
			c.Content = string(b)
		}
		return memberWrite(c)
	case "list":
		return doList(c)
	case "shell":
		return doShell(c)
	case "info":
		return doInfo()
	case "screen":
		return doScreen(c)
	case "media":
		return m.media(c)
	case "play", "open":
		return memberOpen(c)
	default:
		return errResult("unknown_op", "회원 헬퍼에서 지원하지 않는 작업입니다: "+c.Op)
	}
}
func memberWrite(c Command) map[string]interface{} {
	if c.Path == "" {
		return errResult("no_path", "경로가 비었습니다")
	}
	dir := filepath.Dir(c.Path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return errResult("write_failed", err.Error())
	}
	f, err := os.CreateTemp(dir, ".indiebiz-write-*")
	if err != nil {
		return errResult("write_failed", err.Error())
	}
	defer os.Remove(f.Name())
	if _, err = f.Write([]byte(c.Content)); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err == nil {
		err = os.Rename(f.Name(), c.Path)
	}
	if err != nil {
		return errResult("write_failed", err.Error())
	}
	return map[string]interface{}{"success": true, "op": "write", "path": c.Path, "bytes": len(c.Content)}
}
func memberOpen(c Command) map[string]interface{} {
	target := c.Path
	if target == "" {
		target = c.URL
	}
	if target == "" || strings.HasPrefix(target, "-") {
		return errResult("target", "열 대상이 없습니다")
	}
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", target)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", target)
	default:
		cmd = exec.Command("xdg-open", target)
	}
	if err := cmd.Run(); err != nil {
		return errResult("open_failed", err.Error())
	}
	return map[string]interface{}{"success": true, "op": c.Op}
}
func runMemberProgram(path, interpreter string, args map[string]interface{}, timeout int) map[string]interface{} {
	if timeout <= 0 || timeout > 300 {
		timeout = 120
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()
	raw, _ := json.Marshal(args)
	cmd := exec.CommandContext(ctx, interpreter, path)
	cmd.Dir = filepath.Dir(path)
	cmd.Stdin = bytes.NewReader(raw)
	out, err := cmd.CombinedOutput()
	result := map[string]interface{}{"success": err == nil, "stdout": clip(string(out)), "exit": exitCode(err)}
	if err != nil {
		result["error"] = fmt.Sprint(err)
	}
	return result
}
