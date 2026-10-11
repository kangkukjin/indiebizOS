package main

import (
	"os"
	"path/filepath"
	"testing"
)

func writeFakePlayer(t *testing.T, p string, mode os.FileMode) {
	t.Helper()
	if e := os.MkdirAll(filepath.Dir(p), 0o755); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(p, []byte("#!/bin/sh\n"), mode); e != nil {
		t.Fatal(e)
	}
}

func TestFindMediaPlayerHomeAppBundleWithEmptyPath(t *testing.T) {
	root, home := t.TempDir(), t.TempDir()
	want := filepath.Join(home, "Applications/mpv-dl-0.37.0/mpv.app/Contents/MacOS/mpv")
	writeFakePlayer(t, want, 0o755)
	got, searched := findMediaPlayerIn("darwin", "", mediaPlayerCandidates("darwin", root, home))
	if got != want {
		t.Fatalf("got %q want %q (searched %v)", got, want, searched)
	}
}

func TestFindMediaPlayerPrefersPathThenFixedLocations(t *testing.T) {
	root, home, bin := t.TempDir(), t.TempDir(), t.TempDir()
	brew := filepath.Join(root, "/opt/homebrew/bin/mpv")
	writeFakePlayer(t, brew, 0o755)
	writeFakePlayer(t, filepath.Join(home, "Applications/mpv.app/Contents/MacOS/mpv"), 0o755)
	cands := mediaPlayerCandidates("darwin", root, home)
	if got, _ := findMediaPlayerIn("darwin", "/usr/bin", cands); got != brew {
		t.Fatalf("fixed location: got %q want %q", got, brew)
	}
	onPath := filepath.Join(bin, "mpv")
	writeFakePlayer(t, onPath, 0o755)
	if got, searched := findMediaPlayerIn("darwin", bin, cands); got != onPath || searched[0] != onPath {
		t.Fatalf("PATH first: got %q searched %v", got, searched)
	}
}

func TestFindMediaPlayerRejectsNonExecutableAndReportsSearch(t *testing.T) {
	root, home := t.TempDir(), t.TempDir()
	writeFakePlayer(t, filepath.Join(home, "Applications/mpv.app/Contents/MacOS/mpv"), 0o644)
	if e := os.MkdirAll(filepath.Join(root, "/usr/local/bin/mpv"), 0o755); e != nil {
		t.Fatal(e)
	}
	got, searched := findMediaPlayerIn("darwin", "", mediaPlayerCandidates("darwin", root, home))
	if got != "" {
		t.Fatalf("non-executable/dir accepted: %q", got)
	}
	if len(searched) < 6 {
		t.Fatalf("search trail too short: %v", searched)
	}
}

func TestResidentMediaWithoutPlayerReportsSearch(t *testing.T) {
	root, home := t.TempDir(), t.TempDir()
	_, res := residentSelectMediaPlayer("https://example.com/stream", "background", "darwin", "", mediaPlayerCandidates("darwin", root, home))
	if res == nil || res["error"] != "needs_media_player" {
		t.Fatalf("want needs_media_player, got %v", res)
	}
	if s, _ := res["searched"].([]string); len(s) == 0 {
		t.Fatalf("missing search trail: %v", res)
	}
	mpv, local := residentSelectMediaPlayer("/tmp/a.mp3", "background", "darwin", "", mediaPlayerCandidates("darwin", root, home))
	if mpv != "" || local != nil {
		t.Fatalf("local darwin audio should fall back to afplay, got %v", local)
	}
}
