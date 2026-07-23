// indiebiz-helper — USB 로 낯선 PC 에 꽂아 실행하는 얇은 손발(effector).
//
// 이 프로그램은 두뇌가 아니다. 옆에 놓인 indiebiz-helper.json 에서 내 몸(허브)의 공개 주소와
// limb key 를 읽어, 허브에 **아웃바운드로** 붙는다(이 PC 방화벽·공유기 무설정). 그다음
// /limb/poll 을 롱폴로 물으며 허브가 내려보내는 셸/파일 명령을 받아 이 PC 에서 실행하고,
// 결과를 /limb/result 로 돌려준다. 판단은 전부 허브에서 일어난다 — 여긴 손발일 뿐이다.
//
// 1단계: 셸/파일만(눈 없음). 화면 캡처·GUI 조작은 후속 op 로 얹는다.
//
// 빌드(런타임 없는 단일 실행파일, 크로스컴파일):
//
//	GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-win.exe .
//	GOOS=darwin  GOARCH=arm64 go build -ldflags="-s -w" -o dist/indiebiz-helper-mac .
//	GOOS=linux   GOARCH=amd64 go build -ldflags="-s -w" -o dist/indiebiz-helper-linux .
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
	"unicode/utf8"
)

// 옆에 놓인 설정 파일 — 발급기([self:limb]{op:issue})가 USB 에 써 넣는다.
type Config struct {
	Base  string `json:"base"`  // 내 몸(허브)의 공개 주소, 예 https://mac.tailxxxx.ts.net
	Key   string `json:"key"`   // limb key (허브 비밀번호가 아니다)
	Alias string `json:"alias"` // 표시용 이름
}

// 허브가 큐(job.code)에 싣는 셸 봉투. 헬퍼가 자기 코드로 해석한다.
type Job struct {
	ID   string `json:"id"`
	Code string `json:"code"` // 아래 Command 의 JSON 문자열
}

type Command struct {
	Op      string `json:"op"`             // shell | read | write | list | info | note
	Cmd     string `json:"cmd,omitempty"`  // shell
	Path    string `json:"path,omitempty"` // read | write | list
	Content string `json:"content,omitempty"`
	Cwd     string `json:"cwd,omitempty"` // shell 작업 디렉토리
	Timeout int    `json:"timeout,omitempty"`
	Text    string `json:"text,omitempty"` // note — 허브(AI)가 이 창에 찍는 서사 한 줄
}

const (
	maxOutput  = 200 * 1024 // 결과 통화 상한(200KB) — 대용량은 파일에 두고 경로만 보고
	pollWait   = 25         // 롱폴 hold 초
	cmdTimeout = 120        // 셸 기본 타임아웃 초
)

var client = &http.Client{Timeout: 90 * time.Second}

func main() {
	enableUTF8Console() // 한국어 윈도우 CP949 콘솔에서 한글 안내문 깨짐 방지
	cfg, err := loadConfig()
	if err != nil {
		fmt.Fprintf(os.Stderr, "설정을 읽지 못했습니다: %v\n", err)
		fmt.Fprintln(os.Stderr, "이 실행파일 옆에 indiebiz-helper.json 이 있어야 합니다.")
		waitKey()
		os.Exit(1)
	}
	cfg.Base = strings.TrimRight(cfg.Base, "/")

	host := hostLabel()
	fmt.Printf("indiebiz 손발 — %s 로서 %s 에 붙는 중…\n", cfg.Alias, cfg.Base)

	// USB 더블클릭 직후 네트워크가 잠깐 흔들려도 바로 죽지 않게 — 짧은 재시도.
	var connErr error
	for attempt := 1; attempt <= 5; attempt++ {
		if connErr = connect(cfg, host); connErr == nil {
			break
		}
		if attempt < 5 {
			fmt.Printf("접속 재시도 %d/5: %v\n", attempt, connErr)
			time.Sleep(3 * time.Second)
		}
	}
	if connErr != nil {
		fmt.Fprintf(os.Stderr, "접속 실패: %v\n", connErr)
		waitKey()
		os.Exit(1)
	}

	fmt.Println("붙었습니다. 명령을 기다립니다. (창을 닫으면 손발이 떨어집니다.)")
	loop(cfg)
	fmt.Println("허브가 이 손발을 해제했습니다. 이 PC 에는 아무것도 남지 않습니다.")
	waitKey()
}

func loadConfig() (*Config, error) {
	// 실행파일과 같은 폴더의 indiebiz-helper.json 을 우선 찾는다(USB 루트).
	dir := "."
	if exe, err := os.Executable(); err == nil {
		dir = filepath.Dir(exe)
	}
	candidates := []string{
		filepath.Join(dir, "indiebiz-helper.json"),
		"indiebiz-helper.json",
	}
	var lastErr error
	for _, p := range candidates {
		b, err := os.ReadFile(p)
		if err != nil {
			lastErr = err
			continue
		}
		var c Config
		if err := json.Unmarshal(b, &c); err != nil {
			return nil, fmt.Errorf("%s 파싱 오류: %w", p, err)
		}
		if c.Base == "" || c.Key == "" {
			return nil, fmt.Errorf("%s 에 base 와 key 가 모두 필요합니다", p)
		}
		return &c, nil
	}
	return nil, lastErr
}

func connect(cfg *Config, host string) error {
	body := map[string]string{"key": cfg.Key, "host": host}
	var resp struct {
		Success  bool   `json:"success"`
		Error    string `json:"error"`
		Alias    string `json:"alias"`
		Approved bool   `json:"approved"`
	}
	if err := postJSON(cfg.Base+"/limb/connect", body, &resp); err != nil {
		return err
	}
	if !resp.Success {
		return fmt.Errorf("%s", orDefault(resp.Error, "거부됨"))
	}
	if !resp.Approved {
		fmt.Println("아직 승인 대기 중입니다 — 허브에서 이 손발을 승인하면 명령이 시작됩니다.")
	}
	return nil
}

func loop(cfg *Config) {
	backoff := time.Second
	for {
		jobs, approved, err := poll(cfg)
		if err != nil {
			// 네트워크 흔들림 — 백오프 후 재시도(허브가 잠깐 꺼져도 되살아나면 재개).
			time.Sleep(backoff)
			if backoff < 30*time.Second {
				backoff *= 2
			}
			continue
		}
		backoff = time.Second
		if !approved {
			time.Sleep(5 * time.Second) // 승인 전엔 조용히 재시도
			continue
		}
		for _, j := range jobs {
			res := runJob(j)
			// 실행은 이미 끝났으므로 회신만 실패하면 결과가 유실된다 — 짧게 재시도.
			for attempt := 0; attempt < 3; attempt++ {
				if err := postResult(cfg, j.ID, res); err == nil {
					break
				}
				time.Sleep(time.Duration(attempt+1) * 2 * time.Second)
			}
			if op, _ := res["op"].(string); op == "exit" {
				return // 허브가 해제 — loop 종료(main 이 마무리 안내)
			}
		}
	}
}

func poll(cfg *Config) ([]Job, bool, error) {
	body := map[string]interface{}{"key": cfg.Key, "wait": pollWait}
	var resp struct {
		Success  bool  `json:"success"`
		Approved bool  `json:"approved"`
		Jobs     []Job `json:"jobs"`
	}
	if err := postJSON(cfg.Base+"/limb/poll", body, &resp); err != nil {
		return nil, false, err
	}
	if !resp.Success {
		return nil, false, fmt.Errorf("poll 거부")
	}
	return resp.Jobs, resp.Approved, nil
}

func postResult(cfg *Config, jobID string, result map[string]interface{}) error {
	body := map[string]interface{}{"key": cfg.Key, "job_id": jobID, "result": result}
	return postJSON(cfg.Base+"/limb/result", body, nil)
}

// runJob — 셸 봉투를 이 PC 에서 실행하고 결과 통화를 만든다.
// 실행하는 일을 이 창에 생중계한다(에피소드 로그처럼): AI 가 이 PC 에 뭘 시키는지
// 헬퍼 창만 보고도 알 수 있게 — ◀ 명령 수신 / └ 결과 상태 / ※ 허브(AI) 서사(note).
func runJob(j Job) map[string]interface{} {
	var c Command
	if err := json.Unmarshal([]byte(j.Code), &c); err != nil {
		return errResult("bad_command", err.Error())
	}
	start := time.Now()
	var res map[string]interface{}
	switch c.Op {
	case "note":
		// 허브(AI)가 이 창에 찍는 서사 한 줄 — 실행할 것은 없다.
		fmt.Printf("[%s] ※ %s\n", ts(), c.Text)
		return map[string]interface{}{"op": "note", "ok": true}
	case "shell":
		fmt.Printf("[%s] ◀ 셸: %s\n", ts(), oneLine(c.Cmd, 160))
		res = doShell(c)
	case "read":
		fmt.Printf("[%s] ◀ 읽기: %s\n", ts(), c.Path)
		res = doRead(c)
	case "write":
		fmt.Printf("[%s] ◀ 쓰기: %s (%d바이트)\n", ts(), c.Path, len(c.Content))
		res = doWrite(c)
	case "list":
		fmt.Printf("[%s] ◀ 목록: %s\n", ts(), orDefault(c.Path, "."))
		res = doList(c)
	case "info":
		fmt.Printf("[%s] ◀ 기기 정보 조회\n", ts())
		res = doInfo()
	case "exit":
		// 허브의 원격 해제 — 결과 회신 후 loop 가 이 op 를 보고 종료한다.
		fmt.Printf("[%s] ◀ 허브의 해제 명령\n", ts())
		return map[string]interface{}{"op": "exit", "bye": true}
	default:
		return errResult("unknown_op", "알 수 없는 op: "+c.Op)
	}
	fmt.Printf("[%s]   └ %s\n", ts(), statusLine(res, time.Since(start)))
	return res
}

func ts() string { return time.Now().Format("15:04:05") }

// oneLine — 개행·연속 공백을 한 줄로 접고 n 자에서 자른다(콘솔 에코용).
func oneLine(s string, n int) string {
	s = strings.Join(strings.Fields(s), " ")
	r := []rune(s)
	if len(r) > n {
		return string(r[:n]) + "…"
	}
	return s
}

// statusLine — 결과 통화를 사람이 읽는 한 줄 상태로.
func statusLine(res map[string]interface{}, took time.Duration) string {
	if code, bad := res["error"].(string); bad {
		return fmt.Sprintf("실패: %s (%v)", orDefault(code, "?"), res["message"])
	}
	dur := fmt.Sprintf("%.1f초", took.Seconds())
	switch res["op"] {
	case "shell":
		line := fmt.Sprintf("완료 exit %v (%s)", res["exit"], dur)
		if t, _ := res["timeout"].(bool); t {
			line += " — 시간 초과"
		}
		return line
	case "read":
		return fmt.Sprintf("완료 %v바이트 (%s)", res["bytes"], dur)
	case "write":
		return fmt.Sprintf("완료 %v바이트 씀 (%s)", res["bytes"], dur)
	case "list":
		if files, ok := res["files"].([]map[string]interface{}); ok {
			return fmt.Sprintf("완료 %d개 항목 (%s)", len(files), dur)
		}
		return fmt.Sprintf("완료 (%s)", dur)
	case "info":
		return fmt.Sprintf("완료 %v (%s)", res["hostname"], dur)
	}
	return fmt.Sprintf("완료 (%s)", dur)
}

func doShell(c Command) map[string]interface{} {
	if strings.TrimSpace(c.Cmd) == "" {
		return errResult("empty_cmd", "cmd 가 비었습니다")
	}
	to := c.Timeout
	if to <= 0 {
		to = cmdTimeout
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(to)*time.Second)
	defer cancel()

	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		// 한국어 윈도우 cmd 는 CP949 로 출력해 JSON(UTF-8) 통화에서 한글이 전부
		// U+FFFD 로 뭉개진다 — 이 cmd 인스턴스만 UTF-8 코드페이지로 전환(best-effort:
		// 내부 명령·코드페이지를 따르는 프로그램에 유효).
		cmd = exec.CommandContext(ctx, "cmd", "/c", "chcp 65001>nul & "+c.Cmd)
	} else {
		cmd = exec.CommandContext(ctx, "sh", "-c", c.Cmd)
	}
	if c.Cwd != "" {
		cmd.Dir = c.Cwd
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()

	res := map[string]interface{}{
		"op":     "shell",
		"stdout": clip(stdout.String()),
		"stderr": clip(stderr.String()),
		"exit":   exitCode(err),
	}
	if ctx.Err() == context.DeadlineExceeded {
		res["timeout"] = true
	}
	return res
}

func doRead(c Command) map[string]interface{} {
	b, err := os.ReadFile(c.Path)
	if err != nil {
		return errResult("read_failed", err.Error())
	}
	content := string(b)
	truncated := len(b) > maxOutput
	if truncated {
		content = clip(content) // UTF-8 경계 안전 절단
	}
	return map[string]interface{}{
		"op": "read", "path": c.Path, "content": content,
		"bytes": len(b), "truncated": truncated,
	}
}

func doWrite(c Command) map[string]interface{} {
	if c.Path == "" {
		return errResult("no_path", "path 가 비었습니다")
	}
	if dir := filepath.Dir(c.Path); dir != "" {
		_ = os.MkdirAll(dir, 0o755)
	}
	if err := os.WriteFile(c.Path, []byte(c.Content), 0o644); err != nil {
		return errResult("write_failed", err.Error())
	}
	return map[string]interface{}{"op": "write", "path": c.Path, "bytes": len(c.Content)}
}

func doList(c Command) map[string]interface{} {
	dir := c.Path
	if dir == "" {
		dir = "."
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return errResult("list_failed", err.Error())
	}
	var files []map[string]interface{}
	for _, e := range entries {
		info, _ := e.Info()
		var size int64
		var mtime string
		if info != nil {
			size = info.Size()
			mtime = info.ModTime().Format(time.RFC3339)
		}
		files = append(files, map[string]interface{}{
			"name": e.Name(), "dir": e.IsDir(), "bytes": size, "mtime": mtime,
		})
	}
	return map[string]interface{}{"op": "list", "path": dir, "files": files}
}

func doInfo() map[string]interface{} {
	cwd, _ := os.Getwd()
	host, _ := os.Hostname()
	return map[string]interface{}{
		"op": "info", "os": runtime.GOOS, "arch": runtime.GOARCH,
		"hostname": host, "cwd": cwd,
	}
}

// === 유틸 ===

func postJSON(url string, body interface{}, out interface{}) error {
	b, _ := json.Marshal(body)
	req, err := http.NewRequest("POST", url, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, maxOutput+64*1024))
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(data)))
	}
	if out != nil {
		return json.Unmarshal(data, out)
	}
	return nil
}

func clip(s string) string {
	if len(s) <= maxOutput {
		return s
	}
	// UTF-8 문자 경계에서 자른다 — 한가운데를 자르면 마지막 한글이 U+FFFD 로 깨진다.
	cut := maxOutput
	for cut > 0 && cut > maxOutput-4 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut] + "\n…(잘림)"
}

func exitCode(err error) int {
	if err == nil {
		return 0
	}
	if ee, ok := err.(*exec.ExitError); ok {
		return ee.ExitCode()
	}
	return -1
}

func errResult(code, msg string) map[string]interface{} {
	return map[string]interface{}{"error": code, "message": msg}
}

func orDefault(s, d string) string {
	if s == "" {
		return d
	}
	return s
}

func hostLabel() string {
	host, _ := os.Hostname()
	return fmt.Sprintf("%s (%s/%s)", orDefault(host, "unknown"), runtime.GOOS, runtime.GOARCH)
}

// 오류 시 창이 바로 닫히지 않게 — USB 더블클릭 실행 UX.
func waitKey() {
	fmt.Println("\n계속하려면 Enter 를 누르세요…")
	fmt.Fscanln(os.Stdin)
}
