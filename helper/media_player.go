package main

import (
	"os"
	"path/filepath"
	"strings"
)

// A resident helper starts from launchd / a login task / a systemd user unit and
// inherits a minimal PATH, so exec.LookPath("mpv") misses players that a login
// shell would find (user-folder app bundles, Homebrew on Apple silicon, scoop).
// Search order: PATH, then fixed per-OS install locations, then bounded globs
// for app bundles. Every candidate must be an executable regular file.

// mediaPlayerCandidates lists install locations after PATH. root prefixes the
// system locations ("" in production) so tests never see the host's players.
func mediaPlayerCandidates(goos, root, home string) []string {
	sys := func(p string) string { return filepath.Join(root, p) }
	var c []string
	switch goos {
	case "darwin":
		c = []string{sys("/opt/homebrew/bin/mpv"), sys("/usr/local/bin/mpv"), sys("/opt/local/bin/mpv"),
			sys("/Applications/mpv.app/Contents/MacOS/mpv"), sys("/Applications/*/mpv.app/Contents/MacOS/mpv")}
		if home != "" {
			c = append(c, filepath.Join(home, "Applications/mpv.app/Contents/MacOS/mpv"),
				filepath.Join(home, "Applications/*/mpv.app/Contents/MacOS/mpv"))
		}
	case "windows":
		// winget's shinchiro.mpv installer (v0.41+) installs to "MPV Player".
		c = []string{sys(`C:/Program Files/mpv/mpv.exe`), sys(`C:/Program Files/MPV Player/mpv.exe`),
			sys(`C:/ProgramData/chocolatey/bin/mpv.exe`),
			sys(`C:/Program Files/WinGet/Links/mpv.exe`)}
		if home != "" {
			// winget may leave the portable shinchiro.mpv without a Links shim.
			c = append(c, filepath.Join(home, `scoop/shims/mpv.exe`),
				filepath.Join(home, `AppData/Local/Microsoft/WinGet/Links/mpv.exe`),
				filepath.Join(home, `AppData/Local/Microsoft/WinGet/Packages/shinchiro.mpv_*/mpv.exe`))
		}
	default:
		c = []string{sys("/usr/bin/mpv"), sys("/usr/local/bin/mpv"), sys("/snap/bin/mpv")}
		if home != "" {
			c = append(c, filepath.Join(home, ".local/bin/mpv"))
		}
	}
	return c
}

func isExecutableFile(goos, p string) bool {
	st, e := os.Stat(p)
	if e != nil || !st.Mode().IsRegular() {
		return false
	}
	return goos == "windows" || st.Mode().Perm()&0o111 != 0
}

// findMediaPlayerIn returns the first executable mpv and every location examined
// (the helper data dir bin/, then PATH entries), so a miss can be diagnosed from
// the job result. The installer and capabilities use the same lookup.
func findMediaPlayerIn(goos, dataDir, pathEnv string, candidates []string) (string, []string) {
	name := "mpv"
	if goos == "windows" {
		name = "mpv.exe"
	}
	var searched []string
	if dataDir != "" {
		p := filepath.Join(dataDir, "bin", name)
		searched = append(searched, p)
		if isExecutableFile(goos, p) {
			return p, searched
		}
	}
	for _, dir := range filepath.SplitList(pathEnv) {
		if dir == "" || !filepath.IsAbs(dir) {
			continue
		}
		p := filepath.Join(dir, name)
		searched = append(searched, p)
		if isExecutableFile(goos, p) {
			return p, searched
		}
	}
	for _, c := range candidates {
		searched = append(searched, c)
		matches, _ := filepath.Glob(c)
		for _, p := range matches {
			if isExecutableFile(goos, p) {
				return p, searched
			}
		}
	}
	return "", searched
}

// residentSelectMediaPlayer picks mpv, or afplay ("" and nil) for local macOS
// audio, or returns needs_media_player with the locations examined.
func residentSelectMediaPlayer(source, mode, goos, dataDir, pathEnv string, candidates []string) (string, map[string]interface{}) {
	mpv, searched := findMediaPlayerIn(goos, dataDir, pathEnv, candidates)
	if mpv != "" {
		return mpv, nil
	}
	if goos == "darwin" && mode != "interactive" && !strings.Contains(source, "://") {
		return "", nil
	}
	res := errResult("needs_media_player", "mpv 설치 및 로그인한 사용자의 오디오 세션이 필요합니다")
	res["searched"] = searched
	return "", res
}

// mediaPlayerEnv 는 재생기와 같은 폴더를 PATH 앞에 둔 환경을 돌려준다. 상주 헬퍼는 로그인 셸 PATH 를 받지 않아,
// 재생기가 페이지 주소 해소에 부르는 보조 도구(yt-dlp)를 같은 설치 위치에 두고도 찾지 못했다(2026-11-12 실측).
func mediaPlayerEnv(player string, env []string) []string {
	dir := filepath.Dir(player)
	if !filepath.IsAbs(player) || dir == "" {
		return env
	}
	out := make([]string, 0, len(env)+1)
	found := false
	for _, kv := range env {
		if name, value, ok := strings.Cut(kv, "="); ok && strings.EqualFold(name, "PATH") && !found {
			found = true
			if value == "" {
				kv = name + "=" + dir
			} else {
				kv = name + "=" + dir + string(os.PathListSeparator) + value
			}
		}
		out = append(out, kv)
	}
	if !found {
		out = append(out, "PATH="+dir)
	}
	return out
}
