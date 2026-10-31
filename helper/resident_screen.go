package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

type screenMessage struct {
	Type    string  `json:"type"`
	Width   int     `json:"width,omitempty"`
	Quality int     `json:"quality,omitempty"`
	X       float64 `json:"x,omitempty"`
	Y       float64 `json:"y,omitempty"`
	Buttons int     `json:"buttons,omitempty"`
	DX      float64 `json:"dx,omitempty"`
	DY      float64 `json:"dy,omitempty"`
	Code    string  `json:"code,omitempty"`
	Key     string  `json:"key,omitempty"`
	Down    bool    `json:"down"`
	Text    string  `json:"text,omitempty"`
}

type screenWorker struct {
	cmd    *exec.Cmd
	input  io.WriteCloser
	output *bufio.Scanner
}

func startScreenWorker(ctx context.Context, root string) (*screenWorker, error) {
	cmd, err := screenWorkerCommand(ctx, root)
	if err != nil {
		return nil, err
	}
	return startScreenCommand(cmd)
}

func startScreenCommand(cmd *exec.Cmd) (*screenWorker, error) {
	configureResidentDetached(cmd)
	input, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	cmd.Cancel = func() error { return input.Close() }
	cmd.WaitDelay = 2 * time.Second
	output, err := cmd.StdoutPipe()
	if err != nil {
		input.Close()
		return nil, err
	}
	// Commands are private live input; never forward worker stdout/stderr to the job log.
	cmd.Stderr = io.Discard
	if err = cmd.Start(); err != nil {
		input.Close()
		return nil, err
	}
	scanner := bufio.NewScanner(output)
	scanner.Buffer(make([]byte, 65536), 6*1024*1024)
	return &screenWorker{cmd, input, scanner}, nil
}

func (w *screenWorker) call(message screenMessage) ([]byte, error) {
	if err := json.NewEncoder(w.input).Encode(message); err != nil {
		return nil, err
	}
	if !w.output.Scan() {
		return nil, fmt.Errorf("screen worker stopped")
	}
	var result struct {
		Image string `json:"image"`
		Error string `json:"error"`
	}
	if err := json.Unmarshal(w.output.Bytes(), &result); err != nil {
		return nil, err
	}
	if result.Error != "" {
		return nil, fmt.Errorf("%s", result.Error)
	}
	if result.Image == "" {
		return nil, nil
	}
	image, err := base64.StdEncoding.DecodeString(result.Image)
	if err != nil || len(image) > 4*1024*1024 {
		return nil, fmt.Errorf("invalid screen frame")
	}
	return image, nil
}
func (w *screenWorker) close() {
	w.input.Close() // Native workers release every held key/button on EOF.
	done := make(chan struct{})
	go func() { w.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		w.cmd.Process.Kill()
		<-done
	}
}

func (r *residentRuntime) desktopOnce(ctx context.Context, j Job, connection int) map[string]interface{} {
	var command struct {
		ID  string      `json:"screen_id"`
		LAN terminalLAN `json:"lan"`
	}
	if json.Unmarshal([]byte(j.Code), &command) != nil || !residentValidID(command.ID) {
		return errResult("screen_spec", "invalid session")
	}
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	spec := terminalSpec{Config: *r.cfg, ID: command.ID, LAN: command.LAN, Channel: "screen"}
	conn, err := dialTerminal(ctx, spec)
	if err != nil {
		return map[string]interface{}{"error": "screen_connect", "retry": true}
	}
	defer conn.Close()
	conn.SetReadLimit(65536)
	conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	err = conn.WriteJSON(map[string]interface{}{"key": r.cfg.Key, "installation_id": r.cfg.InstallationID, "connection": connection})
	var ready struct {
		Type      string  `json:"type"`
		Reconnect float64 `json:"reconnect_s"`
		Lease     float64 `json:"lease_s"`
	}
	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	if err != nil || conn.ReadJSON(&ready) != nil || ready.Type != "ready" {
		return errResult("screen_auth", "화면 공유 인증 실패")
	}
	worker, err := startScreenWorker(ctx, r.cfg.DataDir)
	if err != nil {
		conn.WriteJSON(map[string]string{"type": "error"})
		return errResult("screen_setup", "원격 PC에서 화면 공유 권한을 설정하세요.")
	}
	defer worker.close()
	finished := make(chan struct{})
	defer close(finished)
	go func() {
		select {
		case <-ctx.Done():
			conn.Close()
			worker.input.Close()
			select {
			case <-finished:
			case <-time.After(2 * time.Second):
				worker.cmd.Process.Kill()
			}
		case <-finished:
		}
	}()
	messages := make(chan screenMessage, 256)
	var remoteClosed atomic.Bool
	samples := make(chan time.Duration, 1)
	go func() {
		defer cancel()
		for {
			var message screenMessage
			conn.SetReadDeadline(time.Now().Add(10 * time.Second))
			if conn.ReadJSON(&message) != nil {
				return
			}
			if message.Type == "close" {
				remoteClosed.Store(true)
				return
			}
			if message.Type == "heartbeat" {
				continue
			}
			select {
			case messages <- message:
			case <-ctx.Done():
				return
			default:
				return
			}
		}
	}()
	// Capture/input never wait behind a slow network frame. Only the latest frame
	// is retained; control messages keep their own ordered path.
	frames := make(chan []byte, 1)
	writerDone := make(chan struct{})
	go func() {
		defer close(writerDone)
		defer cancel()
		for {
			select {
			case <-ctx.Done():
				return
			case frame := <-frames:
				started := time.Now()
				conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
				if conn.WriteMessage(websocket.BinaryMessage, frame) != nil {
					return
				}
				select {
				case samples <- time.Since(started):
				default:
				}
			}
		}
	}()
	defer func() { cancel(); conn.Close(); <-writerDone }()
	quality := screenQuality{}
	var previous []byte
	lastFrame := time.Time{}
	ticker := time.NewTicker(time.Second / 15)
	defer ticker.Stop()
	for {
		var message screenMessage
		select {
		case <-ctx.Done():
			return map[string]interface{}{"closed": true, "retry": !remoteClosed.Load() && ready.Reconnect > 0, "reconnect_s": ready.Reconnect}
		case elapsed := <-samples:
			quality.observe(elapsed)
			ticker.Reset(quality.interval())
			continue
		case message = <-messages:
		case <-ticker.C:
			// Drain an input first when capture and input become ready together.
			select {
			case message = <-messages:
			default:
				message.Type = "frame"
			}
			message.Width, message.Quality = quality.dimensions()
		}
		frame, e := worker.call(message)
		if e != nil {
			return errResult("screen_permissions", "원격 PC에서 화면 공유 권한을 허용하세요.")
		}
		if len(frame) > 0 {
			if bytes.Equal(previous, frame) && time.Since(lastFrame) < 2*time.Second {
				continue
			}
			previous = frame
			lastFrame = time.Now()
			select {
			case frames <- frame:
			default:
				select {
				case <-frames:
				default:
				}
				select {
				case frames <- frame:
				default:
				}
			}
		}
	}
}

// The native worker is also used by the local installation's permission step.
func screenPermissionMain(root string) int {
	if err := prepareScreen(root); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func (r *residentRuntime) desktop(ctx context.Context, j Job) map[string]interface{} {
	var until time.Time
	for connection := 1; ; connection++ {
		started := time.Now()
		result := r.desktopOnce(ctx, j, connection)
		retry, _ := result["retry"].(bool)
		seconds, _ := result["reconnect_s"].(float64)
		delete(result, "retry")
		if ctx.Err() != nil || !retry {
			return result
		}
		if seconds > 0 && (until.IsZero() || time.Since(started) > 5*time.Second) {
			until = time.Now().Add(time.Duration(seconds * float64(time.Second)))
		}
		if until.IsZero() || time.Now().After(until) {
			return result
		}
		select {
		case <-ctx.Done():
			return result
		case <-time.After(500 * time.Millisecond):
		}
	}
}
