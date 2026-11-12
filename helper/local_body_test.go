package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func resetLocalBody(t *testing.T) {
	api, probe := localBodyAPI, localBody.probe
	localBody.Lock()
	localBody.at, localBody.card = time.Time{}, nil
	localBody.Unlock()
	t.Cleanup(func() {
		localBodyAPI = api
		localBody.Lock()
		localBody.probe, localBody.at, localBody.card = probe, time.Time{}, nil
		localBody.Unlock()
	})
}

func TestLocalBodyProbeRecognizesOnlyAnIndieBizBackend(t *testing.T) {
	resetLocalBody(t)
	answer := `{"kind":"indiebiz-capability-card","action_count":58}`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/nodes/card" || r.URL.Query().Get("detail") != "summary" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte(answer))
	}))
	localBodyAPI = srv.URL
	if card := probeLocalBody(); card == nil || card["action_count"] != float64(58) {
		t.Fatalf("a responding IndieBiz backend was not recognized: %v", card)
	}
	answer = `{"status":"ok","message":"another service"}`
	if probeLocalBody() != nil {
		t.Fatal("another service on the port was reported as an IndieBiz body")
	}
	srv.Close()
	if probeLocalBody() != nil {
		t.Fatal("a closed port was reported as reachable")
	}
}

func TestLocalBodyCardIsCachedBetweenSyncs(t *testing.T) {
	resetLocalBody(t)
	calls := 0
	localBody.probe = func() map[string]interface{} { calls++; return map[string]interface{}{"kind": "card"} }
	first := localBodyCard()
	localBodyCard()
	if calls != 1 || first["kind"] != "card" {
		t.Fatalf("calls=%d card=%v", calls, first)
	}
	localBody.Lock()
	localBody.at = time.Now().Add(-31 * time.Second)
	localBody.probe = func() map[string]interface{} { calls++; return nil }
	localBody.Unlock()
	if localBodyCard() != nil || calls != 2 {
		t.Fatalf("a body that stopped answering was still reported, calls=%d", calls)
	}
}

func TestResidentCapabilitiesReportTheLocalBodyOnlyWhileItAnswers(t *testing.T) {
	resetLocalBody(t)
	r := &residentRuntime{cfg: &Config{DataDir: t.TempDir(), InstallationID: residentID()}}
	localBody.probe = func() map[string]interface{} { return nil }
	caps := r.capabilities()
	if caps["ibl"] != false || caps["card"] != nil {
		t.Fatalf("a helper-only PC reported an IBL door: ibl=%v card=%v", caps["ibl"], caps["card"])
	}
	localBody.Lock()
	localBody.at = time.Time{}
	localBody.probe = func() map[string]interface{} { return map[string]interface{}{"action_count": 58} }
	localBody.Unlock()
	caps = r.capabilities()
	if caps["ibl"] != true || caps["card"].(map[string]interface{})["action_count"] != 58 {
		t.Fatalf("ibl=%v card=%v", caps["ibl"], caps["card"])
	}
}

func TestLocalIBLHandsTheSentenceToTheLocalBodyOnce(t *testing.T) {
	resetLocalBody(t)
	posts := 0
	var got map[string]interface{}
	status, answer := http.StatusOK, `{"success":true,"value":{"message":"재생을 중지했습니다."}}`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/ibl/execute" {
			http.NotFound(w, r)
			return
		}
		posts++
		raw, _ := io.ReadAll(r.Body)
		json.Unmarshal(raw, &got)
		w.WriteHeader(status)
		w.Write([]byte(answer))
	}))
	localBodyAPI = srv.URL
	code := "#!ibl edition=2\nreturn [limbs:youtube]{op:\"stop\"}"
	out := localIBL(context.Background(), code)
	if posts != 1 || got["code"] != code || got["project_id"] != localBodyProject || out["success"] != true {
		t.Fatalf("posts=%d sent=%v out=%v", posts, got, out)
	}
	// The body's own refusal comes back as it is; the helper adds no retry.
	answer = `{"success":false,"error":"알 수 없는 액션"}`
	if out := localIBL(context.Background(), code); out["success"] != false || out["error"] != "알 수 없는 액션" || posts != 2 {
		t.Fatalf("posts=%d out=%v", posts, out)
	}
	status, answer = http.StatusServiceUnavailable, `{"detail":"restarting"}`
	if out := localIBL(context.Background(), code); out["success"] != false || out["error"] != "HTTP 503" {
		t.Fatalf("out=%v", out)
	}
	if out := localIBL(context.Background(), "  "); out["error"] != "ibl_code_required" || posts != 3 {
		t.Fatalf("empty code reached the body: posts=%d out=%v", posts, out)
	}
	srv.Close()
	if out := localIBL(context.Background(), code); out["error"] != "local_body_unreachable" {
		t.Fatalf("out=%v", out)
	}
}

func TestResidentJobWithIBLReachesTheLocalBodyThroughTheRegistrationGate(t *testing.T) {
	resetLocalBody(t)
	var got map[string]interface{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		json.Unmarshal(raw, &got)
		w.Write([]byte(`{"success":true,"value":"done"}`))
	}))
	defer srv.Close()
	localBodyAPI = srv.URL
	r := residentTestRuntime(t)
	code := "#!ibl edition=2\nreturn [self:time]{}"
	out := r.execute(context.Background(), residentTestJob(t, map[string]interface{}{"op": "ibl", "ibl": code, "timeout": 30}))
	if out["success"] != true || out["value"] != "done" || got["code"] != code {
		t.Fatalf("out=%v sent=%v", out, got)
	}
	// A sentence from a stale registration never reaches the body.
	got = nil
	stale := residentTestJob(t, map[string]interface{}{"op": "ibl", "ibl": code})
	stale.Code = `{"op":"ibl","ibl":"x","resident":true,"generation":"old"}`
	if r.execute(context.Background(), stale)["error"] != "stale_registration" || got != nil {
		t.Fatalf("stale registration reached the body: %v", got)
	}
}
