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
	name := residentServiceName(cfg)
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
		_, e = residentWriteIfChanged(path, []byte(residentLaunchAgentBody(name, cfg.InstallationID, exe)))
		return e
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
		changed, e := residentWriteIfChanged(path, []byte(residentSystemdUnitBody(cfg.InstallationID, exe)))
		if e != nil || !changed {
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

var residentSetupMessages = map[string]string{
	"enrolled": "등록했습니다. 화면 공유는 원격 PC의 접근 권한을 허용한 뒤 사용할 수 있습니다. USB를 분리해도 됩니다. 중앙 조종실의 손발 (USB)에서 확인·해제하고, AI에게 PC 이름으로 작업을 부탁하세요.",
	"updated":  "화면 공유 권한을 허용했다면 바로 사용할 수 있습니다. 이미 등록된 PC입니다. 헬퍼를 이 USB의 판으로 바꾸고 다시 시작했습니다. 등록과 PC 이름은 그대로입니다. USB를 분리해도 됩니다.",
	"running":  "이미 등록된 PC이고 헬퍼도 이 USB와 같은 판입니다. 바꾼 것이 없습니다.",
}

// Only the PC's local installer/manager teaches OS permissions, not the cockpit.
func residentPermissionHelp() string {
	if runtime.GOOS != "darwin" {
		return ""
	}
	exe, _ := os.Executable()
	return `<p>Mac: 화면 기록·손쉬운 사용에서 IndieBiz Screen을 허용하세요. 모든 폴더와 외장 드라이브를 쓰려면 설치된 indiebiz-helper에 <a href="x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles">전체 디스크 접근 권한</a>도 허용하세요. 권한 변경 후 다시 연결하면 됩니다.</p><p>` + template.HTMLEscapeString(filepath.Dir(exe)) + `</p>`
}

func residentSetupHandler(cfg *Config, install func(*Config) (string, error), done chan error, token string) http.Handler {
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
			if r.FormValue("media") == "on" {
				if err := residentInstallMedia(); err != nil {
					http.Error(w, err.Error(), 500)
					return
				}
			}
			candidate := *cfg
			candidate.Alias = alias
			outcome, e := install(&candidate)
			if e != nil {
				http.Error(w, e.Error(), 500)
				return
			}
			fmt.Fprint(w, residentSetupMessages[outcome]+residentPermissionHelp())
			select {
			case done <- nil:
			default:
			}
			return
		}
		fmt.Fprintf(w, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IndieBiz PC 등록</title><style>body{font:16px system-ui;max-width:560px;margin:8vh auto;padding:24px;line-height:1.7;background:#faf9f6;color:#302e29}input,button{font:inherit;padding:10px;margin:8px 0;box-sizing:border-box;width:100%%}button{background:#302e29;color:white;border:0;border-radius:6px}input{border:1px solid #ccc;border-radius:6px}</style><h1>이 PC 등록</h1><p>중앙 주소: %s</p><p>AI 작업과 화면 공유를 준비하고 로그인 시 자동 시작합니다. 요청되는 화면·입력 접근 권한을 허용하세요. 관리자 작업은 필요할 때 이 PC에서 인증합니다. 중앙 조종실의 손발 (USB)에서 해제하면 헬퍼가 제거됩니다. 작업 파일은 보존합니다.</p><form method="post"><label>중앙 AI에게 부를 PC 이름<input name="alias" value="%s" maxlength="80" required placeholder="예: 맥12"></label><label><input type="checkbox" name="media" checked style="width:auto"> 음성·영상 구성요소도 설치(ffmpeg·mpv)</label><button>등록하고 시작</button></form>`, template.HTMLEscapeString(cfg.Base), template.HTMLEscapeString(name))
	})
	return mux
}

// residentControlAddress is the loopback port of one installation's manager page;
// holding it is also what makes a helper the only one running.
func residentControlAddress(installationID string) string {
	portValue, _ := strconv.ParseUint(installationID[:4], 16, 32)
	return "127.0.0.1:" + strconv.Itoa(30000+int(portValue)%20000)
}

// residentPutExecutable replaces an installed executable that may be running. The
// running file is moved aside — every OS lets an open executable be renamed, while
// Windows refuses to overwrite it — and a failure puts it back.
func residentPutExecutable(src, dest string) error {
	previous := dest + ".previous"
	_ = os.Remove(previous)
	if e := os.Rename(dest, previous); e != nil {
		return e
	}
	e := residentCopy(src, dest+".new")
	if e == nil {
		e = os.Rename(dest+".new", dest)
	}
	if e != nil {
		_ = os.Remove(dest + ".new")
		_ = os.Rename(previous, dest)
	}
	return e
}

// residentReplaceInstalled is the by-hand update: someone at the PC ran a newer
// helper from the USB folder. The installed helper cannot be asked to step aside
// (it may be any older build), so its processes are found by executable and ended.
func residentReplaceInstalled(cfg *Config, src, dest string) error {
	pids := residentExecutablePIDs(dest) // before the rename changes what they report
	if e := residentPutExecutable(src, dest); e != nil {
		return e
	}
	_ = os.Remove(residentUpdatePath(cfg.DataDir)) // a pending self-update must not roll this one back
	for _, pid := range pids {
		residentKillPID(pid)
	}
	address := residentControlAddress(cfg.InstallationID)
	for attempt := 0; attempt < 30; attempt++ {
		c, e := net.DialTimeout("tcp", address, time.Second)
		if e != nil {
			break
		}
		_ = c.Close()
		time.Sleep(500 * time.Millisecond)
	}
	return nil
}

// residentInstall reports what it did: "enrolled", "updated" (an installed helper
// was replaced by this build) or "running" (already installed, same build).
func residentInstall(invite *Config) (string, error) {
	base, e := os.UserConfigDir()
	if e != nil {
		return "", e
	}
	sum := sha256.Sum256([]byte(invite.Key))
	root := filepath.Join(base, "IndieBiz", "resident-"+hex.EncodeToString(sum[:8]))
	if e = os.MkdirAll(root, 0700); e != nil {
		return "", e
	}
	path := filepath.Join(root, "indiebiz-helper.json")
	cfg := *invite
	if b, e := os.ReadFile(path); e == nil {
		if e = json.Unmarshal(b, &cfg); e != nil {
			return "", e
		}
	}
	if cfg.InstallationID == "" {
		cfg.InstallationID = residentID()
		cfg.DataDir = root
		if e = residentSave(path, cfg); e != nil {
			return "", e
		}
	}
	outcome := "running"
	if cfg.Mode != "resident" {
		outcome = "enrolled"
		cfg.Alias = invite.Alias
		resp, e := residentPost(cfg.Base+"/limb/resident/enroll", map[string]interface{}{"key": cfg.Key, "installation_id": cfg.InstallationID, "alias": cfg.Alias})
		if e != nil {
			return "", e
		}
		if err, ok := resp["detail"]; ok {
			return "", fmt.Errorf("enrollment: %v", err)
		}
		key, ok := resp["key"].(string)
		if !ok {
			return "", fmt.Errorf("invalid enrollment response")
		}
		reg, _ := resp["registration"].(map[string]interface{})
		cfg.Key = key
		cfg.Alias, _ = resp["alias"].(string)
		cfg.Generation, _ = reg["generation"].(string)
		cfg.Mode = "resident"
		cfg.ExpiresAt, _ = resp["expires_at"].(float64)
		if e = residentSave(path, cfg); e != nil {
			return "", e
		}
	}
	src, e := os.Executable()
	if e != nil {
		return "", e
	}
	dest := residentExecutable(root)
	// Running the USB helper on an installed PC replaces an installed helper of
	// another build; with the same build it only opens the existing manager.
	_, existing := os.Stat(dest)
	if src != dest && existing != nil {
		if e = residentCopy(src, dest); e != nil {
			return "", e
		}
	} else if src != dest {
		mine, _, e1 := fileDigest(src)
		installed, _, e2 := fileDigest(dest)
		if e1 == nil && e2 == nil && mine != installed {
			if e = residentReplaceInstalled(&cfg, src, dest); e != nil {
				return "", e
			}
			outcome = "updated"
		}
	}
	// Permissions belong to the installed executable, not the USB copy.
	if outcome != "running" {
		permission := exec.Command(dest, "--screen-permissions", root)
		configureResidentDetached(permission)
		_ = permission.Run() // AI commands remain available if a user declines screen access.
	}
	if e = residentAutostart(&cfg, dest, false); e != nil {
		return "", e
	}
	// A service manager that owns this installation starts the new executable itself.
	if outcome == "updated" && runtime.GOOS != "windows" && residentServiceRestart(&cfg) == nil {
		return outcome, nil
	}
	cmd := exec.Command(dest)
	cmd.Dir = root
	configureResidentDetached(cmd)
	return outcome, cmd.Start()
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

	for _, name := range []string{filepath.Base(residentExecutable(root)), filepath.Base(residentExecutable(root)) + ".previous", "update.json", "control.json", "paused.json", "screen-worker.py", "screen-portal-token"} {
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
	_ = os.RemoveAll(filepath.Join(root, "IndieBiz Screen.app"))
	_ = os.Remove(filepath.Join(root, "removing.json"))
	exe, _ := os.Executable()
	return residentDeleteSelf(exe)
}
