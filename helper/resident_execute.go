package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

type residentHTTPError struct {
	status int
	body   string
}

func (e *residentHTTPError) Error() string { return fmt.Sprintf("HTTP %d: %s", e.status, e.body) }

func residentPost(url string, body interface{}) (map[string]interface{}, error) {
	return residentPostContext(context.Background(), url, body)
}
func residentPostContext(ctx context.Context, url string, body interface{}) (map[string]interface{}, error) {
	b, e := json.Marshal(body)
	if e != nil {
		return nil, e
	}
	req, e := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(b))
	if e != nil {
		return nil, e
	}
	req.Header.Set("Content-Type", "application/json")
	if req.URL.Scheme != "https" && req.URL.Hostname() != "127.0.0.1" && req.URL.Hostname() != "localhost" {
		return nil, fmt.Errorf("HTTPS required")
	}
	res, e := residentHTTP.Do(req)
	if e != nil {
		return nil, e
	}
	defer res.Body.Close()
	data, e := io.ReadAll(io.LimitReader(res.Body, 16*1024*1024))
	if e != nil {
		return nil, e
	}
	if res.StatusCode != 200 {
		return nil, &residentHTTPError{res.StatusCode, string(data)}
	}
	var out map[string]interface{}
	e = json.Unmarshal(data, &out)
	return out, e
}

var residentHTTP = &http.Client{Timeout: 45 * time.Second, CheckRedirect: func(req *http.Request, via []*http.Request) error { return http.ErrUseLastResponse }}

// Each pipe decodes independently; one shared log preserves arrival order.
type residentLog struct {
	r       *residentRuntime
	jid     string
	mu      sync.Mutex
	tail    []byte
	written int
	gap     bool
	failure error
}
type residentLogStream struct {
	log     *residentLog
	pending []byte
}

func (s *residentLogStream) Write(b []byte) (int, error) {
	s.log.mu.Lock()
	defer s.log.mu.Unlock()
	n := len(b)
	s.pending = append(s.pending, b...)
	end := 0
	for end < len(s.pending) && utf8.FullRune(s.pending[end:]) {
		_, size := utf8.DecodeRune(s.pending[end:])
		end += size
	}
	complete := append([]byte(nil), s.pending[:end]...)
	s.pending = append(s.pending[:0], s.pending[end:]...)
	if err := s.log.writeLocked([]byte(strings.ToValidUTF8(string(complete), "�"))); err != nil {
		return 0, err
	}
	return n, nil
}
func (s *residentLogStream) Flush() {
	s.log.mu.Lock()
	defer s.log.mu.Unlock()
	if len(s.pending) > 0 {
		_ = s.log.writeLocked([]byte(strings.ToValidUTF8(string(s.pending), "�")))
		s.pending = nil
	}
}
func (w *residentLog) writeLocked(b []byte) error {
	w.tail = append(w.tail, b...)
	if len(w.tail) > 32768 {
		start := len(w.tail) - 32768
		for start < len(w.tail) && !utf8.RuneStart(w.tail[start]) {
			start++
		}
		w.tail = w.tail[start:]
	}
	for len(b) > 0 {
		size := len(b)
		if size > 16384 {
			size = 16384
			for size > 0 && !utf8.RuneStart(b[size]) {
				size--
			}
		}
		piece := b[:size]
		b = b[size:]
		if w.written >= 16*1024*1024 {
			if !w.gap {
				w.failure = w.r.event(w.jid, "log_gap", map[string]interface{}{"reason": "per_job_log_limit", "limit_bytes": 16 * 1024 * 1024})
				w.gap = true
			}
			continue
		}
		if e := w.r.event(w.jid, "log", map[string]interface{}{"text": string(piece)}); e != nil {
			w.failure = e
			return e
		}
		w.written += size
	}
	return nil
}
func (r *residentRuntime) execute(parent context.Context, j Job) map[string]interface{} {
	var c Command
	var extra struct {
		Op         string            `json:"op"`
		Elevate    bool              `json:"elevate"`
		Resident   bool              `json:"resident"`
		Generation string            `json:"generation"`
		Mode       string            `json:"mode"`
		Env        map[string]string `json:"env"`
		TransferID string            `json:"transfer_id"`
		SHA256     string            `json:"sha256"`
		MAC        string            `json:"mac"`
		Broadcast  string            `json:"broadcast"`
	}
	if json.Unmarshal([]byte(j.Code), &extra) != nil {
		return errResult("invalid_command", "")
	}
	if !extra.Resident || extra.Generation != r.cfg.Generation {
		return errResult("stale_registration", "")
	}
	if residentMachineActive(r.cfg) && !residentMachineOperation(extra.Op) {
		return errResult("requires_user_session", "이 작업은 사용자 세션 헬퍼에서 실행하세요. 무인 관리 서비스는 설치·설정·파일·셸 작업용입니다.")
	}
	// The media envelope (contract §6) carries object-valued fields such as
	// `content` that the generic Command shape does not share; it keeps the
	// same resident/generation gate and parses itself.
	if extra.Op == "media_session" {
		return r.mediaSession(parent, j)
	}
	if json.Unmarshal([]byte(j.Code), &c) != nil {
		return errResult("invalid_command", "")
	}
	if extra.Mode == "observe" && (c.Op != "shell" || c.Timeout < 1 || c.Timeout > 10) {
		return errResult("invalid_observation", "mode:observe requires shell with explicit timeout:1..10")
	}
	if c.Timeout <= 0 {
		c.Timeout = 1800
	}
	if c.Timeout > 86400 {
		return errResult("timeout_too_large", "")
	}
	ctx, cancel := context.WithTimeout(parent, time.Duration(c.Timeout)*time.Second)
	defer cancel()
	if ctx.Err() != nil {
		return map[string]interface{}{"cancelled": true, "error": ctx.Err().Error()}
	}
	c.ctx = ctx
	c.JobID = j.ID
	dir := filepath.Join(r.cfg.DataDir, "workspaces", j.ID)
	if e := os.MkdirAll(dir, 0700); e != nil {
		return errResult("workspace", e.Error())
	}
	if c.Cwd != "" {
		if !filepath.IsAbs(c.Cwd) {
			return errResult("absolute_cwd_required", "")
		}
		dir = c.Cwd
	}
	c.Cwd = dir
	if c.Path != "" && !filepath.IsAbs(c.Path) {
		c.Path = filepath.Join(dir, c.Path)
	}
	switch c.Op {
	case "desktop":
		return r.desktop(ctx, j)
	case "terminal":
		return r.terminal(ctx, j)
	case "shell":
		var cmd *exec.Cmd
		if runtime.GOOS == "windows" {
			if c.Shell == "powershell" || c.Shell == "pwsh" || c.Shell == "ps" {
				cmd = exec.CommandContext(ctx, "powershell", "-NoProfile", "-NonInteractive", "-Command", "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "+c.Cmd)
			} else {
				cmd = exec.CommandContext(ctx, "cmd", "/D", "/S", "/C", "chcp 65001>nul & "+c.Cmd)
			}
		} else {
			cmd = exec.CommandContext(ctx, "/bin/sh", "-c", c.Cmd)
		}
		cmd.Dir = dir
		cmd.Env = os.Environ()
		if runtime.GOOS == "windows" {
			cmd.Env = append(cmd.Env, "PYTHONIOENCODING=utf-8")
		}
		for k, v := range extra.Env {
			if strings.ContainsAny(k, "=\x00") {
				return errResult("invalid_env", "")
			}
			cmd.Env = append(cmd.Env, k+"="+v)
		}
		cmd.Stdin = strings.NewReader(c.Stdin)
		if extra.Elevate && !residentMachineActive(r.cfg) {
			return r.elevated(ctx, j.ID, cmd)
		}
		return r.process(ctx, j.ID, cmd)
	case "info":
		info := doInfo()
		info["resident"] = r.capabilities()
		return info
	case "transfer":
		return r.transfer(ctx, c, extra.TransferID)
	case "update":
		return r.selfUpdate(ctx, c, extra.TransferID, extra.SHA256)
	case "wake":
		mac, e := net.ParseMAC(extra.MAC)
		if e != nil && len(extra.MAC) == 12 {
			mac, e = hex.DecodeString(extra.MAC)
		}
		if e != nil || len(mac) != 6 {
			return errResult("invalid_mac", "")
		}
		ip := net.ParseIP(extra.Broadcast)
		if ip == nil || ip.To4() == nil {
			return errResult("invalid_broadcast", "")
		}
		conn, e := net.DialUDP("udp4", nil, &net.UDPAddr{IP: ip, Port: 9})
		if e != nil {
			return errResult("wake_failed", e.Error())
		}
		defer conn.Close()
		packet := bytes.Repeat([]byte{255}, 6)
		for i := 0; i < 16; i++ {
			packet = append(packet, mac...)
		}
		_, e = conn.Write(packet)
		if e != nil {
			return errResult("wake_failed", e.Error())
		}
		return map[string]interface{}{"state": "signal_sent", "ready": false}
	case "media":
		if c.Volume != nil && (math.IsNaN(*c.Volume) || math.IsInf(*c.Volume, 0) || *c.Volume < 0 || *c.Volume > 100) {
			return errResult("invalid_volume", "volume must be 0..100")
		}
		if c.Action != "play" && c.Action != "" {
			return errResult("unsupported_media_action", "재생 작업 ID를 cancel 하여 중지하세요")
		}
		source := c.Path
		if source == "" {
			source = c.URL
		}
		if source == "" {
			return errResult("media_source_required", "")
		}
		if strings.HasPrefix(source, "-") {
			return errResult("invalid_media_source", "")
		}
		home, _ := os.UserHomeDir()
		mpv, missing := residentSelectMediaPlayer(source, extra.Mode, runtime.GOOS, r.cfg.DataDir, os.Getenv("PATH"), mediaPlayerCandidates(runtime.GOOS, "", home))
		if missing != nil {
			return missing
		}
		var cmd *exec.Cmd
		if mpv != "" {
			args := []string{"--no-config", "--no-terminal"}
			if extra.Mode != "interactive" {
				args = append(args, "--no-video")
			}
			if c.Volume != nil {
				args = append(args, fmt.Sprintf("--volume=%g", *c.Volume))
			}
			args = append(args, "--", source)
			cmd = exec.CommandContext(ctx, mpv, args...)
		} else {
			cmd = exec.CommandContext(ctx, "/usr/bin/afplay", residentAfplayArgs(source, c.Volume)...)
		}
		result := r.process(ctx, j.ID, cmd)
		result["media_source"] = source
		result["player"] = filepath.Base(cmd.Path)
		result["player_path"] = cmd.Path
		if c.Volume != nil {
			result["volume"] = *c.Volume
		}
		return result
	case "read":
		return doRead(c)
	case "write":
		return doWrite(c)
	case "list":
		if c.Path == "" {
			c.Path = dir
		}
		return doList(c)
	case "screen", "click", "move", "type", "key", "scroll", "drag":
		if extra.Mode != "interactive" {
			return errResult("needs_interactive", "")
		}
		if c.Op == "screen" {
			return doScreen(c)
		}
		return doInput(c)
	default:
		return errResult("unsupported_resident_operation", c.Op)
	}
}
func (r *residentRuntime) process(ctx context.Context, jid string, cmd *exec.Cmd) map[string]interface{} {
	workingDir := cmd.Dir
	if !strings.HasSuffix(os.Args[0], ".test") {
		supervised, release, e := residentSupervise(ctx, cmd, r.cfg.DataDir, jid)
		if e != nil {
			return errResult("process_supervisor", e.Error())
		}
		defer release()
		cmd = supervised
	} else {
		configureResidentProcess(cmd)
	}
	log := &residentLog{r: r, jid: jid}
	stdout, stderr := &residentLogStream{log: log}, &residentLogStream{log: log}
	cmd.Stdout = stdout
	cmd.Stderr = stderr
	e := cmd.Run()
	stdout.Flush()
	stderr.Flush()
	result := map[string]interface{}{"exit": exitCode(e), "output": string(log.tail), "log_truncated": log.gap, "cwd": workingDir}
	// ErrWaitDelay means the command exited successfully, but inherited output
	// pipes never closed. Re-running it could duplicate an already running server.
	if errors.Is(e, exec.ErrWaitDelay) && cmd.ProcessState != nil && cmd.ProcessState.Success() {
		result["exit"] = cmd.ProcessState.ExitCode()
		result["output_incomplete"] = true
		result["warning"] = "command exited successfully; inherited output pipes remained open (a background child may still be running). Do not resubmit. Redirect background stdin/stdout/stderr, e.g. nohup command >server.log 2>&1 </dev/null &; verify the process separately."
	} else if ctx.Err() != nil {
		result["cancelled"] = ctx.Err() == context.Canceled
		result["timeout"] = ctx.Err() == context.DeadlineExceeded
		result["error"] = ctx.Err().Error()
	} else if e != nil {
		result["error"] = e.Error()
	}
	if log.failure != nil {
		result["error"] = "log_persistence_failed"
	}
	return result
}

// Public volume is percent; afplay's per-process gain uses 0..1.
func residentAfplayArgs(source string, volume *float64) []string {
	args := []string{}
	if volume != nil {
		args = append(args, "-v", fmt.Sprintf("%g", *volume/100))
	}
	return append(args, source)
}
