// shell.go — 손발의 셸. 눈·손이 없어도 여기가 일의 대부분이다.
//
// 왜 따로 뺐나: 셸 실행에 "정확도"를 붙이는 장치가 셋 붙었기 때문이다.
//
//  1. 작업 디렉토리 기억 — 종전엔 매 명령이 새 `sh -c` 라 `cd /project` 다음 줄의
//     `npm install` 이 엉뚱한 곳에서 돌았다. AI 는 cd 가 먹은 줄 알고 다음으로 넘어가니
//     원인 모를 실패가 쌓인다. 이제 명령이 끝난 자리의 PWD 를 받아 다음 명령에 물려준다
//     (진짜 상주 셸 대신 이 방식인 이유: 명령들이 고루틴으로 **병렬** 실행돼서,
//     상주 셸 하나를 공유하면 출력이 섞이고 긴 명령이 다른 명령을 막는다).
//  2. 셸 선택 — 윈도우에서 cmd 는 빈약하다. shell:"powershell" 로 갈아탈 수 있다.
//  3. 결과에 cwd 를 실어 보냄 — AI 가 "지금 어디에 있는지" 매번 확인 없이 알 수 있다.
package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"
)

// cwdMarker — 명령이 끝난 자리의 작업 디렉토리를 stdout 꼬리에 실어 보내는 표식.
// 임시 파일을 쓰지 않는 이유: 낯선 PC 의 쓰기 가능한 경로를 미리 알 수 없다.
const cwdMarker = "__IB_CWD__"

// envMarker — 명령이 끝난 뒤의 환경변수를 stdout 에 실어 보내는 표식.
// cwd 표식보다 **먼저** 찍는다 — cwd 표식이 늘 꼬리에 오게 해서 LastIndex 로 안전히 자른다.
const envMarker = "__IB_ENV__"

// 세션 환경에서 제외할 휘발성 변수 — 명령마다 저절로 바뀌므로 물려주면 노이즈만 쌓인다.
// (PWD 는 cwd 로 따로 관리하고, _ 나 RANDOM 은 매번 다르다.)
var volatileEnv = map[string]bool{
	"PWD": true, "OLDPWD": true, "SHLVL": true, "_": true, "RANDOM": true,
	"SECONDS": true, "LINES": true, "COLUMNS": true, "PPID": true,
	"BASHPID": true, "BASH_SUBSHELL": true, "EPOCHSECONDS": true, "EPOCHREALTIME": true,
	"CD": true, "ERRORLEVEL": true, "__IBRC": true,
}

// 세션 환경 총량 상한 — 명령마다 export 로 다시 실려 나가므로 무한정 자라면 안 된다.
const maxSessionEnvBytes = 8 * 1024

var (
	sessionMu  sync.Mutex
	sessionCwd string            // 마지막 명령이 끝난 자리 — 다음 명령의 출발점
	sessionEnv map[string]string // 명령이 바꿔놓은 환경변수 — venv·nvm 이 이어지는 근거
	baseEnv    map[string]string // 헬퍼 시작 시점의 환경 — 무엇이 '바뀐 것'인지 판단할 기준
)

func init() {
	baseEnv = map[string]string{}
	for _, kv := range os.Environ() {
		if i := strings.IndexByte(kv, '='); i > 0 {
			baseEnv[kv[:i]] = kv[i+1:]
		}
	}
	sessionEnv = map[string]string{}
}

func getSessionCwd() string {
	sessionMu.Lock()
	defer sessionMu.Unlock()
	return sessionCwd
}

func setSessionCwd(p string) {
	if p == "" {
		return
	}
	sessionMu.Lock()
	sessionCwd = p
	sessionMu.Unlock()
}

// resetSession — 기억한 디렉토리·환경을 버리고 그 PC 의 원래 환경으로 돌아간다.
func resetSession() {
	sessionMu.Lock()
	sessionCwd = ""
	sessionEnv = map[string]string{}
	sessionMu.Unlock()
}

func getSessionEnv() map[string]string {
	sessionMu.Lock()
	defer sessionMu.Unlock()
	out := make(map[string]string, len(sessionEnv))
	for k, v := range sessionEnv {
		out[k] = v
	}
	return out
}

// mergeSessionEnv — 명령이 뱉은 환경을 baseline·기존 세션과 비교해 **바뀐 것만** 남긴다.
// 통째로 물려주면 그 PC 의 원래 환경까지 우리가 덮어쓰는 꼴이 되고 통화도 붓는다.
func mergeSessionEnv(after map[string]string) {
	if len(after) == 0 {
		return // env 블록을 못 읽었다 — 섣불리 세션을 지우지 않는다(파싱 실패 ≠ 초기화)
	}
	sessionMu.Lock()
	defer sessionMu.Unlock()
	// ★이번 명령에서 **사라진** 변수는 기억에서도 지운다. 이게 없으면 `deactivate` 나
	// `unset` 이 먹지 않는다 — 사라진 변수는 env 출력에 아예 없으므로 아래 루프가
	// 못 보고, 옛 값을 영원히 물려주게 된다(실측으로 잡힌 버그).
	for k := range sessionEnv {
		if _, still := after[k]; !still {
			delete(sessionEnv, k)
		}
	}
	total := 0
	for k, v := range after {
		if volatileEnv[strings.ToUpper(k)] || k == "" {
			continue
		}
		if base, ok := baseEnv[k]; ok && base == v {
			delete(sessionEnv, k) // 원래 값으로 되돌아왔으면 기억할 이유가 없다(deactivate)
			continue
		}
		if strings.ContainsAny(v, "\n\r") {
			continue // 여러 줄 값은 파싱·export 둘 다 위태롭다 — 버린다
		}
		sessionEnv[k] = v
	}
	// 상한 초과 시 긴 값부터 버린다(PATH 같은 핵심 짧은 값이 살아남게)
	for total = envBytes(sessionEnv); total > maxSessionEnvBytes; total = envBytes(sessionEnv) {
		longest, size := "", -1
		for k, v := range sessionEnv {
			if len(k)+len(v) > size {
				longest, size = k, len(k)+len(v)
			}
		}
		if longest == "" {
			break
		}
		delete(sessionEnv, longest)
	}
}

func envBytes(m map[string]string) int {
	n := 0
	for k, v := range m {
		n += len(k) + len(v) + 2
	}
	return n
}

// parseEnvBlock — `env`(sh) · `set`(cmd) 출력에서 KEY=VALUE 를 거둔다.
// KEY 모양이 아닌 줄(여러 줄 값의 이어짐 등)은 조용히 버린다.
func parseEnvBlock(block string) map[string]string {
	out := map[string]string{}
	for _, line := range strings.Split(block, "\n") {
		line = strings.TrimRight(line, "\r")
		i := strings.IndexByte(line, '=')
		if i <= 0 {
			continue
		}
		k := line[:i]
		ok := true
		for j, r := range k {
			if !(r == '_' || (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') ||
				(j > 0 && r >= '0' && r <= '9')) {
				ok = false
				break
			}
		}
		if ok {
			out[k] = line[i+1:]
		}
	}
	return out
}

// exportPrefix — 기억한 환경을 다음 명령 앞에 다시 깔아준다. 이게 venv 가 이어지는 실체다
// (`source .venv/bin/activate` 는 결국 PATH·VIRTUAL_ENV 를 바꾸는 일이라 이걸로 재현된다).
func exportPrefix(kind string, env map[string]string) string {
	if len(env) == 0 {
		return ""
	}
	keys := make([]string, 0, len(env))
	for k := range env {
		keys = append(keys, k)
	}
	sort.Strings(keys) // 결정적 순서 — 재현 가능한 스크립트
	var b strings.Builder
	for _, k := range keys {
		v := env[k]
		if runtime.GOOS == "windows" {
			if isPowerShell(kind) {
				b.WriteString("$env:" + k + " = " + psQuote(v) + "; ")
			} else {
				b.WriteString("set \"" + k + "=" + v + "\" & ")
			}
			continue
		}
		b.WriteString("export " + k + "=" + shQuote(v) + "; ")
	}
	return b.String()
}

func isPowerShell(kind string) bool {
	k := strings.ToLower(kind)
	return k == "powershell" || k == "pwsh" || k == "ps"
}

// shellFor — (실행파일, 인자들). 윈도우는 cmd(기본)/powershell 선택.
// 반환된 인자 마지막 원소가 실행할 스크립트다.
func shellFor(kind, script string) (string, []string) {
	if runtime.GOOS != "windows" {
		return "sh", []string{"-c", script}
	}
	switch strings.ToLower(kind) {
	case "powershell", "pwsh", "ps":
		if _, err := exec.LookPath("pwsh"); err == nil {
			return "pwsh", []string{"-NoProfile", "-NonInteractive", "-Command", script}
		}
		return "powershell", []string{"-NoProfile", "-NonInteractive", "-Command", script}
	default:
		// 한국어 윈도우 cmd 는 CP949 로 출력해 JSON(UTF-8) 통화에서 한글이 U+FFFD 로
		// 뭉개진다 — 이 인스턴스만 UTF-8 코드페이지로 전환(best-effort).
		// /v:on = 지연 확장(!CD!) — 이게 없으면 cd 이후의 위치를 못 읽는다.
		return "cmd", []string{"/v:on", "/c", "chcp 65001>nul & " + script}
	}
}

// wrapScript — 사용자 명령을 감싸 (a) 기억한 디렉토리에서 시작하고 (b) 끝난 자리의
// 디렉토리를 표식과 함께 뱉되 (c) **원래 명령의 종료 코드를 보존**한다.
// (c)가 핵심이다 — 표식 출력이 성공하면서 실패한 명령을 성공으로 둔갑시키면 안 된다.
func wrapScript(kind, cmd, startDir string, env map[string]string) string {
	exports := exportPrefix(kind, env)
	if runtime.GOOS == "windows" {
		if isPowerShell(kind) {
			pre := exports
			if startDir != "" {
				pre += fmt.Sprintf("Set-Location -LiteralPath %s -ErrorAction SilentlyContinue; ", psQuote(startDir))
			}
			return pre + "$global:LASTEXITCODE = 0; " + cmd +
				"; $__ibrc = $LASTEXITCODE; if ($null -eq $__ibrc) { $__ibrc = 0 }; " +
				"Write-Output \"" + envMarker + "\"; " +
				"Get-ChildItem Env: | ForEach-Object { \"$($_.Name)=$($_.Value)\" }; " +
				"Write-Output (\"" + cwdMarker + "\" + $PWD.Path); exit $__ibrc"
		}
		pre := exports
		if startDir != "" {
			pre += "cd /d \"" + startDir + "\" 2>nul & "
		}
		return pre + "( " + cmd + " ) & set __ibrc=!errorlevel! & echo " + envMarker +
			" & set & echo " + cwdMarker + "!CD! & exit /b !__ibrc!"
	}
	pre := exports
	if startDir != "" {
		pre += "cd " + shQuote(startDir) + " 2>/dev/null; "
	}
	// 순서가 중요하다: 명령 → 종료코드 보관 → env → cwd(꼬리). cwd 를 마지막에 둬야
	// LastIndex 로 자를 때 env 블록이 통째로 딸려 나온다.
	return pre + cmd +
		"\n__ibrc=$?" +
		"\nprintf '\\n" + envMarker + "\\n'" +
		"\nenv" +
		"\nprintf '\\n" + cwdMarker + "%s\\n' \"$PWD\"" +
		"\nexit $__ibrc"
}

func shQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }
func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }

// splitMarkers — stdout 꼬리에서 표식 두 개(env·cwd)를 떼어낸다.
// 반환 (정리된 stdout, 끝난 자리, 끝난 뒤 환경).
// 명령 자신의 출력에 표식 문자열이 섞여도 **마지막** 것만 본다(위장 방어).
func splitMarkers(out string) (string, string, map[string]string) {
	idx := strings.LastIndex(out, cwdMarker)
	if idx < 0 {
		return out, "", nil
	}
	rest := out[idx+len(cwdMarker):]
	dir := strings.TrimRight(strings.SplitN(rest, "\n", 2)[0], "\r \t")
	body := strings.TrimRight(out[:idx], "\r\n")

	var env map[string]string
	if e := strings.LastIndex(body, envMarker); e >= 0 {
		env = parseEnvBlock(body[e+len(envMarker):])
		body = strings.TrimRight(body[:e], "\r\n")
	}
	return body, dir, env
}

func doShell(c Command) map[string]interface{} {
	if strings.TrimSpace(c.Cmd) == "" {
		return errResult("empty_cmd", "cmd 가 비었습니다")
	}
	to := c.Timeout
	if to <= 0 {
		to = cmdTimeout
	}

	// ★세션 초기화 — 환경변수는 이어지지만 **셸 함수·별칭은 이어지지 않는다**(우린 상주
	// 셸이 아니라 매번 새 셸에 환경만 다시 깔아준다). 그래서 `deactivate` 같은 *함수*는
	// 부를 수 없다. venv 를 벗거나 환경이 꼬였을 때 되돌릴 길이 이 reset 이다.
	if c.Reset {
		resetSession()
	}

	// 출발 디렉토리: 명시한 cwd > 기억한 자리 > (그 PC 기본)
	startDir := c.Cwd
	if startDir == "" {
		startDir = getSessionCwd()
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(to)*time.Second)
	defer cancel()

	bin, args := shellFor(c.Shell, wrapScript(c.Shell, c.Cmd, startDir, getSessionEnv()))
	cmd := exec.CommandContext(ctx, bin, args...)
	var stdout, stderr bytes.Buffer
	// 진행 중계 — 긴 명령이 끝날 때까지 깜깜하지 않게 주기적으로 꼬리를 허브에 올린다.
	prog := newProgressReporter(c.JobID)
	cmd.Stdout = io.MultiWriter(&stdout, prog)
	cmd.Stderr = io.MultiWriter(&stderr, prog)
	// 대화형 프롬프트 대응 — stdin 이 주어지면 물려준다. 없으면 nil(=/dev/null) 이라
	// 프롬프트를 기다리는 명령은 EOF 를 받고 곧장 끝난다(타임아웃까지 멈추지 않는다).
	if c.Stdin != "" {
		cmd.Stdin = strings.NewReader(c.Stdin)
	}
	err := cmd.Run()
	prog.stop()

	cleaned, endDir, endEnv := splitMarkers(stdout.String())
	if endDir != "" {
		setSessionCwd(endDir) // 다음 명령이 여기서 이어진다
	} else if startDir != "" {
		endDir = startDir
	}
	if endEnv != nil {
		mergeSessionEnv(endEnv) // venv·nvm 활성화가 다음 명령까지 이어지는 지점
	}

	res := map[string]interface{}{
		"op":     "shell",
		"stdout": clip(cleaned),
		"stderr": clip(stderr.String()),
		"exit":   exitCode(err),
		"cwd":    endDir, // ★AI 가 "지금 어디인지"를 매번 되묻지 않게
	}
	if n := len(getSessionEnv()); n > 0 {
		res["session_env"] = n // 몇 개의 환경변수가 이어지고 있는지(디버깅 단서)
	}
	if c.Shell != "" {
		res["shell"] = bin
	}
	if ctx.Err() == context.DeadlineExceeded {
		res["timeout"] = true
	}
	return res
}

// doInfo — 그 PC 의 신상. **낯선 PC 에서 AI 가 명령 문법을 추측하지 않게** 하는 게 목적이다.
// 종전엔 os/arch/hostname/cwd 넷뿐이라, AI 는 패키지 매니저가 뭔지·관리자인지·GUI 가 있는지를
// 셸을 여러 번 찔러 알아내야 했다(그 왕복이 곧 실패와 지연이었다). 접속 직후 한 번에 준다.
func doInfo() map[string]interface{} {
	cwd, _ := os.Getwd()
	if s := getSessionCwd(); s != "" {
		cwd = s
	}
	host, _ := os.Hostname()

	info := map[string]interface{}{
		"op": "info", "os": runtime.GOOS, "arch": runtime.GOARCH,
		"hostname": host, "cwd": cwd,
		"user": osUser(), "home": userHome(),
		"os_version": osVersion(),
		"admin":      isAdmin(),
		"shells":     whichOf(shellCandidates()),
		"package_managers": whichOf([]string{
			"winget", "choco", "scoop", "brew", "apt", "dnf", "pacman", "zypper"}),
		"tools": whichOf([]string{"git", "python3", "python", "node", "curl", "docker"}),
		"gui":   guiCapabilities(),
		"path":  os.Getenv("PATH"),
	}
	if n := len(getSessionEnv()); n > 0 {
		info["session_env"] = getSessionEnv() // 지금 이어지고 있는 환경(venv 등)
	}
	return info
}

func shellCandidates() []string {
	if runtime.GOOS == "windows" {
		return []string{"powershell", "pwsh", "cmd", "bash"}
	}
	return []string{"bash", "zsh", "sh", "fish", "pwsh"}
}

// whichOf — PATH 에 실제로 있는 것만 골라 돌려준다(없는 걸 있다고 하지 않는다).
func whichOf(names []string) []string {
	var found []string
	for _, n := range names {
		if _, err := exec.LookPath(n); err == nil {
			found = append(found, n)
		}
	}
	return found
}

// guiCapabilities — 눈·손이 이 PC 에서 실제로 될지 미리 알려준다. 해보고 실패하는 것보다
// 미리 아는 게 싸다(특히 헤드리스 서버·잠긴 화면·Wayland 권한).
func guiCapabilities() map[string]interface{} {
	g := map[string]interface{}{}
	// 화면 해상도 — 좌표 감각의 바탕(캡처는 축소돼 오므로 원본 크기를 미리 알면 좋다).
	if w, h := logicalScreenSize(0, 0); w > 0 && h > 0 {
		g["resolution"] = fmt.Sprintf("%dx%d", w, h)
	}
	switch runtime.GOOS {
	case "darwin":
		g["screen"] = "screencapture"
		g["input"] = "osascript(System Events) — 손쉬운 사용 권한 필요"
		if len(whichOf([]string{"cliclick"})) > 0 {
			g["input"] = "cliclick (전 기능)"
		}
	case "windows":
		g["screen"] = "powershell/System.Drawing"
		g["input"] = "powershell/user32"
	default:
		g["screen"] = firstOr(whichOf([]string{"grim", "scrot", "import", "gnome-screenshot", "spectacle"}), "없음")
		g["input"] = firstOr(whichOf([]string{"xdotool", "ydotool"}), "없음")
		g["display"] = firstOr(nonEmpty([]string{os.Getenv("WAYLAND_DISPLAY"), os.Getenv("DISPLAY")}), "없음(헤드리스)")
	}
	return g
}

func firstOr(list []string, dflt string) string {
	if len(list) > 0 {
		return list[0]
	}
	return dflt
}

func nonEmpty(list []string) []string {
	var out []string
	for _, s := range list {
		if s != "" {
			out = append(out, s)
		}
	}
	return out
}

func osUser() string {
	for _, k := range []string{"USER", "USERNAME", "LOGNAME"} {
		if v := os.Getenv(k); v != "" {
			return v
		}
	}
	return ""
}

func userHome() string {
	h, _ := os.UserHomeDir()
	return h
}

func osVersion() string {
	switch runtime.GOOS {
	case "darwin":
		if out, err := runOutTimeout(8*time.Second, "sw_vers", "-productVersion"); err == nil {
			return "macOS " + strings.TrimSpace(out)
		}
	case "windows":
		if out, err := runOutTimeout(10*time.Second, "cmd", "/c", "ver"); err == nil {
			return strings.TrimSpace(out)
		}
	default:
		if b, err := os.ReadFile("/etc/os-release"); err == nil {
			for _, line := range strings.Split(string(b), "\n") {
				if strings.HasPrefix(line, "PRETTY_NAME=") {
					return strings.Trim(strings.TrimPrefix(line, "PRETTY_NAME="), `"`)
				}
			}
		}
	}
	return ""
}

// isAdmin — 관리자/root 여부. 설치 명령이 권한으로 실패할지를 AI 가 **미리** 알게 한다.
func isAdmin() bool {
	if runtime.GOOS == "windows" {
		// net session 은 관리자에서만 성공한다(추가 설치 없이 되는 표준 확인법).
		_, err := runOutTimeout(10*time.Second, "cmd", "/c", "net session >nul 2>&1")
		return err == nil
	}
	return os.Geteuid() == 0
}
