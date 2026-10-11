//go:build !windows

package main

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestTerminalBridgeInteractiveResizeInterruptAndClose(t *testing.T) {
	t.Setenv("SHELL", "/bin/sh")
	output := make(chan []byte, 100)
	connected := make(chan *websocket.Conn, 1)
	errors := make(chan error, 1)
	upgrader := websocket.Upgrader{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		conn, err := upgrader.Upgrade(w, req, nil)
		if err != nil {
			errors <- err
			return
		}
		defer conn.Close()
		var auth map[string]string
		if err = conn.ReadJSON(&auth); err != nil {
			errors <- err
			return
		}
		if auth["key"] != "test-key" {
			errors <- context.Canceled
			return
		}
		if err = conn.WriteJSON(map[string]string{"type": "ready"}); err != nil {
			errors <- err
			return
		}
		connected <- conn
		for {
			_, data, err := conn.ReadMessage()
			if err != nil {
				return
			}
			output <- data
		}
	}))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	finished := make(chan error, 1)
	go func() {
		finished <- terminalBridge(ctx, terminalSpec{Config: Config{Base: server.URL, Key: "test-key"}, ID: strings.Repeat("a", 32), Cols: 80, Rows: 24})
	}()
	var conn *websocket.Conn
	select {
	case conn = <-connected:
	case err := <-errors:
		t.Fatal(err)
	case <-ctx.Done():
		t.Fatal("connect timeout")
	}
	waitFor := func(want string) {
		t.Helper()
		var collected bytes.Buffer
		for !strings.Contains(collected.String(), want) {
			select {
			case data := <-output:
				collected.Write(data)
			case <-ctx.Done():
				t.Fatalf("missing %q: %s", want, collected.String())
			}
		}
	}
	send := func(data string) {
		t.Helper()
		if err := conn.WriteJSON(map[string]interface{}{"type": "input", "data": data}); err != nil {
			t.Fatal(err)
		}
	}
	send("stty -echo; printf '\\101\\102\\103'; export IB_TERM_TEST=kept\r")
	waitFor("ABC")
	send("printf '%s' \"$IB_TERM_TEST\"\r")
	waitFor("kept")
	if err := conn.WriteJSON(map[string]interface{}{"type": "resize", "cols": 101, "rows": 37}); err != nil {
		t.Fatal(err)
	}
	send("stty size\r")
	waitFor("37 101")
	send("sleep 20\r")
	time.Sleep(100 * time.Millisecond)
	send("\x03")
	send("printf '\\111\\116\\124\\105\\122\\122\\125\\120\\124'\r")
	waitFor("INTERRUPT")
	if err := conn.WriteJSON(map[string]string{"type": "close"}); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-finished:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("terminal failed to close")
	}
}
