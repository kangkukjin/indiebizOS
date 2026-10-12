package main

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"
)

// Elevation is one OS-approved job, not a stored administrator password or daemon.
// The privileged child owns its process group and cancels it when the owner's
// loopback lease closes (including helper crash, cancellation and timeout).
func elevationCommand(exe, address, token string) *exec.Cmd {
	switch runtime.GOOS {
	case "darwin":
		quote := func(s string) string { return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'" }
		command := quote(exe) + " --resident-elevated " + quote(address) + " " + quote(token)
		return exec.Command("osascript", "-e", `do shell script "`+osaEscape(command)+`" with administrator privileges`)
	case "windows":
		return elevatedWindowsCommand(exe, address, token)
	default:
		return exec.Command("pkexec", exe, "--resident-elevated", address, token)
	}
}
func (r *residentRuntime) elevated(ctx context.Context, jid string, cmd *exec.Cmd) map[string]interface{} {
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		return errResult("elevation_start", "관리자 인증을 시작하지 못했습니다.")
	}
	defer listener.Close()
	token := residentID() + residentID()
	exe, e := os.Executable()
	if e != nil {
		return errResult("elevation_start", e.Error())
	}
	admin := elevationCommand(exe, listener.Addr().String(), token)
	if e = admin.Start(); e != nil {
		return errResult("elevation_start", "이 PC에서 관리자 인증 창을 열지 못했습니다.")
	}
	done := make(chan error, 1)
	go func() { done <- admin.Wait() }()
	waitCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	go func() {
		select {
		case <-waitCtx.Done():
		case <-done:
		}
		listener.Close()
	}()
	var conn net.Conn
	for {
		conn, e = listener.Accept()
		if e != nil {
			return errResult("elevation_cancelled", "원격 PC에서 관리자 인증이 완료되지 않았습니다.")
		}
		conn.SetReadDeadline(time.Now().Add(5 * time.Second))
		var auth struct{ Token string }
		if json.NewDecoder(conn).Decode(&auth) == nil && subtle.ConstantTimeCompare([]byte(auth.Token), []byte(token)) == 1 {
			break
		}
		conn.Close()
	}
	defer conn.Close()
	cancel() // No further clients can attach. The accepted socket remains live.
	conn.SetReadDeadline(time.Time{})
	var input []byte
	if cmd.Stdin != nil {
		input, _ = io.ReadAll(cmd.Stdin)
	}
	spec := residentProcessSpec{cmd.Path, cmd.Args[1:], cmd.Dir, cmd.Env, input}
	if e = json.NewEncoder(conn).Encode(spec); e != nil {
		return errResult("elevation_start", e.Error())
	}
	finished := make(chan struct{})
	defer close(finished)
	go func() {
		select {
		case <-ctx.Done():
			conn.Close()
		case <-finished:
		}
	}()
	log := &residentLog{r: r, jid: jid}
	decoder := json.NewDecoder(conn)
	for {
		var m struct {
			Data []byte
			Exit *int
		}
		if e = decoder.Decode(&m); e != nil {
			return map[string]interface{}{"error": "관리자 작업 연결이 종료됐습니다.", "cancelled": ctx.Err() != nil, "output": string(log.tail)}
		}
		if len(m.Data) > 0 {
			if _, e = log.Write(m.Data); e != nil {
				return errResult("elevation_output", e.Error())
			}
		}
		if m.Exit != nil {
			return map[string]interface{}{"exit": *m.Exit, "output": string(log.tail), "elevated": true, "cwd": cmd.Dir}
		}
	}
}

type elevatedOutput struct {
	mu      sync.Mutex
	encoder *json.Encoder
}

func (w *elevatedOutput) Write(b []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	n := len(b)
	for len(b) > 0 {
		size := len(b)
		if size > 16384 {
			size = 16384
		}
		if e := w.encoder.Encode(map[string]interface{}{"Data": b[:size]}); e != nil {
			return 0, e
		}
		b = b[size:]
	}
	return n, nil
}
func residentElevatedMain(address, token string) int {
	host, _, e := net.SplitHostPort(address)
	if e != nil || host != "127.0.0.1" || len(token) != 64 {
		return 125
	}
	conn, e := net.DialTimeout("tcp", address, 5*time.Second)
	if e != nil {
		return 125
	}
	defer conn.Close()
	enc := json.NewEncoder(conn)
	if enc.Encode(map[string]string{"Token": token}) != nil {
		return 125
	}
	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	var spec residentProcessSpec
	dec := json.NewDecoder(io.LimitReader(conn, 1024*1024))
	if dec.Decode(&spec) != nil {
		return 125
	}
	conn.SetReadDeadline(time.Time{})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { io.Copy(io.Discard, conn); cancel() }()
	child := exec.CommandContext(ctx, spec.Path, spec.Args...)
	child.Dir = spec.Dir
	child.Env = spec.Env
	child.Stdin = strings.NewReader(string(spec.Input))
	configureResidentProcess(child)
	output := &elevatedOutput{encoder: enc}
	child.Stdout = output
	child.Stderr = output
	code := exitCode(child.Run())
	if e = enc.Encode(map[string]interface{}{"Exit": code}); e != nil {
		fmt.Fprintln(os.Stderr, "elevated owner disconnected")
	}
	return 0
}
