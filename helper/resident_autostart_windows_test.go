package main

import (
	"os"
	"os/exec"
	"os/user"
	"strings"
	"testing"
	"unicode/utf16"

	"golang.org/x/sys/windows/registry"
)

func TestResidentExistingLoginTaskReadOnly(t *testing.T) {
	name, exe := os.Getenv("INDIEBIZ_TEST_EXISTING_TASK"), os.Getenv("INDIEBIZ_TEST_EXISTING_EXE")
	if name == "" || exe == "" {
		t.Skip("optional existing-task observation")
	}
	current, err := user.Current()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := exec.Command("schtasks", "/Query", "/TN", name, "/XML").Output()
	if err != nil {
		t.Fatal(err)
	}
	if !residentLoginTaskMatches(residentWindowsOutput(raw), exe, current.Uid, current.Username) {
		t.Fatal("existing login task does not match the installed executable and user")
	}
}

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

func TestResidentWindowsTaskOutputUTF16(t *testing.T) {
	text := `<?xml version="1.0" encoding="UTF-16"?><Task>한글</Task>`
	for _, bom := range []bool{false, true} {
		raw := []byte{}
		if bom {
			raw = append(raw, 0xff, 0xfe)
		}
		for _, unit := range utf16.Encode([]rune(text)) {
			raw = append(raw, byte(unit), byte(unit>>8))
		}
		if got := residentWindowsOutput(raw); got != text {
			t.Fatal(got)
		}
	}
}
