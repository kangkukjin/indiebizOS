package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

// Media components are optional: their install never fails enrollment. The
// installer reports what is still missing and how to add it, and the helper
// keeps reporting the same live lookup in its capabilities.
var mediaComponentNames = []string{"ffmpeg", "ffplay", "mpv"}

var mediaInstallMu sync.Mutex // one package-manager run at a time

type mediaInstallReport struct {
	Components map[string]string `json:"components"` // name -> executable path, "" when absent
	Missing    []string          `json:"missing"`
	Error      string            `json:"error,omitempty"`
	Hint       string            `json:"hint,omitempty"`
}

// mediaLookup resolves the components with the same functions the media session
// (mediaFindBinary) and playback (findMediaPlayerIn) use, the helper bin/ included.
type mediaLookup struct {
	goos, dataDir, pathEnv string
	ffmpegDirs, players    []string
}

func newMediaLookup(dataDir string) mediaLookup {
	home, _ := os.UserHomeDir()
	return mediaLookup{goos: runtime.GOOS, dataDir: dataDir, pathEnv: os.Getenv("PATH"),
		ffmpegDirs: mediaFFmpegCandidates(runtime.GOOS, "", home), players: mediaPlayerCandidates(runtime.GOOS, "", home)}
}

func (l mediaLookup) locate() (map[string]string, []string) {
	mpv, _ := findMediaPlayerIn(l.goos, l.dataDir, l.pathEnv, l.players)
	found := map[string]string{
		"ffmpeg": mediaFindBinary("ffmpeg", "", l.dataDir, l.goos, l.pathEnv, l.ffmpegDirs),
		"ffplay": mediaFindBinary("ffplay", "", l.dataDir, l.goos, l.pathEnv, l.ffmpegDirs),
		"mpv":    mpv,
	}
	missing := []string{}
	for _, name := range mediaComponentNames {
		if found[name] == "" {
			missing = append(missing, name)
		}
	}
	return found, missing
}

// status is the live state reported in capabilities and on the manager page.
func (l mediaLookup) status() mediaInstallReport {
	found, missing := l.locate()
	rep := mediaInstallReport{Components: found, Missing: missing}
	if len(missing) > 0 {
		rep.Hint = mediaInstallHint(l.goos, l.dataDir, missing)
	}
	return rep
}

type mediaInstaller struct {
	mediaLookup
	has func(string) bool
	run func(ctx context.Context, argv []string) ([]byte, error)
}

func newMediaInstaller(dataDir string) mediaInstaller {
	return mediaInstaller{mediaLookup: newMediaLookup(dataDir),
		has: func(name string) bool { _, err := exec.LookPath(name); return err == nil },
		run: func(ctx context.Context, argv []string) ([]byte, error) {
			return exec.CommandContext(ctx, argv[0], argv[1:]...).CombinedOutput()
		}}
}

// install runs only from the PC's own setup and manager pages, never from a hub
// command. It installs just the missing components and always returns a report.
func (m mediaInstaller) install() mediaInstallReport {
	if !mediaInstallMu.TryLock() {
		rep := m.status()
		rep.Error = "미디어 구성요소 설치가 이미 진행 중입니다. 잠시 뒤 다시 확인하세요."
		return rep
	}
	defer mediaInstallMu.Unlock()
	_, missing := m.locate()
	if len(missing) == 0 {
		return m.status()
	}
	cmds := mediaInstallCommands(m.goos, m.has, missing)
	var errs []string
	if len(cmds) == 0 {
		errs = append(errs, "이 PC에서 쓸 수 있는 패키지 관리자를 찾지 못했습니다")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	for _, argv := range cmds {
		if output, err := m.run(ctx, argv); err != nil {
			out := strings.TrimSpace(string(output))
			if r := []rune(out); len(r) > 400 {
				out = "…" + string(r[len(r)-400:])
			}
			errs = append(errs, fmt.Sprintf("%s 실패: %v %s", strings.Join(argv, " "), err, out))
		}
	}
	rep := m.status()
	if len(rep.Missing) > 0 {
		if len(errs) == 0 {
			errs = append(errs, "설치 명령은 끝났지만 실행 파일을 찾지 못했습니다")
		}
		rep.Error = strings.Join(errs, "; ")
	}
	return rep
}

func mediaInstallHint(goos, dataDir string, missing []string) string {
	var how string
	switch goos {
	case "darwin":
		how = "Homebrew(https://brew.sh)를 설치한 뒤 터미널에서 brew install ffmpeg mpv"
	case "windows":
		how = "명령 프롬프트에서 winget install --exact --id Gyan.FFmpeg 및 winget install --exact --id shinchiro.mpv (winget이 없으면 Microsoft Store의 '앱 설치 관리자'를 먼저 설치)"
	default:
		how = "sudo apt install ffmpeg mpv (dnf·pacman도 같은 패키지 이름)"
	}
	hint := strings.Join(missing, "·") + " 보완: " + how
	if dataDir != "" {
		hint += " — 또는 실행 파일을 " + filepath.Join(dataDir, "bin") + " 에 넣으세요"
	}
	return hint + ". 그다음 이 PC의 관리 화면에서 '미디어 구성요소 다시 설치'를 누르면 다시 확인합니다."
}

// mediaInstallCommands asks the local package manager for the missing packages
// only (ffmpeg provides ffmpeg and ffplay).
func mediaInstallCommands(goos string, has func(string) bool, missing []string) [][]string {
	var ffmpeg, mpv bool
	for _, name := range missing {
		ffmpeg = ffmpeg || name == "ffmpeg" || name == "ffplay"
		mpv = mpv || name == "mpv"
	}
	var pkgs []string
	if ffmpeg {
		pkgs = append(pkgs, "ffmpeg")
	}
	if mpv {
		pkgs = append(pkgs, "mpv")
	}
	if len(pkgs) == 0 {
		return nil
	}
	// Independent packages must still install when another package fails.
	commands := func(prefix ...string) [][]string {
		var cmds [][]string
		for _, pkg := range pkgs {
			cmds = append(cmds, append(append([]string{}, prefix...), pkg))
		}
		return cmds
	}
	switch goos {
	case "darwin":
		for _, brew := range []string{"/opt/homebrew/bin/brew", "/usr/local/bin/brew", "brew"} {
			if has(brew) {
				return commands(brew, "install")
			}
		}
	case "windows":
		if has("winget") {
			ids := map[string]string{"ffmpeg": "Gyan.FFmpeg", "mpv": "shinchiro.mpv"}
			var cmds [][]string
			for _, p := range pkgs {
				cmds = append(cmds, []string{"winget", "install", "--exact", "--id", ids[p], "--accept-package-agreements", "--accept-source-agreements"})
			}
			return cmds
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
				return commands("pkexec", manager, "-S", "--needed", "--noconfirm")
			}
			return commands("pkexec", manager, "install", "-y")
		}
	}
	return nil
}
