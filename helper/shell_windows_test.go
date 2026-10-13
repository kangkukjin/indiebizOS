package main

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestWindowsQuotedCommandEcho(t *testing.T) {
	if os.Getenv("INDIEBIZ_TEST_QUOTED_ECHO") != "1" {
		return
	}
	for i, arg := range os.Args {
		if arg == "--" {
			b, _ := json.Marshal(os.Args[i+1:])
			os.Stdout.Write(b)
			os.Exit(7)
		}
	}
	os.Exit(99)
}

func TestWindowsQuotedCommandLinePreservesArgumentsAndExit(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows cmd parser")
	}
	dir := filepath.Join(t.TempDir(), "한글 tools")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	source, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(source)
	if err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(dir, "quoted echo.exe")
	if err := os.WriteFile(target, data, 0700); err != nil {
		t.Fatal(err)
	}
	script := `"` + target + `" -test.run=^TestWindowsQuotedCommandEcho$ -- "one two" "a&b" "한글 日本語" "100%"`
	for _, mode := range []string{"resident", "portable"} {
		t.Run(mode, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			var cmd *exec.Cmd
			if mode == "resident" {
				cmd = exec.CommandContext(ctx, "cmd", "/D", "/S", "/C", "chcp 65001>nul & "+script)
				configureResidentProcess(cmd)
			} else {
				bin, args := shellFor("cmd", script)
				cmd = exec.CommandContext(ctx, bin, args...)
				configureShellCommand(cmd)
			}
			cmd.Env = append(os.Environ(), "INDIEBIZ_TEST_QUOTED_ECHO=1")
			output, err := cmd.CombinedOutput()
			if exitCode(err) != 7 {
				t.Fatalf("exit=%d err=%v output=%s", exitCode(err), err, output)
			}
			var got []string
			if err := json.Unmarshal(output, &got); err != nil {
				t.Fatalf("%v: %s", err, output)
			}
			if !reflect.DeepEqual(got, []string{"one two", "a&b", "한글 日本語", "100%"}) {
				t.Fatal(got)
			}
		})
	}
}

func TestWindowsCommandLineConfigurationPreservesProcessFlags(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows command line")
	}
	cmd := exec.Command("cmd", "/D", "/S", "/C", `"C:\path space\app.exe" "x y"`)
	configureResidentProcess(cmd)
	// A second configuration (supervisor/elevation) must keep the same command.
	before := cmd.SysProcAttr.CmdLine
	configureResidentDetached(cmd)
	if before == "" || cmd.SysProcAttr.CmdLine != before || !cmd.SysProcAttr.HideWindow {
		t.Fatal(cmd.SysProcAttr)
	}
	if strings.Contains(before, `\"`) {
		t.Fatal(before)
	}
	plain := exec.Command("powershell", "-Command", `Write-Output "x y"`)
	configureResidentProcess(plain)
	if plain.SysProcAttr.CmdLine != "" {
		t.Fatal("non-cmd argv changed")
	}
}
