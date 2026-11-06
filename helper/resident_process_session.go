package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"github.com/gorilla/websocket"
	"io"
	"os"
	"sync"
	"time"
)

// Only the helper owns the PTY. A hub restart reconnects to this same process;
// transport failure is never permission to rerun the command or replay stdin.
func processSessionBridge(ctx context.Context, spec terminalSpec) error {
	dir := spec.Cwd
	if dir == "" {
		dir, _ = os.UserHomeDir()
	}
	process, err := startTerminalCommand(dir, spec.Cols, spec.Rows, spec.Command)
	if err != nil {
		return err
	}
	defer process.Close()
	var mu sync.Mutex
	output := []byte{}
	var offset int64
	finished := false
	code := 0
	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		buffer := make([]byte, 16384)
		for {
			n, e := process.Read(buffer)
			mu.Lock()
			output = append(output, buffer[:n]...)
			if len(output) > 1048576 {
				discard := len(output) - 1048576
				output = output[discard:]
				offset += int64(discard)
			}
			mu.Unlock()
			if e != nil {
				break
			}
		}
	}()
	go func() {
		c := process.Wait()
		// ConPTY's output pipe can remain open after the child exits. Drain
		// concurrently and close the terminal if it does not reach EOF itself.
		select {
		case <-readDone:
		case <-time.After(time.Second):
			process.Close()
			<-readDone
		}
		mu.Lock()
		code = c
		finished = true
		mu.Unlock()
	}()
	go func() { <-ctx.Done(); process.Close() }()
	spec.Channel = "process"
	for ctx.Err() == nil {
		conn, e := dialTerminal(ctx, spec)
		if e != nil {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Second):
				continue
			}
		}
		e = processSessionConnection(ctx, conn, spec, process, &mu, &output, &offset, &finished, &code)
		conn.Close()
		if e == nil {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
	return ctx.Err()
}

func processSessionConnection(ctx context.Context, conn *websocket.Conn, spec terminalSpec, process terminalProcess,
	mu *sync.Mutex, output *[]byte, offset *int64, finished *bool, code *int) error {
	conn.SetReadLimit(200000)
	_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := conn.WriteJSON(map[string]string{"key": spec.Config.Key, "installation_id": spec.Config.InstallationID}); err != nil {
		return err
	}
	var ready struct {
		Type   string `json:"type"`
		Cursor int64  `json:"cursor"`
	}
	_ = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	if err := conn.ReadJSON(&ready); err != nil {
		return err
	}
	if ready.Type == "complete" {
		return nil
	}
	if ready.Type != "ready" {
		return fmt.Errorf("process handshake")
	}
	done := make(chan struct{})
	defer close(done)
	acks := make(chan map[string]interface{}, 128)
	readError := make(chan error, 1)
	go func() {
		for {
			var msg struct {
				Type string `json:"type"`
				Data string `json:"data"`
				ID   string `json:"request_id"`
				Cols int    `json:"cols"`
				Rows int    `json:"rows"`
			}
			_ = conn.SetReadDeadline(time.Now().Add(15 * time.Second))
			if err := conn.ReadJSON(&msg); err != nil {
				readError <- err
				return
			}
			n := 0
			var err error
			switch msg.Type {
			case "heartbeat":
				continue
			case "complete":
				readError <- io.EOF
				return
			case "input":
				var data []byte
				data, err = base64.StdEncoding.DecodeString(msg.Data)
				if err == nil && len(data) <= 65536 {
					n, err = process.Write(data)
				} else {
					err = fmt.Errorf("input size")
				}
			case "interrupt":
				n, err = process.Write([]byte{3})
			case "eof":
				n, err = process.Write([]byte{4})
			case "resize":
				if msg.Cols < 2 || msg.Cols > 500 || msg.Rows < 2 || msg.Rows > 300 {
					err = fmt.Errorf("invalid size")
				} else {
					err = process.Resize(msg.Cols, msg.Rows)
				}
			case "cancel":
				err = process.Close()
			default:
				err = fmt.Errorf("unknown process control")
			}
			delivery := "delivered"
			if err != nil {
				delivery = "delivery_unknown"
			}
			ack := map[string]interface{}{"type": "ack", "request_id": msg.ID, "delivery": delivery, "bytes_written": n}
			select {
			case acks <- ack:
			case <-done:
				return
			}
		}
	}()
	ticker := time.NewTicker(30 * time.Millisecond)
	defer ticker.Stop()
	cursor := ready.Cursor
	waitingFinal := false
	send := func(v interface{}) error {
		_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
		return conn.WriteJSON(v)
	}
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case err := <-readError:
			if err == io.EOF {
				return nil
			}
			return err
		case ack := <-acks:
			if err := send(ack); err != nil {
				return err
			}
		case <-ticker.C:
			mu.Lock()
			if cursor < *offset {
				cursor = *offset
			}
			end := *offset + int64(len(*output))
			count := end - cursor
			if count > 16384 {
				count = 16384
			}
			data := append([]byte(nil), (*output)[cursor-*offset:cursor-*offset+count]...)
			terminal, exit := *finished, *code
			mu.Unlock()
			if len(data) > 0 {
				if err := send(map[string]interface{}{"type": "output", "offset": cursor, "data": base64.StdEncoding.EncodeToString(data)}); err != nil {
					return err
				}
				cursor += int64(len(data))
			}
			if terminal && cursor >= end && !waitingFinal {
				if err := send(map[string]interface{}{"type": "exit", "code": exit}); err != nil {
					return err
				}
				waitingFinal = true
			}
		}
	}
}
