package main

import (
	"strings"
	"testing"

	"golang.org/x/sys/windows/registry"
)

func TestResidentRunEntryLifecycle(t *testing.T) {
	// Exercise Unicode/quoting, replacement and removal in an isolated key;
	// never register a test executable to launch at the user's next login.
	path := `Software\IndieBizTest-` + residentID()
	t.Cleanup(func() { _ = registry.DeleteKey(registry.CURRENT_USER, path) })
	exe := `C:\Users\한글 사용자\AppData\Roaming\IndieBiz\indiebiz-helper.exe`
	if err := residentWriteRun(registry.CURRENT_USER, path, "one", exe, false); err != nil {
		t.Fatal(err)
	}
	if err := residentWriteRun(registry.CURRENT_USER, path, "other", exe, false); err != nil {
		t.Fatal(err)
	}
	value, err := residentReadRun(registry.CURRENT_USER, path, "one")
	if err != nil || value != `"`+exe+`"` {
		t.Fatal(value, err)
	}
	cleaner := `C:\Users\한글 사용자\cleanup.exe`
	if err := residentWriteRun(registry.CURRENT_USER, path, "one", cleaner, false); err != nil {
		t.Fatal(err)
	}
	if value, err = residentReadRun(registry.CURRENT_USER, path, "one"); err != nil || value != `"`+cleaner+`"` {
		t.Fatal(value, err)
	}
	for i := 0; i < 2; i++ {
		if err := residentWriteRun(registry.CURRENT_USER, path, "one", "", true); err != nil {
			t.Fatal(err)
		}
	}
	if value, err = residentReadRun(registry.CURRENT_USER, path, "one"); err != nil || value != "" {
		t.Fatal(value, err)
	}
	if value, err = residentReadRun(registry.CURRENT_USER, path, "other"); err != nil || value == "" {
		t.Fatal("another installation was removed", value, err)
	}
	if err := residentWriteRun(registry.CURRENT_USER, path, "one", strings.Repeat("x", 260), false); err == nil {
		t.Fatal("accepted an overlong Run command")
	}
}

func TestResidentWindowsOutputPreservesUTF8(t *testing.T) {
	for _, s := range []string{"", "한글 오류", "Access denied"} {
		if got := residentWindowsOutput([]byte(s)); got != s {
			t.Fatal(got)
		}
	}
}
