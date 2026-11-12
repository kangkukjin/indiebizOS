package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// 이 PC 의 IndieBiz OS(로컬 백엔드). 등록된 PC 에 IndieBiz OS 가 응답하면 중앙은 헬퍼로 조작하는 대신
// IBL 문장을 보내고, 헬퍼는 그 문장을 이 몸에 건넨다. 실행·검사는 이 몸의 사전이 한다.
// 설치 여부가 아니라 지금 닿는지를 신고한다 — 백엔드는 창을 닫으면 내려간다.
var localBodyAPI = "http://127.0.0.1:8765"

// 중앙의 하달은 소유자가 직접 모는 호출과 같은 자리(시스템 프로젝트)에서 돈다.
const localBodyProject = "앱모드"

var localBodyClient = &http.Client{Transport: &http.Transport{Proxy: nil}}

var localBody = struct {
	sync.Mutex
	at    time.Time
	card  map[string]interface{}
	probe func() map[string]interface{}
}{probe: probeLocalBody}

// probeLocalBody 는 로컬 백엔드의 요약 명함을 돌려준다. 다른 서비스가 같은 포트에 있으면 nil 이다.
func probeLocalBody() map[string]interface{} {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	req, e := http.NewRequestWithContext(ctx, http.MethodGet, localBodyAPI+"/nodes/card?detail=summary", nil)
	if e != nil {
		return nil
	}
	resp, e := localBodyClient.Do(req)
	if e != nil {
		return nil
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 8192))
	var card map[string]interface{}
	if resp.StatusCode != http.StatusOK || json.Unmarshal(raw, &card) != nil || card["kind"] != "indiebiz-capability-card" {
		return nil
	}
	return card
}

// localBodyCard 는 응답하는 로컬 몸의 명함(없으면 nil)이다. capabilities() 는 동기화마다 불리므로
// 30초 안의 재호출은 직전 결과를 돌려준다.
func localBodyCard() map[string]interface{} {
	localBody.Lock()
	defer localBody.Unlock()
	if localBody.at.IsZero() || time.Since(localBody.at) > 30*time.Second {
		localBody.card = localBody.probe()
		localBody.at = time.Now()
	}
	return localBody.card
}

// localIBL 은 중앙이 보낸 IBL 문장을 이 PC 의 IndieBiz OS 에 한 번 건네고 그 응답을 그대로 돌려준다.
// 결과가 불명확해도 다시 보내지 않는다.
func localIBL(ctx context.Context, code string) map[string]interface{} {
	if strings.TrimSpace(code) == "" {
		return errResult("ibl_code_required", "")
	}
	body, _ := json.Marshal(map[string]interface{}{"code": code, "project_id": localBodyProject})
	req, e := http.NewRequestWithContext(ctx, http.MethodPost, localBodyAPI+"/ibl/execute", bytes.NewReader(body))
	if e != nil {
		return errResult("local_body_unreachable", e.Error())
	}
	req.Header.Set("Content-Type", "application/json")
	resp, e := localBodyClient.Do(req)
	if e != nil {
		return errResult("local_body_unreachable", e.Error())
	}
	defer resp.Body.Close()
	const limit = 4 << 20
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if len(raw) > limit {
		return errResult("local_response_too_large", "")
	}
	var out map[string]interface{}
	if json.Unmarshal(raw, &out) != nil {
		head := string(raw)
		if len(head) > 2000 {
			head = head[:2000]
		}
		return errResult("invalid_local_response", head)
	}
	if resp.StatusCode != http.StatusOK {
		out["success"] = false
		if out["error"] == nil {
			out["error"] = fmt.Sprintf("HTTP %d", resp.StatusCode)
		}
	}
	return out
}
