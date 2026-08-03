// input.go — 손발의 손. 그 PC 의 마우스·키보드를 움직인다(screen.go 의 눈과 짝).
//
// 눈만으로는 반쪽이다: 셸이 못 건드리는 일(설치 마법사의 '다음' 버튼, 로그인 창, GUI
// 전용 앱)은 결국 누르고 입력해야 끝난다. 반대로 손만 있으면 눈먼 조작이라 위험하다 —
// 그래서 기본값이 **누른 뒤 자동 재캡처**(shot)다: 한 번의 왕복에 see→act→verify 가
// 다 들어가서, AI 가 자기 조작의 결과를 반드시 보고 다음을 정한다.
//
// 좌표: AI 는 자기가 본 그림 위의 좌표를 그대로 말한다(screen.go 의 mapPoint 가 환산).
//
// 얇은 바이너리 원칙(screen.go 와 동일): CGo 없이 OS 기본 도구로 셸아웃한다.
//   · macOS  : cliclick 이 있으면 그것(전 기능), 없으면 osascript/System Events(클릭·타이핑)
//   · Windows: PowerShell + user32.dll (SetCursorPos/mouse_event/keybd_event) — 기본 탑재
//   · Linux  : xdotool(X11) / ydotool(Wayland) 중 있는 것
// 맥에서 System Events 는 **손쉬운 사용(접근성) 권한**을 요구한다. 이 마찰은 버그가 아니라
// 그 PC 주인이 보는 동의 지점이라 안내만 정확히 한다(inputPermissionHint).
package main

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const inputTimeout = 20 * time.Second

// doInput — click/type/key/scroll/drag/move 공통 진입점.
// 성공하면 (기본) 화면을 다시 찍어 결과를 눈으로 확인시킨다.
func doInput(c Command) map[string]interface{} {
	var err error
	var desc string

	switch c.Op {
	case "click":
		x, y := mapPoint(c.X, c.Y)
		btn := orDefault(c.Button, "left")
		n := c.Clicks
		if n <= 0 {
			n = 1
		}
		desc = fmt.Sprintf("%s %d회 @(%d,%d)", btn, n, c.X, c.Y)
		err = injectClick(x, y, btn, n)
	case "move":
		x, y := mapPoint(c.X, c.Y)
		desc = fmt.Sprintf("(%d,%d)", c.X, c.Y)
		err = injectMove(x, y)
	case "type":
		if c.Text == "" {
			return errResult("empty_text", "type 엔 text 가 필요합니다.")
		}
		desc = oneLine(c.Text, 60)
		err = injectType(c.Text)
	case "key":
		if c.Key == "" {
			return errResult("empty_key", "key 가 필요합니다(예: return, escape, cmd+s, ctrl+c).")
		}
		desc = c.Key
		err = injectKey(c.Key)
	case "scroll":
		dir := orDefault(c.Direction, "down")
		amt := c.Amount
		if amt <= 0 {
			amt = 5
		}
		x, y := mapPoint(c.X, c.Y)
		desc = fmt.Sprintf("%s %d", dir, amt)
		err = injectScroll(x, y, dir, amt, c.X != 0 || c.Y != 0)
	case "drag":
		x1, y1 := mapPoint(c.X, c.Y)
		x2, y2 := mapPoint(c.X2, c.Y2)
		desc = fmt.Sprintf("(%d,%d)→(%d,%d)", c.X, c.Y, c.X2, c.Y2)
		err = injectDrag(x1, y1, x2, y2)
	default:
		return errResult("unknown_op", "알 수 없는 입력 op: "+c.Op)
	}

	if err != nil {
		return errResult("input_failed", err.Error()+" — "+inputPermissionHint())
	}

	res := map[string]interface{}{"op": c.Op, "did": desc}
	// 기본 재캡처 — 조작 결과를 AI 가 반드시 보게 한다. shot:false 로 끌 수 있다
	// (연속 입력처럼 중간 화면이 필요 없을 때는 끄는 게 빠르고 싸다).
	if c.Shot == nil || *c.Shot {
		time.Sleep(settleDelay(c)) // UI 가 그려질 짬 — 너무 빨리 찍으면 이전 화면이 찍힌다
		shot := doScreen(c)
		if _, bad := shot["error"]; !bad {
			for _, k := range []string{"b64", "media_type", "width", "height",
				"orig_width", "orig_height", "bytes", "tool"} {
				res[k] = shot[k]
			}
			res["shot"] = true
		} else {
			res["shot"] = false
			res["shot_error"] = shot["message"]
		}
	}
	return res
}

func settleDelay(c Command) time.Duration {
	if c.SettleMs > 0 {
		return time.Duration(c.SettleMs) * time.Millisecond
	}
	return 700 * time.Millisecond
}

// === 플랫폼 분기 ===

func hasBin(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

func runIn(bin string, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), inputTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, bin, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if m := oneLine(stderr.String(), 200); m != "" {
			return fmt.Errorf("%s: %s", bin, m)
		}
		return fmt.Errorf("%s: %w", bin, err)
	}
	return nil
}

func runOut(bin string, args ...string) (string, error) {
	return runOutTimeout(inputTimeout, bin, args...)
}

func runOutTimeout(d time.Duration, bin string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), d)
	defer cancel()
	cmd := exec.CommandContext(ctx, bin, args...)
	var out, stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if m := oneLine(stderr.String(), 200); m != "" {
			return "", fmt.Errorf("%s: %s", bin, m)
		}
		return "", err
	}
	return out.String(), nil
}

func osaEscape(s string) string {
	return strings.NewReplacer(`\`, `\\`, `"`, `\"`).Replace(s)
}

func injectMove(x, y int) error {
	switch runtime.GOOS {
	case "darwin":
		if hasBin("cliclick") {
			return runIn("cliclick", fmt.Sprintf("m:%d,%d", x, y))
		}
		// System Events 엔 순수 커서 이동이 없다 — 이동만 필요한 경우는 드무니 정직하게 알린다.
		return fmt.Errorf("맥에서 커서 이동만 하려면 cliclick 이 필요합니다(brew install cliclick). 클릭은 cliclick 없이도 됩니다")
	case "windows":
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command",
			winUser32Prelude+fmt.Sprintf("[IB]::SetCursorPos(%d,%d)", x, y))
	default:
		if hasBin("xdotool") {
			return runIn("xdotool", "mousemove", strconv.Itoa(x), strconv.Itoa(y))
		}
		if hasBin("ydotool") {
			return runIn("ydotool", "mousemove", "--absolute", "-x", strconv.Itoa(x), "-y", strconv.Itoa(y))
		}
		return errNoLinuxInput()
	}
}

func injectClick(x, y int, button string, clicks int) error {
	switch runtime.GOOS {
	case "darwin":
		if hasBin("cliclick") {
			verb := map[string]string{"left": "c", "right": "rc", "middle": "c"}[button]
			if verb == "" {
				verb = "c"
			}
			if button == "left" && clicks >= 2 {
				verb = "dc"
				clicks = 1
			}
			args := []string{fmt.Sprintf("m:%d,%d", x, y)}
			for i := 0; i < clicks; i++ {
				args = append(args, fmt.Sprintf("%s:%d,%d", verb, x, y))
			}
			return runIn("cliclick", args...)
		}
		if button != "left" {
			return fmt.Errorf("맥에서 %s 클릭은 cliclick 이 필요합니다(brew install cliclick)", button)
		}
		// System Events 의 좌표 클릭 — 커서는 안 움직이지만 클릭은 전달된다.
		script := fmt.Sprintf(`tell application "System Events" to click at {%d, %d}`, x, y)
		for i := 0; i < clicks; i++ {
			if err := runIn("osascript", "-e", script); err != nil {
				return err
			}
		}
		return nil
	case "windows":
		down, up := "0x0002", "0x0004" // LEFTDOWN/LEFTUP
		switch button {
		case "right":
			down, up = "0x0008", "0x0010"
		case "middle":
			down, up = "0x0020", "0x0040"
		}
		ps := winUser32Prelude + fmt.Sprintf("[IB]::SetCursorPos(%d,%d); Start-Sleep -m 40; ", x, y)
		for i := 0; i < clicks; i++ {
			ps += fmt.Sprintf("[IB]::mouse_event(%s,0,0,0,0); [IB]::mouse_event(%s,0,0,0,0); Start-Sleep -m 60; ", down, up)
		}
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command", ps)
	default:
		if hasBin("xdotool") {
			btn := map[string]string{"left": "1", "middle": "2", "right": "3"}[button]
			if btn == "" {
				btn = "1"
			}
			args := []string{"mousemove", strconv.Itoa(x), strconv.Itoa(y), "click"}
			if clicks > 1 {
				args = append(args, "--repeat", strconv.Itoa(clicks))
			}
			return runIn("xdotool", append(args, btn)...)
		}
		return errNoLinuxInput()
	}
}

func injectType(text string) error {
	switch runtime.GOOS {
	case "darwin":
		// keystroke 는 유니코드(한글 포함)를 그대로 넣는다 — IME 를 안 거쳐 조합 문제도 없다.
		return runIn("osascript", "-e",
			fmt.Sprintf(`tell application "System Events" to keystroke "%s"`, osaEscape(text)))
	case "windows":
		// SendKeys 는 +^%~(){}[] 가 제어문자다 — 중괄호로 감싸 원문 그대로 넣는다.
		esc := text
		for _, ch := range []string{"{", "}", "+", "^", "%", "~", "(", ")", "[", "]"} {
			esc = strings.ReplaceAll(esc, ch, "{"+ch+"}")
		}
		esc = strings.ReplaceAll(esc, "'", "''") // PowerShell 작은따옴표 리터럴
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command",
			"Add-Type -AssemblyName System.Windows.Forms; "+
				"[System.Windows.Forms.SendKeys]::SendWait('"+esc+"')")
	default:
		if hasBin("xdotool") {
			return runIn("xdotool", "type", "--clearmodifiers", "--", text)
		}
		if hasBin("ydotool") {
			return runIn("ydotool", "type", "--", text)
		}
		return errNoLinuxInput()
	}
}

// keyAliases — 사람이 부르는 이름 → 각 OS 표기. AI 가 "return"·"esc"·"엔터" 중 뭘 써도
// 통하게 하는 게 목적(어휘 하나에 표기 셋을 외우게 하지 않는다).
var keyAliases = map[string]string{
	"enter": "return", "엔터": "return", "리턴": "return",
	"esc": "escape", "이스케이프": "escape",
	"del": "delete", "backspace": "delete", "백스페이스": "delete",
	"pgup": "pageup", "pgdn": "pagedown",
	"ctl": "ctrl", "control": "ctrl", "cmd": "command", "메타": "command",
	"opt": "option", "alt": "option",
}

var macKeyCodes = map[string]int{
	"return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53,
	"left": 123, "right": 124, "down": 125, "up": 126,
	"home": 115, "end": 119, "pageup": 116, "pagedown": 121,
	"f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
	"forwarddelete": 117,
}

var winKeyNames = map[string]string{
	"return": "{ENTER}", "tab": "{TAB}", "space": " ", "delete": "{BACKSPACE}",
	"escape": "{ESC}", "left": "{LEFT}", "right": "{RIGHT}", "up": "{UP}", "down": "{DOWN}",
	"home": "{HOME}", "end": "{END}", "pageup": "{PGUP}", "pagedown": "{PGDN}",
	"forwarddelete": "{DELETE}", "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}",
	"f5": "{F5}", "f6": "{F6}", "f11": "{F11}", "f12": "{F12}",
}

// parseKey — "cmd+shift+s" → (수식키들, 본키). 별칭을 정규화한다.
func parseKey(spec string) ([]string, string) {
	parts := strings.Split(strings.ToLower(strings.TrimSpace(spec)), "+")
	var mods []string
	base := ""
	for i, p := range parts {
		p = strings.TrimSpace(p)
		if a, ok := keyAliases[p]; ok {
			p = a
		}
		if i < len(parts)-1 {
			mods = append(mods, p)
		} else {
			base = p
		}
	}
	return mods, base
}

func injectKey(spec string) error {
	mods, base := parseKey(spec)
	switch runtime.GOOS {
	case "darwin":
		var using []string
		for _, m := range mods {
			switch m {
			case "command":
				using = append(using, "command down")
			case "ctrl":
				using = append(using, "control down")
			case "option":
				using = append(using, "option down")
			case "shift":
				using = append(using, "shift down")
			}
		}
		suffix := ""
		if len(using) > 0 {
			suffix = " using {" + strings.Join(using, ", ") + "}"
		}
		var action string
		if code, ok := macKeyCodes[base]; ok {
			action = fmt.Sprintf("key code %d", code)
		} else if len([]rune(base)) == 1 {
			action = fmt.Sprintf(`keystroke "%s"`, osaEscape(base))
		} else {
			return fmt.Errorf("알 수 없는 키 이름: %s", base)
		}
		return runIn("osascript", "-e",
			fmt.Sprintf(`tell application "System Events" to %s%s`, action, suffix))
	case "windows":
		prefix := ""
		for _, m := range mods {
			switch m {
			case "ctrl", "command": // 윈도우엔 command 가 없다 — ctrl 로 받는다
				prefix += "^"
			case "option":
				prefix += "%"
			case "shift":
				prefix += "+"
			}
		}
		key, ok := winKeyNames[base]
		if !ok {
			if len([]rune(base)) != 1 {
				return fmt.Errorf("알 수 없는 키 이름: %s", base)
			}
			key = base
		}
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command",
			"Add-Type -AssemblyName System.Windows.Forms; "+
				"[System.Windows.Forms.SendKeys]::SendWait('"+prefix+key+"')")
	default:
		if hasBin("xdotool") {
			var xs []string
			for _, m := range mods {
				switch m {
				case "ctrl", "command":
					xs = append(xs, "ctrl")
				case "option":
					xs = append(xs, "alt")
				case "shift":
					xs = append(xs, "shift")
				}
			}
			xs = append(xs, base)
			return runIn("xdotool", "key", "--clearmodifiers", strings.Join(xs, "+"))
		}
		return errNoLinuxInput()
	}
}

func injectScroll(x, y int, dir string, amount int, positioned bool) error {
	switch runtime.GOOS {
	case "darwin":
		// System Events 엔 스크롤이 없다 — 방향키/페이지키로 대신한다(대부분의 목록·문서에서 통한다).
		key := map[string]string{"down": "pagedown", "up": "pageup", "left": "left", "right": "right"}[dir]
		if key == "" {
			key = "pagedown"
		}
		reps := amount / 5
		if reps < 1 {
			reps = 1
		}
		for i := 0; i < reps; i++ {
			if err := injectKey(key); err != nil {
				return err
			}
		}
		return nil
	case "windows":
		delta := 120 * amount
		if dir == "down" {
			delta = -delta
		}
		ps := winUser32Prelude
		if positioned {
			ps += fmt.Sprintf("[IB]::SetCursorPos(%d,%d); Start-Sleep -m 40; ", x, y)
		}
		// MOUSEEVENTF_WHEEL=0x0800, HWHEEL=0x1000
		ev := "0x0800"
		if dir == "left" || dir == "right" {
			ev = "0x1000"
			if dir == "left" {
				delta = -120 * amount
			} else {
				delta = 120 * amount
			}
		}
		ps += fmt.Sprintf("[IB]::mouse_event(%s,0,0,%d,0)", ev, delta)
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command", ps)
	default:
		if hasBin("xdotool") {
			btn := map[string]string{"up": "4", "down": "5", "left": "6", "right": "7"}[dir]
			if btn == "" {
				btn = "5"
			}
			args := []string{}
			if positioned {
				args = append(args, "mousemove", strconv.Itoa(x), strconv.Itoa(y))
			}
			args = append(args, "click", "--repeat", strconv.Itoa(amount), btn)
			return runIn("xdotool", args...)
		}
		return errNoLinuxInput()
	}
}

func injectDrag(x1, y1, x2, y2 int) error {
	switch runtime.GOOS {
	case "darwin":
		if hasBin("cliclick") {
			return runIn("cliclick",
				fmt.Sprintf("m:%d,%d", x1, y1), fmt.Sprintf("dd:%d,%d", x1, y1),
				fmt.Sprintf("m:%d,%d", x2, y2), fmt.Sprintf("du:%d,%d", x2, y2))
		}
		return fmt.Errorf("맥에서 드래그는 cliclick 이 필요합니다(brew install cliclick)")
	case "windows":
		ps := winUser32Prelude +
			fmt.Sprintf("[IB]::SetCursorPos(%d,%d); Start-Sleep -m 60; ", x1, y1) +
			"[IB]::mouse_event(0x0002,0,0,0,0); Start-Sleep -m 60; " +
			fmt.Sprintf("[IB]::SetCursorPos(%d,%d); Start-Sleep -m 120; ", x2, y2) +
			"[IB]::mouse_event(0x0004,0,0,0,0)"
		return runIn("powershell", "-NoProfile", "-NonInteractive", "-Command", ps)
	default:
		if hasBin("xdotool") {
			return runIn("xdotool", "mousemove", strconv.Itoa(x1), strconv.Itoa(y1),
				"mousedown", "1", "mousemove", strconv.Itoa(x2), strconv.Itoa(y2), "mouseup", "1")
		}
		return errNoLinuxInput()
	}
}

// winUser32Prelude — PowerShell 에 user32 를 한 번 붙이는 서두. 여러 번 붙이면 타입 중복
// 오류가 나므로 존재 확인 후 정의한다(한 프로세스에서 여러 명령이 이어질 수 있다).
const winUser32Prelude = "if (-not ([System.Management.Automation.PSTypeName]'IB').Type) { " +
	"Add-Type -Name IB -Namespace '' -MemberDefinition '" +
	"[DllImport(\"user32.dll\")] public static extern bool SetCursorPos(int X, int Y); " +
	"[DllImport(\"user32.dll\")] public static extern void mouse_event(uint f, uint dx, uint dy, int d, int e);" +
	"' }; "

func errNoLinuxInput() error {
	return fmt.Errorf("이 PC 에 입력 도구가 없습니다 — xdotool(X11) 또는 ydotool(Wayland) 설치가 필요합니다")
}

// inputPermissionHint — 입력 주입은 OS 가 막는 게 정상이다(악성 프로그램도 같은 문을 쓴다).
// 실패를 '고장'으로 오독하지 않게 그 PC 에서 무엇을 허용해야 하는지 정확히 알린다.
func inputPermissionHint() string {
	switch runtime.GOOS {
	case "darwin":
		return "맥이면 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서 이 헬퍼(또는 실행한 터미널)를 허용한 뒤 헬퍼를 재실행하세요."
	case "windows":
		return "관리자 권한으로 뜬 창에는 일반 권한 프로세스가 입력을 넣을 수 없습니다(UIPI) — 헬퍼를 관리자로 실행해야 할 수 있습니다."
	default:
		return "그래픽 세션(X11/Wayland) 접근 권한을 확인하세요."
	}
}
