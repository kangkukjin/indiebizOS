package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type terminalProcess interface {
	io.ReadWriteCloser
	Resize(int, int) error
	Wait() int
}
type terminalSpec struct {
	Config Config `json:"config"`
	ID     string `json:"terminal_id"`
	Cols   int    `json:"cols"`
	Rows   int    `json:"rows"`
}

// The bridge runs in a separate process. A worker crash closes its stdin lease;
// the bridge then closes the PTY, even when the main helper cannot run defers.
func (r *residentRuntime) terminal(ctx context.Context, j Job) map[string]interface{} {
	var spec terminalSpec
	if err := json.Unmarshal([]byte(j.Code), &spec); err != nil {
		return errResult("terminal_spec", err.Error())
	}
	if !residentValidID(spec.ID) || spec.Cols < 2 || spec.Cols > 500 || spec.Rows < 2 || spec.Rows > 300 {
		return errResult("terminal_spec", "invalid id or dimensions")
	}
	spec.Config = *r.cfg
	path := filepath.Join(r.cfg.DataDir, "spool", "terminal-"+j.ID+".json")
	if err := residentSave(path, spec); err != nil {
		return errResult("terminal_spec", err.Error())
	}
	defer os.Remove(path)
	executable, err := os.Executable()
	if err != nil {
		return errResult("terminal_start", err.Error())
	}
	cmd := exec.CommandContext(ctx, executable, "--resident-terminal", path)
	configureResidentDetached(cmd)
	lease, err := cmd.StdinPipe()
	if err != nil {
		return errResult("terminal_start", err.Error())
	}
	defer lease.Close()
	cmd.Cancel = func() error { return lease.Close() }
	cmd.WaitDelay = 5 * time.Second
	err = cmd.Run()
	result := map[string]interface{}{"exit": exitCode(err), "terminal_id": spec.ID}
	if err != nil {
		result["error"] = err.Error()
	}
	if ctx.Err() != nil {
		result["cancelled"] = true
	}
	return result
}

func residentTerminalMain(path string) int {
	b, err := os.ReadFile(path)
	_ = os.Remove(path)
	if err != nil {
		return 125
	}
	var spec terminalSpec
	if json.Unmarshal(b, &spec) != nil {
		return 125
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _, _ = io.Copy(io.Discard, os.Stdin); cancel() }()
	if err = terminalBridge(ctx, spec); err != nil {
		return 1
	}
	return 0
}

func terminalBridge(ctx context.Context, spec terminalSpec) error {
	u, err := url.Parse(spec.Config.Base)
	if err != nil {
		return err
	}
	if u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost")) {
		return fmt.Errorf("HTTPS required")
	}
	if u.Scheme == "https" {
		u.Scheme = "wss"
	} else {
		u.Scheme = "ws"
	}
	u.Path = strings.TrimRight(u.Path, "/") + "/limb/resident/terminal/" + spec.ID
	dialer := websocket.Dialer{HandshakeTimeout: 10 * time.Second}
	conn, response, err := dialer.DialContext(ctx, u.String(), nil)
	if response != nil && response.Body != nil {
		response.Body.Close()
	}
	if err != nil {
		return err
	}
	defer conn.Close()
	conn.SetReadLimit(128 * 1024)
	_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err = conn.WriteJSON(map[string]string{"key": spec.Config.Key, "installation_id": spec.Config.InstallationID}); err != nil {
		return err
	}
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	var ready struct {
		Type string `json:"type"`
	}
	if err = conn.ReadJSON(&ready); err != nil || ready.Type != "ready" {
		return fmt.Errorf("terminal handshake failed: %v", err)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	process, err := startTerminal(home, spec.Cols, spec.Rows)
	if err != nil {
		_ = conn.WriteMessage(websocket.BinaryMessage, []byte("\r\nTerminal: "+err.Error()+"\r\n"))
		return err
	}
	var once sync.Once
	closeAll := func() { once.Do(func() { conn.Close(); process.Close() }) }
	defer closeAll()
	finished := make(chan struct{})
	defer close(finished)
	go func() {
		select {
		case <-ctx.Done():
			closeAll()
		case <-finished:
		}
	}()
	outputDone := make(chan struct{})
	go func() {
		defer close(outputDone)
		buffer := make([]byte, 16384)
		for {
			n, e := process.Read(buffer)
			if n > 0 {
				_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
				if e = conn.WriteMessage(websocket.BinaryMessage, buffer[:n]); e != nil {
					break
				}
			}
			if e != nil {
				break
			}
		}
		conn.Close()
	}()
	for {
		var message struct {
			Type string `json:"type"`
			Data string `json:"data"`
			Cols int    `json:"cols"`
			Rows int    `json:"rows"`
		}
		_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
		if err = conn.ReadJSON(&message); err != nil {
			break
		}
		switch message.Type {
		case "input":
			_, err = process.Write([]byte(message.Data))
		case "resize":
			if message.Cols < 2 || message.Cols > 500 || message.Rows < 2 || message.Rows > 300 {
				return fmt.Errorf("invalid terminal size")
			}
			err = process.Resize(message.Cols, message.Rows)
		case "close":
			closeAll()
		}
		if err != nil || message.Type == "close" {
			break
		}
	}
	closeAll()
	<-outputDone
	process.Wait()
	return nil
}
