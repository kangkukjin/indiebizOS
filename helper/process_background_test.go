package main

import (
	"bytes"
	"context"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"strings"
	"testing"
	"time"
)

func TestBackgroundCommandChild(t *testing.T) {
	switch os.Getenv("INDIEBIZ_BACKGROUND_TEST") {
	case "output":
		fmt.Fprint(os.Stdout, "한글 output")
		fmt.Fprint(os.Stderr, "diagnostic")
		os.Exit(7)
	case "wait":
		fmt.Fprintln(os.Stdout, "ready")
		time.Sleep(time.Minute)
		os.Exit(0)
	}
}

func TestBackgroundCommandOutputAndCancellation(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := backgroundCommandContext(ctx, os.Args[0], "-test.run=^TestBackgroundCommandChild$")
	cmd.Env = append(os.Environ(), "INDIEBIZ_BACKGROUND_TEST=output")
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err := cmd.Run()
	if exitCode(err) != 7 || stdout.String() != "한글 output" || stderr.String() != "diagnostic" {
		t.Fatalf("output/exit lost: %v stdout=%q stderr=%q", err, &stdout, &stderr)
	}

	childCtx, stop := context.WithCancel(ctx)
	defer stop()
	cmd = backgroundCommandContext(childCtx, os.Args[0], "-test.run=^TestBackgroundCommandChild$")
	cmd.Env = append(os.Environ(), "INDIEBIZ_BACKGROUND_TEST=wait")
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 6)
	if _, err = io.ReadFull(pipe, buf); err != nil || string(buf) != "ready\n" {
		stop()
		_ = cmd.Wait()
		t.Fatalf("child did not start: %q %v", buf, err)
	}
	stop()
	if err = cmd.Wait(); err == nil || cmd.ProcessState == nil || cmd.ProcessState.Success() {
		t.Fatalf("child was not cancelled: %v", err)
	}
}

// These paths run unattended (including the periodic media probe). Guard their
// launch boundary on every OS; the Windows test below checks actual console use.
func TestInternalCommandsUseBackgroundLaunch(t *testing.T) {
	functions := map[string][]string{
		"input.go":                {"runIn", "runOutTimeout"},
		"screen.go":               {"runCapture"},
		"media_session_ffmpeg.go": {"mediaListDevices", "mediaEncoders"},
		"media_install.go":        {"newMediaInstaller"},
		"member_diagnostics.go":   {"gitDiff"},
	}
	for path, names := range functions {
		file, err := parser.ParseFile(token.NewFileSet(), path, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		for _, name := range names {
			found, launches := false, 0
			for _, decl := range file.Decls {
				fn, ok := decl.(*ast.FuncDecl)
				if !ok || fn.Name.Name != name {
					continue
				}
				found = true
				ast.Inspect(fn.Body, func(n ast.Node) bool {
					call, ok := n.(*ast.CallExpr)
					if !ok {
						return true
					}
					if id, ok := call.Fun.(*ast.Ident); ok && id.Name == "backgroundCommandContext" {
						launches++
					}
					if sel, ok := call.Fun.(*ast.SelectorExpr); ok {
						if id, ok := sel.X.(*ast.Ident); ok && id.Name == "exec" && strings.HasPrefix(sel.Sel.Name, "Command") {
							t.Errorf("%s:%s bypasses background launch", path, name)
						}
					}
					return true
				})
			}
			if !found || launches == 0 {
				t.Errorf("%s:%s background launch boundary missing", path, name)
			}
		}
	}
}
