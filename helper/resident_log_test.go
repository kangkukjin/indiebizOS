package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"unicode/utf8"
)

func readResidentLog(t *testing.T, r *residentRuntime) string {
	t.Helper()
	paths, _ := filepath.Glob(filepath.Join(r.cfg.DataDir, "spool", "events", "*.json"))
	var result strings.Builder
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var e residentEvent
		if err := json.Unmarshal(data, &e); err != nil {
			t.Fatal(err)
		}
		if e.Kind == "log" {
			result.WriteString(e.Payload["text"].(string))
		}
	}
	return result.String()
}
func TestResidentLogUTF8AcrossWritesAndChunkBoundary(t *testing.T) {
	r := residentTestRuntime(t)
	log := &residentLog{r: r, jid: "unicode"}
	stream := &residentLogStream{log: log}
	text := strings.Repeat("a", 16383) + strings.Repeat("한글 日本語 😀", 3000)
	b := []byte(text)
	for _, span := range [][2]int{{0, 16384}, {16384, 16385}, {16385, len(b)}} {
		if n, err := stream.Write(b[span[0]:span[1]]); err != nil || n != span[1]-span[0] {
			t.Fatal(n, err)
		}
	}
	stream.Flush()
	if got := readResidentLog(t, r); got != text {
		t.Fatalf("stream corrupted: got %d bytes, want %d", len(got), len(text))
	}
	if !utf8.Valid(log.tail) || !strings.HasSuffix(text, string(log.tail)) || len(log.tail) > 32768 {
		t.Fatal("invalid tail")
	}
}
func TestResidentLogIndependentPipesAndIncompleteEOF(t *testing.T) {
	r := residentTestRuntime(t)
	log := &residentLog{r: r, jid: "pipes"}
	stdout, stderr := &residentLogStream{log: log}, &residentLogStream{log: log}
	b := []byte("😀")
	stdout.Write(b[:2])
	stderr.Write([]byte("한글"))
	stdout.Write(b[2:])
	stdout.Flush()
	stderr.Flush()
	if got := readResidentLog(t, r); got != "한글😀" {
		t.Fatal(got)
	}
	stdout.Write([]byte{0xe3})
	stdout.Flush()
	if got := readResidentLog(t, r); got != "한글😀�" {
		t.Fatal(got)
	}
}

func TestResidentWindowsShellUnicodeOutputAndExit(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows PowerShell transport")
	}
	r := residentTestRuntime(t)
	job := residentTestJob(t, map[string]interface{}{"op": "shell", "shell": "powershell", "cmd": "[Console]::Write('한글 日本語 😀'); exit 7"})
	got := r.execute(context.Background(), job)
	if got["exit"] != 7 || got["output"] != "한글 日本語 😀" {
		t.Fatal(got)
	}
}
