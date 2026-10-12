//go:build !windows

package main

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestScreenWorkerFramesAndEOFRelease(t *testing.T) {
	released := filepath.Join(t.TempDir(), "released")
	cmd := exec.CommandContext(context.Background(), "/bin/sh", "-c", `while read -r line; do printf '%s\n' '{"image":"/9j/2Q=="}'; done; touch "$1"`, "screen", released)
	worker, err := startScreenCommand(cmd)
	if err != nil {
		t.Fatal(err)
	}
	frame, err := worker.call(screenMessage{Type: "frame"})
	if err != nil || string(frame) != "\xff\xd8\xff\xd9" {
		t.Fatalf("%x %v", frame, err)
	}
	worker.close()
	if _, err := os.Stat(released); err != nil {
		t.Fatalf("EOF cleanup did not run: %v", err)
	}
}

func TestResidentElevatedChild(t *testing.T) {
	if os.Getenv("IB_TEST_ELEVATED") != "1" {
		return
	}
	os.Exit(residentElevatedMain(os.Getenv("IB_TEST_ADDRESS"), strings.Repeat("a", 64)))
}

func TestElevatedLeaseCancellationAndOutput(t *testing.T) {
	for _, disconnect := range []bool{false, true} {
		listener, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		cmd := exec.Command(os.Args[0], "-test.run=^TestResidentElevatedChild$")
		cmd.Env = append(os.Environ(), "IB_TEST_ELEVATED=1", "IB_TEST_ADDRESS="+listener.Addr().String())
		if err := cmd.Start(); err != nil {
			listener.Close()
			t.Fatal(err)
		}
		listener.(*net.TCPListener).SetDeadline(time.Now().Add(5 * time.Second))
		conn, err := listener.Accept()
		listener.Close()
		if err != nil {
			cmd.Process.Kill()
			t.Fatal(err)
		}
		dec := json.NewDecoder(conn)
		var auth map[string]string
		if dec.Decode(&auth) != nil || auth["Token"] != strings.Repeat("a", 64) {
			t.Fatal("missing authentication")
		}
		command := "printf success; exit 7"
		if disconnect {
			command = "printf ready; sleep 60"
		}
		if err := json.NewEncoder(conn).Encode(residentProcessSpec{Path: "/bin/sh", Args: []string{"-c", command}}); err != nil {
			t.Fatal(err)
		}
		conn.SetReadDeadline(time.Now().Add(5 * time.Second))
		var data []byte
		for {
			var msg struct {
				Data []byte
				Exit *int
			}
			if err := dec.Decode(&msg); err != nil {
				t.Fatal(err)
			}
			data = append(data, msg.Data...)
			if disconnect && strings.Contains(string(data), "ready") {
				break
			}
			if msg.Exit != nil {
				if *msg.Exit != 7 || string(data) != "success" {
					t.Fatalf("exit/output %v %s", msg.Exit, data)
				}
				break
			}
		}
		conn.Close()
		done := make(chan error, 1)
		go func() { done <- cmd.Wait() }()
		select {
		case <-done:
		case <-time.After(5 * time.Second):
			cmd.Process.Kill()
			t.Fatal("privileged child outlived owner lease")
		}
	}
}
