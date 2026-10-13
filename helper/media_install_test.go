package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

func TestMediaInstallUsesOnlyLocalPackageManager(t *testing.T) {
	all := []string{"ffmpeg", "ffplay", "mpv"}
	for _, test := range []struct{ os, binary, want string }{
		{"darwin", "/opt/homebrew/bin/brew", "install"}, {"windows", "winget", "install"}, {"linux", "apt-get", "apt-get"},
	} {
		cmds := mediaInstallCommands(test.os, func(s string) bool { return s == test.binary || s == "pkexec" }, all)
		if len(cmds) == 0 || cmds[0][1] != test.want {
			t.Fatalf("%s: %v", test.os, cmds)
		}
	}
	if cmds := mediaInstallCommands("linux", func(string) bool { return false }, all); len(cmds) != 0 {
		t.Fatal(cmds)
	}
}

func TestMediaInstallCommandsAskOnlyForMissingPackages(t *testing.T) {
	yes := func(string) bool { return true }
	if got := mediaInstallCommands("windows", yes, []string{"mpv"}); len(got) != 1 || got[0][4] != "shinchiro.mpv" {
		t.Fatalf("windows mpv only: %v", got)
	}
	if got := mediaInstallCommands("darwin", yes, []string{"ffplay"}); !reflect.DeepEqual(got, [][]string{{"/opt/homebrew/bin/brew", "install", "ffmpeg"}}) {
		t.Fatalf("darwin ffplay: %v", got)
	}
	if got := mediaInstallCommands("linux", yes, nil); got != nil {
		t.Fatalf("nothing missing: %v", got)
	}
}

func fakeExecutable(t *testing.T, p string) string {
	t.Helper()
	if e := os.MkdirAll(filepath.Dir(p), 0o755); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(p, []byte("#!/bin/sh\n"), 0o755); e != nil {
		t.Fatal(e)
	}
	return p
}

// fakeInstaller sees only dataDir: no PATH, no system locations, no package manager
// unless has says so, and every package-manager run fails.
func fakeInstaller(dataDir string, has func(string) bool, ran *[][]string) mediaInstaller {
	return mediaInstaller{mediaLookup: mediaLookup{goos: "linux", dataDir: dataDir},
		has: has,
		run: func(_ context.Context, argv []string) ([]byte, error) {
			*ran = append(*ran, argv)
			return []byte("E: Unable to locate package mpv"), errors.New("exit status 100")
		}}
}

func setupPost(t *testing.T, media func(*Config) mediaInstallReport) (*httptest.ResponseRecorder, []Config) {
	t.Helper()
	cfg := &Config{Mode: "enroll", Base: "https://central.example", Key: "usb-registration"}
	var installed []Config
	handler := residentSetupHandler(cfg, func(c *Config) (string, error) { installed = append(installed, *c); return "enrolled", nil }, media, make(chan error, 1), "secret")
	r := httptest.NewRequest("POST", "/?token=secret", strings.NewReader("alias=tv1&media=on"))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	return w, installed
}

// No package manager: the media step fails, the PC is still registered and the
// page warns which components are missing and how to add them.
func TestSetupRegistersWhenNoPackageManager(t *testing.T) {
	data := t.TempDir()
	var ran [][]string
	var rep mediaInstallReport
	w, installed := setupPost(t, func(*Config) mediaInstallReport {
		rep = fakeInstaller(data, func(string) bool { return false }, &ran).install()
		return rep
	})
	t.Logf("HTTP %d, registered %d PC(s)\nreport: %+v\npage: %s", w.Code, len(installed), rep, w.Body.String())
	if w.Code != 200 || len(installed) != 1 || installed[0].Alias != "tv1" {
		t.Fatalf("registration blocked: %d %q %v", w.Code, w.Body.String(), installed)
	}
	if !reflect.DeepEqual(rep.Missing, []string{"ffmpeg", "ffplay", "mpv"}) || len(ran) != 0 || !strings.Contains(rep.Error, "패키지 관리자") {
		t.Fatalf("report: %+v ran %v", rep, ran)
	}
	body := w.Body.String()
	for _, want := range []string{"등록했습니다", "경고", "ffmpeg·ffplay·mpv", "apt install ffmpeg mpv", filepath.Join(data, "bin"), "미디어 구성요소 다시 설치"} {
		if !strings.Contains(body, want) {
			t.Fatalf("page lacks %q: %s", want, body)
		}
	}
}

// ffmpeg/ffplay present in the helper bin/, mpv install fails: partial success,
// only mpv requested and reported missing, registration completes.
func TestSetupPartialMediaInstallDoesNotBlock(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("exec bits")
	}
	data := t.TempDir()
	ffmpeg := fakeExecutable(t, filepath.Join(data, "bin", "ffmpeg"))
	fakeExecutable(t, filepath.Join(data, "bin", "ffplay"))
	var ran [][]string
	var rep mediaInstallReport
	w, installed := setupPost(t, func(*Config) mediaInstallReport {
		rep = fakeInstaller(data, func(s string) bool { return s == "pkexec" || s == "apt-get" }, &ran).install()
		return rep
	})
	t.Logf("HTTP %d, registered %d PC(s)\npackage-manager runs: %v\nreport: %+v\npage: %s", w.Code, len(installed), ran, rep, w.Body.String())
	if w.Code != 200 || len(installed) != 1 {
		t.Fatalf("registration blocked: %d %q", w.Code, w.Body.String())
	}
	if !reflect.DeepEqual(ran, [][]string{{"pkexec", "apt-get", "install", "-y", "mpv"}}) {
		t.Fatalf("should request only mpv: %v", ran)
	}
	if !reflect.DeepEqual(rep.Missing, []string{"mpv"}) || rep.Components["ffmpeg"] != ffmpeg || !strings.Contains(rep.Error, "exit status 100") {
		t.Fatalf("report: %+v", rep)
	}
	if body := w.Body.String(); !strings.Contains(body, "등록했습니다") || !strings.Contains(body, "구성요소 중 mpv이(가) 없습니다") {
		t.Fatalf("page: %s", body)
	}
}

// Installer, capabilities and playback resolve mpv through one lookup that
// includes the helper bin/.
func TestMediaLookupMatchesPlaybackIncludingHelperBin(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("exec bits")
	}
	data := t.TempDir()
	for _, name := range []string{"ffmpeg", "ffplay", "mpv"} {
		fakeExecutable(t, filepath.Join(data, "bin", name))
	}
	var ran [][]string
	rep := fakeInstaller(data, func(string) bool { return true }, &ran).install()
	if len(rep.Missing) != 0 || len(ran) != 0 || rep.Error != "" {
		t.Fatalf("helper bin/ ignored by installer: %+v ran %v", rep, ran)
	}
	mpv, missing := residentSelectMediaPlayer("https://example.test/a.mp3", "background", "linux", data, "", nil)
	t.Logf("installer components %v; playback mpv %q; media session ffplay %q", rep.Components, mpv, mediaFindBinary("ffplay", "", data, "linux", "", nil))
	if missing != nil || mpv != rep.Components["mpv"] {
		t.Fatalf("playback %q %v, installer %q", mpv, missing, rep.Components["mpv"])
	}
	if got := mediaFindBinary("ffplay", "", data, "linux", "", nil); got != rep.Components["ffplay"] {
		t.Fatalf("media session %q, installer %q", got, rep.Components["ffplay"])
	}
	if html := residentMediaReportHTML(rep); !strings.Contains(html, "준비되었습니다") {
		t.Fatal(html)
	}
}

func TestSetupFlushesRegistrationBeforeOptionalInstall(t *testing.T) {
	w := httptest.NewRecorder()
	done := make(chan error, 1)
	registered := false
	h := residentSetupHandler(&Config{}, func(*Config) (string, error) {
		registered = true
		return "enrolled", nil
	}, func(*Config) mediaInstallReport {
		if !registered || !w.Flushed || !strings.Contains(w.Body.String(), "등록했습니다") {
			t.Fatal("registration not delivered", w.Body.String())
		}
		if len(done) != 0 {
			t.Fatal("installer may exit before media finishes")
		}
		return mediaInstallReport{Missing: []string{"mpv"}, Error: "<failure>", Hint: "retry"}
	}, done, "secret")
	r := httptest.NewRequest("POST", "/?token=secret", strings.NewReader("alias=test&media=on"))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	h.ServeHTTP(w, r)
	if len(done) != 1 || !strings.Contains(w.Body.String(), "&lt;failure&gt;") || w.Header().Get("Content-Type") != "text/html; charset=utf-8" {
		t.Fatal(w.Header(), w.Body.String())
	}
}

func TestSetupRegistrationFailureDoesNotInstallMedia(t *testing.T) {
	done := make(chan error, 1)
	h := residentSetupHandler(&Config{}, func(*Config) (string, error) { return "", errors.New("offline") },
		func(*Config) mediaInstallReport {
			t.Fatal("media after failed registration")
			return mediaInstallReport{}
		}, done, "secret")
	r := httptest.NewRequest("POST", "/?token=secret", strings.NewReader("alias=test&media=on"))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 500 || len(done) != 0 {
		t.Fatal(w.Code, len(done))
	}
}

func TestMediaInstallContinuesAfterOnePackageFails(t *testing.T) {
	for _, goos := range []string{"darwin", "linux", "windows"} {
		t.Run(goos, func(t *testing.T) {
			data := t.TempDir()
			m := mediaInstaller{mediaLookup: mediaLookup{goos: goos, dataDir: data}, has: func(string) bool { return true }}
			var ran [][]string
			m.run = func(_ context.Context, argv []string) ([]byte, error) {
				ran = append(ran, argv)
				if len(ran) == 1 {
					return []byte("unavailable"), errors.New("package missing")
				}
				name := "mpv"
				if goos == "windows" {
					name += ".exe"
				}
				fakeExecutable(t, filepath.Join(data, "bin", name))
				return nil, nil
			}
			rep := m.install()
			if len(ran) != 2 || rep.Components["mpv"] == "" || !reflect.DeepEqual(rep.Missing, []string{"ffmpeg", "ffplay"}) || !strings.Contains(rep.Error, "package missing") {
				t.Fatalf("runs %v report %+v", ran, rep)
			}
		})
	}
}

func TestMediaInstallDoesNotQueueDuplicatePackageManager(t *testing.T) {
	mediaInstallMu.Lock()
	defer mediaInstallMu.Unlock()
	var ran [][]string
	rep := fakeInstaller(t.TempDir(), func(string) bool { return true }, &ran).install()
	if len(ran) != 0 || !strings.Contains(rep.Error, "이미 진행 중") {
		t.Fatal(rep, ran)
	}
}

func TestManagerShowsLiveMediaStatus(t *testing.T) {
	data := t.TempDir()
	for _, name := range mediaComponentNames {
		if runtime.GOOS == "windows" {
			name += ".exe"
		}
		fakeExecutable(t, filepath.Join(data, "bin", name))
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	r := &residentRuntime{cfg: &Config{DataDir: data}}
	r.localControl(listener)
	b, err := os.ReadFile(filepath.Join(data, "control.json"))
	if err != nil {
		t.Fatal(err)
	}
	var control map[string]string
	if err := json.Unmarshal(b, &control); err != nil {
		t.Fatal(err)
	}
	resp, err := http.Get(control["url"])
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 || !strings.Contains(string(body), "준비되었습니다") || resp.Header.Get("Content-Type") != "text/html; charset=utf-8" {
		t.Fatal(resp.StatusCode, string(body))
	}
}

func TestMinimumHelperStartsWhenAutostartFails(t *testing.T) {
	cfg := &Config{DataDir: t.TempDir()}
	started := false
	err := residentStartInstalled(cfg, "helper", func(*Config, string, bool) error {
		return errors.New("systemd user session unavailable")
	}, func() error { started = true; return nil })
	if err != nil || !started {
		t.Fatal("optional autostart blocked connection", err)
	}
	warnings := residentInstallWarnings(cfg.DataDir)
	if len(warnings) != 1 || !strings.Contains(warnings[0], "systemd") {
		t.Fatal(warnings)
	}
	if !strings.Contains(residentInstallWarningsHTML(cfg.DataDir), "다음 로그인") {
		t.Fatal("no recovery guidance")
	}
	// Successful retry clears the old setup warning, but a launch failure stays fatal.
	err = residentStartInstalled(cfg, "helper", func(*Config, string, bool) error { return nil },
		func() error { return errors.New("cannot execute helper") })
	if err == nil || len(residentInstallWarnings(cfg.DataDir)) != 0 {
		t.Fatal(err)
	}
}

func TestSetupDefaultsToMinimumConnection(t *testing.T) {
	h := residentSetupHandler(&Config{}, nil, nil, make(chan error, 1), "secret")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/?token=secret", nil))
	if strings.Contains(w.Body.String(), `name="media" checked`) || !strings.Contains(w.Body.String(), "나중에 관리 화면") {
		t.Fatal(w.Body.String())
	}
}
