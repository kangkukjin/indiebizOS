package main

import (
	"fmt"
	"net/url"
	"time"
)

// 승인된 재생 명령만 로컬 번들 화면이 받아 실행한다. 허브는 HTML을 공급하지 않는다.
type MemberMedia struct {
	Command Command `json:"command"`
	Claimed bool    `json:"-"`
	answer  chan map[string]interface{}
}

func (m *MemberRuntime) media(c Command) map[string]interface{} {
	if c.Action == "" {
		c.Action = "play"
	}
	switch c.Action {
	case "play", "stop", "status", "volume":
	default:
		return errResult("unsupported_action", "지원하지 않는 재생 동작")
	}
	if c.Volume != nil && (*c.Volume < 0 || *c.Volume > 100) {
		return errResult("volume", "볼륨은 0~100입니다")
	}
	if c.Action == "play" {
		u, err := url.Parse(c.URL)
		if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
			return errResult("url", "HTTP(S) 스트림 주소가 필요합니다")
		}
	}
	pending := &MemberMedia{Command: c, answer: make(chan map[string]interface{}, 1)}
	m.mu.Lock()
	m.mediaPending = pending
	m.mu.Unlock()
	defer func() {
		m.mu.Lock()
		if m.mediaPending == pending {
			m.mediaPending = nil
		}
		m.mu.Unlock()
	}()
	select {
	case result := <-pending.answer:
		return result
	case <-time.After(30 * time.Second):
		return errResult("result_unknown", "로컬 재생 화면에서 결과를 확인하세요. 자동 재실행하지 않습니다")
	}
}
func (m *MemberRuntime) claimMedia(key string) interface{} {
	m.mu.Lock()
	defer m.mu.Unlock()
	p := m.mediaPending
	if p == nil || p.Claimed || p.Command.RequestKey != key {
		return errResult("not_found", "없거나 이미 전달된 재생 명령")
	}
	p.Claimed = true
	return map[string]interface{}{"success": true, "command": p.Command}
}
func (m *MemberRuntime) mediaResult(key string, result map[string]interface{}) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	p := m.mediaPending
	if p == nil || !p.Claimed || p.Command.RequestKey != key {
		return fmt.Errorf("종료된 재생 명령")
	}
	select {
	case p.answer <- result:
	default:
	}
	return nil
}
