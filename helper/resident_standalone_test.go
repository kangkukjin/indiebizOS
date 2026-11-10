package main

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// The helper-only baseline (docs/REMOTE_EXECUTION_CONTINUITY_REPAIR_DESIGN_2026_11_11.md, R0):
// a PC with nothing but the helper keeps shell, file round trip, info and cancellation.
// The environment is cut down to the OS's own directories and an empty home so that a
// developer machine's interpreters, virtualenvs or repositories cannot be what makes it pass.
func standaloneEnvironment(t *testing.T) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("POSIX baseline fixture; Windows is covered by the resident acceptance run")
	}
	home := t.TempDir()
	t.Setenv("PATH", "/usr/bin:/bin")
	t.Setenv("HOME", home)
	for _, name := range []string{"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "NODE_PATH", "INDIEBIZ_BASE_PATH", "INDIEBIZ_API_PORT"} {
		t.Setenv(name, "")
		os.Unsetenv(name)
	}
	return home
}

func TestResidentBaselineNeedsOnlyTheOperatingSystem(t *testing.T) {
	home := standaloneEnvironment(t)
	r := residentTestRuntime(t)
	run := func(body map[string]interface{}) map[string]interface{} {
		return r.execute(context.Background(), residentTestJob(t, body))
	}

	shell := run(map[string]interface{}{"op": "shell", "cmd": "printf helper-only"})
	if shell["exit"] != 0 || shell["output"] != "helper-only" {
		t.Fatal(shell)
	}
	// The job saw the reduced environment: nothing was inherited from the machine that built it.
	seen := run(map[string]interface{}{"op": "shell", "cmd": "printf '%s|%s' \"$PATH\" \"$HOME\""})
	if seen["output"] != "/usr/bin:/bin|"+home {
		t.Fatal(seen)
	}

	path := filepath.Join(home, "notes", "round trip.txt")
	if got := run(map[string]interface{}{"op": "write", "path": path, "content": "가나다 abc\n"}); got["error"] != nil || got["bytes"] != len("가나다 abc\n") {
		t.Fatal(got)
	}
	if got := run(map[string]interface{}{"op": "read", "path": path}); got["content"] != "가나다 abc\n" || got["truncated"] != false {
		t.Fatal(got)
	}
	listed := run(map[string]interface{}{"op": "list", "path": filepath.Dir(path)})
	if listed["error"] != nil || !strings.Contains(strings.Join(fileNames(listed), ","), "round trip.txt") {
		t.Fatal(listed)
	}

	info := run(map[string]interface{}{"op": "info"})
	if info["error"] != nil || info["os"] != runtime.GOOS || info["path"] != "/usr/bin:/bin" || info["home"] != home {
		t.Fatal(info)
	}
	capabilities, ok := info["resident"].(map[string]interface{})
	if !ok || capabilities["shell"] != true || capabilities["transfer"] != true {
		t.Fatal(info["resident"])
	}
	// Optional media components are a report, never a gate on the base operations above.
	if _, reported := capabilities["media_components"]; !reported {
		t.Fatal("media components must be reported, present or missing")
	}
	for _, key := range []string{"python", "runtimes", "indiebizos", "backend"} {
		if _, declared := capabilities[key]; declared {
			t.Fatalf("baseline capability must not depend on %s", key)
		}
	}
}

func TestResidentBaselineCancelStopsTheCommand(t *testing.T) {
	home := standaloneEnvironment(t)
	r := residentTestRuntime(t)
	marker := filepath.Join(home, "finished")
	job := residentTestJob(t, map[string]interface{}{"op": "shell", "cmd": "sleep 5; echo done > '" + marker + "'"})
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan map[string]interface{}, 1)
	go func() { done <- r.execute(ctx, job) }()
	time.Sleep(300 * time.Millisecond)
	cancel()
	select {
	case got := <-done:
		if got["cancelled"] != true && got["timeout"] != true {
			t.Fatal(got)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled command kept the job running")
	}
	if _, e := os.Stat(marker); !os.IsNotExist(e) {
		t.Fatal("command completed after cancellation")
	}
}

func fileNames(listed map[string]interface{}) []string {
	var names []string
	switch rows := listed["files"].(type) {
	case []map[string]interface{}:
		for _, row := range rows {
			names = append(names, row["name"].(string))
		}
	case []interface{}:
		for _, row := range rows {
			if m, ok := row.(map[string]interface{}); ok {
				names = append(names, m["name"].(string))
			}
		}
	}
	return names
}

// No base source may reach for a hub port on the target or a development interpreter path.
func TestHelperSourcesDoNotAssumeADevelopmentInstall(t *testing.T) {
	files, e := filepath.Glob("*.go")
	if e != nil {
		t.Fatal(e)
	}
	for _, name := range files {
		if strings.HasSuffix(name, "_test.go") {
			continue
		}
		body, e := os.ReadFile(name)
		if e != nil {
			t.Fatal(e)
		}
		for number, line := range strings.Split(string(body), "\n") {
			code := line
			if i := strings.Index(code, "//"); i >= 0 {
				code = code[:i]
			}
			for _, banned := range []string{"8765", ".venv/", "indiebizOS/backend", "Desktop/AI"} {
				if strings.Contains(code, banned) {
					t.Errorf("%s:%d assumes a development install (%s): %s", name, number+1, banned, strings.TrimSpace(line))
				}
			}
		}
	}
}
