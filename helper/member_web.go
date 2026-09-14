package main

import (
	"crypto/rand"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// member_app.html은 scripts/build_member_shell.py 파생물이다(공통 렌더러 단일 소스).
//
//go:embed member_app.html
var memberHTML string

func randomToken() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func (m *MemberRuntime) serve() error {
	u, err := url.Parse(m.cfg.Base)
	if err != nil {
		return err
	}
	if u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost")) {
		return fmt.Errorf("허브는 HTTPS 주소여야 합니다")
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	origin := "http://" + ln.Addr().String()
	m.localURL = origin
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		io.WriteString(w, memberHTML)
	})
	mux.HandleFunc("/member/", func(w http.ResponseWriter, r *http.Request) {
		if r.Host != ln.Addr().String() || (r.Header.Get("Origin") != "" && r.Header.Get("Origin") != origin) || r.Header.Get("X-Member-Token") != m.token {
			http.Error(w, "unauthorized", 403)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		if r.Method == "GET" && r.URL.Path == "/member/approvals" {
			m.mu.Lock()
			items := []*Approval{}
			for _, a := range m.approvals {
				items = append(items, a)
			}
			m.mu.Unlock()
			json.NewEncoder(w).Encode(items)
			return
		}
		if r.Method == "GET" && r.URL.Path == "/member/history" {
			json.NewEncoder(w).Encode(m.store.recall("", 40))
			return
		}
		if r.Method == "GET" && r.URL.Path == "/member/results" {
			json.NewEncoder(w).Encode(m.store.pendingResults())
			return
		}
		if r.Method != "POST" {
			http.Error(w, "method", 405)
			return
		}
		var body map[string]interface{}
		if err := json.NewDecoder(io.LimitReader(r.Body, 1024*1024)).Decode(&body); err != nil {
			http.Error(w, "json", 400)
			return
		}
		switch r.URL.Path {
		case "/member/approve":
			key, _ := body["key"].(string)
			ok, _ := body["allow"].(bool)
			m.mu.Lock()
			a := m.approvals[key]
			m.mu.Unlock()
			if a == nil {
				http.Error(w, "없거나 종료된 승인", 404)
				return
			}
			select {
			case a.answer <- ok:
			default:
			}
			json.NewEncoder(w).Encode(map[string]bool{"success": true})
		case "/member/chat", "/member/close", "/member/profile":
			target := map[string]string{"/member/chat": "/m/chat", "/member/close": "/m/session/close", "/member/profile": "/m/profile"}[r.URL.Path]
			// 키와 신원은 로컬 설정만 소유한다. 브라우저 입력은 메시지뿐이다.
			request := map[string]interface{}{"key": m.cfg.Key}
			if target == "/m/chat" {
				request["message"] = body["message"]
			}
			var out map[string]interface{}
			c := *client
			c.Timeout = 240 * time.Second
			raw, _ := json.Marshal(request)
			req, _ := http.NewRequestWithContext(r.Context(), "POST", m.cfg.Base+target, strings.NewReader(string(raw)))
			req.Header.Set("Content-Type", "application/json")
			resp, err := c.Do(req)
			if err != nil {
				json.NewEncoder(w).Encode(errResult("connection", "연결이 끊겼습니다. 결과 목록에서 상태를 확인하세요"))
				return
			}
			defer resp.Body.Close()
			if err = json.NewDecoder(io.LimitReader(resp.Body, 2*1024*1024)).Decode(&out); err != nil {
				out = errResult("protocol", "응답 파싱 실패")
			}
			json.NewEncoder(w).Encode(out)
		case "/member/export":
			path, _ := body["path"].(string)
			json.NewEncoder(w).Encode(m.export(path)) // 로컬 화면에서 직접 누른 내보내기
		default:
			http.NotFound(w, r)
		}
	})
	m.server = &http.Server{Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	go func() { _ = m.server.Serve(ln) }()
	fmt.Printf("회원 화면: %s/#%s\n", origin, m.token)
	// 브라우저에는 로컬 한시 토큰만 전달한다. limb key는 URL·HTML에 넣지 않는다.
	if os.Getenv("INDIEBIZ_MEMBER_NO_BROWSER") != "1" {
		go memberOpen(Command{Op: "open", URL: origin + "/#" + m.token})
	}
	return nil
}
