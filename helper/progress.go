// progress.go — 긴 명령의 중간 경과 중계.
//
// 왜 필요한가: 설치·빌드는 all-or-nothing 이었다. 30분짜리 명령이 도는 동안 허브는
// 깜깜했고, AI 는 "돌고 있는지 멎었는지"를 구별할 방법이 없어 그냥 기다리거나 —
// 더 나쁘게 — 같은 명령을 다시 보냈다(이중 실행). 중간 출력이 보이면 진행 여부를
// 판단하고, 잘못 가고 있으면 일찍 방향을 바꿀 수 있다.
//
// 설계: 명령이 짧으면 아무것도 안 보낸다(첫 중계는 progressFirstDelay 이후). 그래서
// 흔한 짧은 명령엔 비용이 0이고, 오래 끄는 명령만 스스로 말을 하기 시작한다.
package main

import (
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

const (
	progressFirstDelay = 6 * time.Second  // 이보다 짧게 끝나는 명령은 중계 안 함
	progressInterval   = 6 * time.Second  // 이후 중계 주기
	progressTailBytes  = 3 * 1024         // 한 번에 올리는 꼬리 크기
)

type progressReporter struct {
	jobID string
	mu    sync.Mutex
	buf   []byte
	total int
	done  chan struct{}
	once  sync.Once
}

func newProgressReporter(jobID string) *progressReporter {
	p := &progressReporter{jobID: jobID, done: make(chan struct{})}
	if jobID != "" && hubCfg != nil {
		go p.loop()
	}
	return p
}

// Write — io.Writer. 꼬리만 들고 있는다(전체 출력은 어차피 최종 결과가 나른다).
func (p *progressReporter) Write(b []byte) (int, error) {
	p.mu.Lock()
	p.total += len(b)
	p.buf = append(p.buf, b...)
	if len(p.buf) > progressTailBytes {
		p.buf = p.buf[len(p.buf)-progressTailBytes:]
	}
	p.mu.Unlock()
	return len(b), nil
}

func (p *progressReporter) stop() {
	p.once.Do(func() { close(p.done) })
}

func (p *progressReporter) loop() {
	select {
	case <-p.done:
		return // 짧게 끝났다 — 아무것도 안 보낸다
	case <-time.After(progressFirstDelay):
	}
	t := time.NewTicker(progressInterval)
	defer t.Stop()
	p.send()
	for {
		select {
		case <-p.done:
			return
		case <-t.C:
			p.send()
		}
	}
}

func (p *progressReporter) send() {
	p.mu.Lock()
	tail := string(p.buf)
	total := p.total
	p.mu.Unlock()

	// 표식은 내부 배관이라 중간 경과에 노출하지 않는다(AI 가 이걸 진짜 출력으로 오해하면
	// 엉뚱한 판단을 한다). 꼬리라 앞이 잘려 UTF-8 이 깨질 수 있으니 그것도 정리.
	if i := strings.Index(tail, envMarker); i >= 0 {
		tail = tail[:i]
	}
	if i := strings.Index(tail, cwdMarker); i >= 0 {
		tail = tail[:i]
	}
	tail = trimBrokenUTF8Prefix(tail)

	body := map[string]interface{}{
		"key": hubCfg.Key, "job_id": p.jobID,
		"tail": tail, "bytes": total, "running": true,
	}
	_ = postJSON(hubCfg.Base+"/limb/progress", body, nil) // best-effort — 실패해도 명령은 계속
}

// trimBrokenUTF8Prefix — 꼬리 자르기로 앞부분의 한글이 반토막 났으면 그 조각을 버린다.
func trimBrokenUTF8Prefix(s string) string {
	for i := 0; i < len(s) && i < 4; i++ {
		if utf8.RuneStart(s[i]) && utf8.ValidString(s[i:]) {
			return s[i:]
		}
	}
	if utf8.ValidString(s) {
		return s
	}
	return strings.ToValidUTF8(s, "")
}
