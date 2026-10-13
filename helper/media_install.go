package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"time"
)

// Invoked only by the local installer checkbox, never by a hub command.
func residentInstallMedia() error {
	home, _ := os.UserHomeDir()
	candidates := mediaFFmpegCandidates(runtime.GOOS, "", home)
	ready := true
	for _, name := range []string{"ffmpeg", "ffplay"} {
		ready = ready && mediaFindBinary(name, "", "", runtime.GOOS, os.Getenv("PATH"), candidates) != ""
	}
	player, _ := findMediaPlayer()
	if ready && player != "" {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	for _, argv := range mediaInstallCommands(runtime.GOOS, func(name string) bool { _, err := exec.LookPath(name); return err == nil }) {
		cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
		if output, err := cmd.CombinedOutput(); err != nil {
			return fmt.Errorf("미디어 구성요소 설치 실패: %w (%s)", err, string(output))
		}
	}
	for _, name := range []string{"ffmpeg", "ffplay"} {
		if mediaFindBinary(name, "", "", runtime.GOOS, os.Getenv("PATH"), candidates) == "" {
			return fmt.Errorf("%s를 찾지 못했습니다. 패키지 관리자를 설치하거나 헬퍼 bin 폴더에 미디어 구성요소를 넣어 주세요", name)
		}
	}
	if player, _ := findMediaPlayer(); player == "" {
		return fmt.Errorf("mpv를 찾지 못했습니다. 설치 후 다시 시도해 주세요")
	}
	return nil
}

func mediaInstallCommands(goos string, has func(string) bool) [][]string {
	switch goos {
	case "darwin":
		for _, brew := range []string{"/opt/homebrew/bin/brew", "/usr/local/bin/brew", "brew"} {
			if has(brew) {
				return [][]string{{brew, "install", "ffmpeg", "mpv"}}
			}
		}
	case "windows":
		if has("winget") {
			return [][]string{
				{"winget", "install", "--exact", "--id", "Gyan.FFmpeg", "--accept-package-agreements", "--accept-source-agreements"},
				{"winget", "install", "--exact", "--id", "shinchiro.mpv", "--accept-package-agreements", "--accept-source-agreements"},
			}
		}
	case "linux":
		if !has("pkexec") {
			return nil
		}
		for _, manager := range []string{"apt-get", "dnf", "pacman"} {
			if !has(manager) {
				continue
			}
			if manager == "pacman" {
				return [][]string{{"pkexec", manager, "-S", "--needed", "--noconfirm", "ffmpeg", "mpv"}}
			}
			return [][]string{{"pkexec", manager, "install", "-y", "ffmpeg", "mpv"}}
		}
	}
	return nil
}
