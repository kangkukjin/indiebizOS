package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLaunchAgentRestartsOnlyAbnormalExit(t *testing.T) {
	id := "45e1e7d030124b7afd1cab2078ce887d"
	body := residentLaunchAgentBody("indiebiz-resident-"+id, id, "/Users/a b/Library/Application Support/IndieBiz/r&d/indiebiz-helper")
	for _, want := range []string{
		"<key>RunAtLoad</key><true/>",
		"<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>",
		"<key>" + residentServiceEnv + "</key><string>" + id + "</string>",
		"Application Support/IndieBiz/r&amp;d/indiebiz-helper</string>",
	} {
		if !strings.Contains(body, want) {
			t.Fatalf("plist lacks %q:\n%s", want, body)
		}
	}
}

func TestSystemdUnitRestartsOnFailure(t *testing.T) {
	body := residentSystemdUnitBody("abc", "/home/u/x y/indiebiz-helper")
	for _, want := range []string{"Restart=on-failure\n", "RestartSec=10\n", "Environment=" + residentServiceEnv + "=abc\n", `ExecStart="/home/u/x y/indiebiz-helper"`} {
		if !strings.Contains(body, want) {
			t.Fatalf("unit lacks %q:\n%s", want, body)
		}
	}
}

func TestLaunchdJobPID(t *testing.T) {
	running := "gui/501/indiebiz-resident-x = {\n\tactive count = 1\n\tpath = /p\n\tstate = running\n\n\tprogram = /p/h\n\tpid = 22973\n\timmediate reason = speculative\n}\n"
	if got := launchdJobPID(running); got != 22973 {
		t.Fatalf("pid = %d", got)
	}
	// A loaded but stopped job has no pid line; "last exit pid" style keys must not match.
	if got := launchdJobPID("x = {\n\tstate = not running\n\tlast pid = 7\n\truns = 3\n}\n"); got != 0 {
		t.Fatalf("stopped job pid = %d", got)
	}
}

func TestWriteIfChangedIsIdempotent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "entry")
	if changed, e := residentWriteIfChanged(path, []byte("a")); e != nil || !changed {
		t.Fatal(changed, e)
	}
	if changed, e := residentWriteIfChanged(path, []byte("a")); e != nil || changed {
		t.Fatal(changed, e)
	}
	if changed, e := residentWriteIfChanged(path, []byte("b")); e != nil || !changed {
		t.Fatal(changed, e)
	}
	if b, _ := os.ReadFile(path); string(b) != "b" {
		t.Fatalf("content %q", b)
	}
}

func TestServiceStartedNeedsThisInstallation(t *testing.T) {
	cfg := &Config{InstallationID: "aaaa"}
	t.Setenv(residentServiceEnv, "bbbb")
	if residentServiceStarted(cfg) {
		t.Fatal("another installation's marker accepted")
	}
	t.Setenv(residentServiceEnv, "aaaa")
	if !residentServiceStarted(cfg) {
		t.Fatal("own marker rejected")
	}
	if residentServiceAdopt(cfg) {
		t.Fatal("service-started helper must never hand itself over")
	}
}

func TestMaintainInstallsNothingOutsideAnInstallation(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	cfg := &Config{InstallationID: strings.Repeat("c", 32), DataDir: t.TempDir()}
	if residentServiceMaintain(cfg) {
		t.Fatal("a helper that is not the installed executable asked to exit")
	}
	if entry := residentAutostartEntry(cfg); entry != "" {
		if !strings.HasPrefix(entry, home) {
			t.Fatalf("entry %q escapes the test home", entry)
		}
		if _, e := os.Stat(entry); e == nil {
			t.Fatal("autostart entry was created for a non-installed helper")
		}
	}
}
