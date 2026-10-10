package main

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"html/template"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

func residentID() string {
	b := make([]byte, 16)
	if _, e := rand.Read(b); e != nil {
		panic(e)
	}
	return hex.EncodeToString(b)
}
func residentSave(path string, value interface{}) error {
	b, e := json.Marshal(value)
	if e != nil {
		return e
	}
	if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
		return e
	}
	f, e := os.CreateTemp(filepath.Dir(path), ".save-")
	if e != nil {
		return e
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if e = f.Chmod(0600); e == nil {
		_, e = f.Write(b)
	}
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return e
	}
	// Windows cannot rename over an open file; all readers close before this operation.
	return os.Rename(tmp, path)
}
func residentCopy(src, dest string) error {
	in, e := os.Open(src)
	if e != nil {
		return e
	}
	defer in.Close()
	out, e := os.OpenFile(dest, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0700)
	if e != nil {
		return e
	}
	_, e = io.Copy(out, in)
	ce := out.Close()
	if e == nil {
		e = ce
	}
	return e
}
func residentExecutable(root string) string {
	name := "indiebiz-helper"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	return filepath.Join(root, name)
}
func residentOpen(url string) {
	var c *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		c = exec.Command("open", url)
	case "windows":
		c = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		c = exec.Command("xdg-open", url)
	}
	_ = c.Start()
}
func xmlText(s string) string {
	var b strings.Builder
	_ = xml.EscapeText(&b, []byte(s))
	return b.String()
}
func residentAutostart(cfg *Config, exe string, remove bool) error {
	name := "indiebiz-resident-" + cfg.InstallationID
	switch runtime.GOOS {
	case "darwin":
		home, e := os.UserHomeDir()
		if e != nil {
			return e
		}
		path := filepath.Join(home, "Library", "LaunchAgents", name+".plist")
		if remove {
			e = os.Remove(path)
			if os.IsNotExist(e) {
				return nil
			}
			return e
		}
		if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
			return e
		}
		body := `<?xml version="1.0"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>` + name + `</string><key>ProgramArguments</key><array><string>` + xmlText(exe) + `</string></array><key>RunAtLoad</key><true/><key>ProcessType</key><string>Background</string></dict></plist>`
		return os.WriteFile(path, []byte(body), 0600)
	case "windows":
		args := []string{"/Create", "/F", "/IT", "/SC", "ONLOGON", "/TN", name, "/TR", `"` + exe + `"`}
		if remove {
			args = []string{"/Delete", "/F", "/TN", name}
		}
		b, e := exec.Command("schtasks", args...).CombinedOutput()
		if e != nil {
			return fmt.Errorf("autostart: %s: %w", b, e)
		}
		return nil
	default:
		home, e := os.UserHomeDir()
		if e != nil {
			return e
		}
		path := filepath.Join(home, ".config", "systemd", "user", name+".service")
		if remove {
			_, _ = exec.Command("systemctl", "--user", "disable", name).CombinedOutput()
			e = os.Remove(path)
			_, _ = exec.Command("systemctl", "--user", "daemon-reload").CombinedOutput()
			if os.IsNotExist(e) {
				return nil
			}
			return e
		}
		if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
			return e
		}
		body := "[Unit]\nDescription=IndieBiz registered PC\n[Service]\nExecStart=" + strconv.Quote(exe) + "\n[Install]\nWantedBy=default.target\n"
		if e = os.WriteFile(path, []byte(body), 0600); e != nil {
			return e
		}
		if b, e := exec.Command("systemctl", "--user", "daemon-reload").CombinedOutput(); e != nil {
			return fmt.Errorf("systemd user: %s %w", b, e)
		}
		b, e := exec.Command("systemctl", "--user", "enable", name).CombinedOutput()
		if e != nil {
			return fmt.Errorf("autostart: %s %w", b, e)
		}
		return nil
	}
}

func residentSetup(cfg *Config) error {
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		return e
	}
	defer listener.Close()
	token := residentID()
	done := make(chan error, 1)
	mux := residentSetupHandler(cfg, residentInstall, done, token)
	server := &http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go server.Serve(listener)
	url := "http://" + listener.Addr().String() + "/?token=" + token
	fmt.Println("설치 화면:", url)
	residentOpen(url)
	return <-done
}

func residentSetupHandler(cfg *Config, install func(*Config) error, done chan error, token string) http.Handler {
	mux := http.NewServeMux()
	var installing sync.Mutex
	name := cfg.Alias
	if name == "" {
		name, _ = os.Hostname()
	}
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("token") != token {
			http.Error(w, "forbidden", 403)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		if r.Method == "POST" {
			installing.Lock()
			defer installing.Unlock()
			alias := strings.TrimSpace(r.FormValue("alias"))
			if alias == "" || len([]rune(alias)) > 80 || strings.ContainsAny(alias, "\r\n\t") {
				http.Error(w, "PC 이름을 1~80자로 입력하세요.", 400)
				return
			}
			candidate := *cfg
			candidate.Alias = alias
			e := install(&candidate)
			if e != nil {
				http.Error(w, e.Error(), 500)
				return
			}
			fmt.Fprint(w, "등록했습니다. USB를 분리해도 됩니다. 중앙 조종실의 손발 (USB)에서 확인·해제하고, AI에게 PC 이름으로 작업을 부탁하세요.")
			select {
			case done <- nil:
			default:
			}
			return
		}
		fmt.Fprintf(w, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IndieBiz PC 등록</title><style>body{font:16px system-ui;max-width:560px;margin:8vh auto;padding:24px;line-height:1.7;background:#faf9f6;color:#302e29}input,button{font:inherit;padding:10px;margin:8px 0;box-sizing:border-box;width:100%%}button{background:#302e29;color:white;border:0;border-radius:6px}input{border:1px solid #ccc;border-radius:6px}</style><h1>이 PC 등록</h1><p>중앙 주소: %s</p><p>현재 사용자 권한으로 작업하며 로그인 시 자동 시작합니다. 중앙 조종실의 손발 (USB)에서 해제하면 헬퍼가 제거됩니다. 작업 파일은 보존합니다.</p><form method="post"><label>중앙 AI에게 부를 PC 이름<input name="alias" value="%s" maxlength="80" required placeholder="예: 맥12"></label><button>등록하고 시작</button></form>`, template.HTMLEscapeString(cfg.Base), template.HTMLEscapeString(name))
	})
	return mux
}
func residentInstall(invite *Config) error {
	base, e := os.UserConfigDir()
	if e != nil {
		return e
	}
	sum := sha256.Sum256([]byte(invite.Key))
	root := filepath.Join(base, "IndieBiz", "resident-"+hex.EncodeToString(sum[:8]))
	if e = os.MkdirAll(root, 0700); e != nil {
		return e
	}
	path := filepath.Join(root, "indiebiz-helper.json")
	cfg := *invite
	if b, e := os.ReadFile(path); e == nil {
		if e = json.Unmarshal(b, &cfg); e != nil {
			return e
		}
	}
	if cfg.InstallationID == "" {
		cfg.InstallationID = residentID()
		cfg.DataDir = root
		if e = residentSave(path, cfg); e != nil {
			return e
		}
	}
	if cfg.Mode != "resident" {
		cfg.Alias = invite.Alias
		resp, e := residentPost(cfg.Base+"/limb/resident/enroll", map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID, "alias": cfg.Alias})
		if e != nil {
			return e
		}
		if err, ok := resp["detail"]; ok {
			return fmt.Errorf("enrollment: %v", err)
		}
		key, ok := resp["key"].(string)
		if !ok {
			return fmt.Errorf("invalid enrollment response")
		}
		reg, _ := resp["registration"].(map[string]interface{})
		cfg.Key = key
		cfg.Alias, _ = resp["alias"].(string)
		cfg.Generation, _ = reg["generation"].(string)
		cfg.Mode = "resident"
		cfg.ExpiresAt, _ = resp["expires_at"].(float64)
		if e = residentSave(path, cfg); e != nil {
			return e
		}
	}
	src, e := os.Executable()
	if e != nil {
		return e
	}
	dest := residentExecutable(root)
	// Reopening the USB installer for an installed PC launches its existing manager.
	// Do not overwrite a running executable (ETXTBSY / Windows file lock).
	_, existing := os.Stat(dest)
	if src != dest && existing != nil {
		if e = residentCopy(src, dest); e != nil {
			return e
		}
	}
	if e = residentAutostart(&cfg, dest, false); e != nil {
		return e
	}
	cmd := exec.Command(dest)
	cmd.Dir = root
	configureResidentDetached(cmd)
	return cmd.Start()
}

// A separate cleanup process survives the worker and deletes only owned program files.
// Workspaces contain user artifacts and are intentionally retained.
func residentRemove(cfg *Config) error {
	copyConfig := *cfg
	copyConfig.Mode = "cleanup"
	if e := residentSave(filepath.Join(cfg.DataDir, "indiebiz-helper.json"), copyConfig); e != nil {
		return e
	}
	if e := residentSave(filepath.Join(cfg.DataDir, "removing.json"), cfg); e != nil {
		return e
	}
	src, e := os.Executable()
	if e != nil {
		return e
	}
	cleaner := filepath.Join(cfg.DataDir, "cleanup")
	if runtime.GOOS == "windows" {
		cleaner += ".exe"
	}
	if e = residentCopy(src, cleaner); e != nil {
		return e
	}
	if e = residentAutostart(cfg, cleaner, false); e != nil {
		return e
	}
	cmd := exec.Command(cleaner, "--resident-cleanup", cfg.DataDir)
	configureResidentDetached(cmd)
	return cmd.Start()
}
func residentCleanup(root string) error {
	var cfg Config
	b, e := os.ReadFile(filepath.Join(root, "removing.json"))
	if e != nil {
		return e
	}
	if e = json.Unmarshal(b, &cfg); e != nil {
		return e
	}
	if filepath.Clean(cfg.DataDir) != filepath.Clean(root) || len(cfg.InstallationID) != 32 {
		return fmt.Errorf("invalid cleanup manifest")
	}
	time.Sleep(2 * time.Second)
	// Cleanup-only mode is restartable at login until logs and removal reach the hub.
	revoked := false

	for _, name := range []string{filepath.Base(residentExecutable(root)), "control.json", "paused.json"} {
		for attempt := 0; attempt < 30; attempt++ {
			e = os.Remove(filepath.Join(root, name))
			if e == nil || os.IsNotExist(e) {
				break
			}
			time.Sleep(time.Second)
		}
		if e != nil && !os.IsNotExist(e) {
			return e
		}
	}
	for {
		_, err := residentPost(cfg.Base+"/limb/resident/local-state", map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID, "remove": true})
		if err == nil {
			break
		}
		if strings.Contains(err.Error(), "invalid_registration") {
			revoked = true
			break
		}
		time.Sleep(15 * time.Second)
	}
	for !revoked {
		paths, _ := filepath.Glob(filepath.Join(root, "spool", "events", "*.json"))
		sort.Strings(paths)
		if len(paths) == 0 {
			break
		}
		if len(paths) > 16 {
			paths = paths[:16]
		}
		events := []residentEvent{}
		for _, p := range paths {
			b, e := os.ReadFile(p)
			if e != nil {
				return e
			}
			var ev residentEvent
			if e = json.Unmarshal(b, &ev); e != nil {
				return e
			}
			events = append(events, ev)
		}
		response, err := residentPost(cfg.Base+"/limb/resident/sync", map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID, "events": events})
		if err != nil {
			time.Sleep(15 * time.Second)
			continue
		}
		acks, _ := response["ack"].([]interface{})
		confirmed := map[string]bool{}
		for _, v := range acks {
			if id, ok := v.(string); ok {
				confirmed[id] = true
			}
		}
		for i, ev := range events {
			if confirmed[ev.EventID] {
				if e = os.Remove(paths[i]); e != nil {
					return e
				}
			}
		}
	}
	if e = os.RemoveAll(filepath.Join(root, "spool")); e != nil {
		return e
	}
	if e = residentAutostart(&cfg, "", true); e != nil {
		return e
	}
	if e = os.Remove(filepath.Join(root, "indiebiz-helper.json")); e != nil && !os.IsNotExist(e) {
		return e
	}
	// Managed executable/autostart are gone; the finalizer remains until receipt delivery.
	for !revoked {
		res, err := residentPost(cfg.Base+"/limb/resident/removed", map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID})
		if err == nil && res["registration"] != nil {
			break
		}
		time.Sleep(30 * time.Second)
	}
	_ = os.Remove(filepath.Join(root, "removing.json"))
	exe, _ := os.Executable()
	return residentDeleteSelf(exe)
}
