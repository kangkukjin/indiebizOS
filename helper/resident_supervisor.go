package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

// The supervisor outlives the worker long enough to reap its process tree. The
// anonymous stdin pipe is a liveness lease: worker crash/exit closes it in the OS.
type residentProcessSpec struct {
	Path  string
	Args  []string
	Dir   string
	Env   []string
	Input []byte
}

func residentProcessMain(path string) int {
	b, e := os.ReadFile(path)
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		return 125
	}
	_ = os.Remove(path)
	var spec residentProcessSpec
	if e = json.Unmarshal(b, &spec); e != nil {
		fmt.Fprintln(os.Stderr, e)
		return 125
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _, _ = io.Copy(io.Discard, os.Stdin); cancel() }()
	child := exec.CommandContext(ctx, spec.Path, spec.Args...)
	child.Dir = spec.Dir
	child.Env = spec.Env
	child.Stdout = os.Stdout
	child.Stderr = os.Stderr
	if len(spec.Input) > 0 {
		reader, writer := io.Pipe()
		child.Stdin = reader
		defer reader.Close()
		go func() { _, _ = writer.Write(spec.Input); _ = writer.Close() }()
	}
	configureResidentProcess(child)
	e = child.Run()
	code := exitCode(e)
	if code < 0 {
		code = 125
	}
	return code
}
func residentSupervise(ctx context.Context, cmd *exec.Cmd, root, jid string) (*exec.Cmd, func(), error) {
	var input []byte
	var e error
	if cmd.Stdin != nil {
		input, e = io.ReadAll(cmd.Stdin)
		if e != nil {
			return nil, nil, e
		}
	}
	path := filepath.Join(root, "spool", "process-"+jid+".json")
	if e = residentSave(path, residentProcessSpec{cmd.Path, cmd.Args[1:], cmd.Dir, cmd.Env, input}); e != nil {
		return nil, nil, e
	}
	executable, e := os.Executable()
	if e != nil {
		return nil, nil, e
	}
	supervisor := exec.CommandContext(ctx, executable, "--resident-process", path)
	lease, e := supervisor.StdinPipe()
	if e != nil {
		return nil, nil, e
	}
	var once sync.Once
	release := func() { once.Do(func() { _ = lease.Close(); _ = os.Remove(path) }) }
	configureResidentDetached(supervisor)
	supervisor.Cancel = func() error { release(); return nil }
	supervisor.WaitDelay = 5 * time.Second
	return supervisor, release, nil
}
