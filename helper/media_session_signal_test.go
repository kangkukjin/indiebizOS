package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"time"
)

func TestMediaOutboxSeqAndGeneration(t *testing.T) {
	sid := residentID()
	o := newMediaOutbox(sid, "device", "hub", 0, "")
	f1, _ := o.frame("keepalive", map[string]interface{}{})
	f2, _ := o.frame("keepalive", map[string]interface{}{})
	if f1["seq"] != 1 || f2["seq"] != 2 || f1["generation"] != 0 || f1["v"] != 1 || f1["from"] != "device" || f1["to"] != "hub" || f1["session_id"] != sid {
		t.Fatalf("frames %v %v", f1, f2)
	}
	if f1["msg_id"] == f2["msg_id"] || len(f1["msg_id"].(string)) != 32 {
		t.Fatal("msg_id not unique")
	}
	if _, ok := f1["mac"]; ok {
		t.Fatal("mac without secret")
	}
	if o.setGeneration(-1) {
		t.Fatal("lower generation adopted")
	}
	if !o.setGeneration(2) {
		t.Fatal("higher generation refused")
	}
	f3, _ := o.frame("state", map[string]interface{}{"state": "active"})
	if f3["generation"] != 2 || f3["seq"] != 1 {
		t.Fatalf("seq not restarted: %v", f3)
	}
	if !o.setGeneration(2) {
		t.Fatal("same generation refused")
	}
	if f4, _ := o.frame("keepalive", map[string]interface{}{}); f4["seq"] != 2 {
		t.Fatal("same generation restarted seq")
	}
	var p map[string]interface{}
	if json.Unmarshal(f3["payload"].(json.RawMessage), &p) != nil || p["state"] != "active" {
		t.Fatal("payload")
	}
}

func TestMediaOutboxMAC(t *testing.T) {
	o := newMediaOutbox(residentID(), "device", "hub", 0, "s3cret")
	f, _ := o.frame("keepalive", map[string]interface{}{})
	mac, _ := f["mac"].(string)
	if len(mac) != 64 {
		t.Fatal("mac missing")
	}
	clean := map[string]interface{}{}
	for k, v := range f {
		if k != "mac" {
			clean[k] = v
		}
	}
	canonical, _ := json.Marshal(clean) // sorted keys, no whitespace
	m := hmac.New(sha256.New, []byte("s3cret"))
	m.Write(canonical)
	if hex.EncodeToString(m.Sum(nil)) != mac {
		t.Fatal("mac does not verify")
	}
}

func TestMediaInboxFiltering(t *testing.T) {
	sid := residentID()
	in := newMediaInbox(sid, 0)
	now := time.Now()
	in.now = func() time.Time { return now }
	frame := func(gen, seq int, exp float64) *mediaSignal {
		return &mediaSignal{V: 1, SessionID: sid, Generation: gen, Seq: seq, ExpiresAt: exp, Type: "candidate"}
	}
	if !in.accept(&mediaSignal{Type: "heartbeat"}) {
		t.Fatal("transport frame dropped")
	}
	if !in.accept(frame(0, 1, 0)) || in.accept(frame(0, 1, 0)) {
		t.Fatal("replay accepted")
	}
	if !in.accept(frame(0, 3, 0)) || in.accept(frame(0, 2, 0)) {
		t.Fatal("old seq accepted")
	}
	if in.accept(frame(0, 4, float64(now.Add(-time.Second).UnixNano())/1e9)) {
		t.Fatal("expired accepted")
	}
	if !in.accept(frame(0, 4, float64(now.Add(time.Minute).UnixNano())/1e9)) {
		t.Fatal("fresh refused")
	}
	if !in.accept(frame(1, 1, 0)) || in.current() != 1 || in.accept(frame(0, 9, 0)) {
		t.Fatal("generation handling")
	}
	other := frame(1, 2, 0)
	other.SessionID = residentID()
	if in.accept(other) {
		t.Fatal("other session accepted")
	}
	if in.accept(&mediaSignal{V: 2, SessionID: sid, Generation: 1, Seq: 2}) {
		t.Fatal("unknown version accepted")
	}
}

const mediaTestSDP = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=fingerprint:sha-256 AB:CD:EF:01\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=rtpmap:111 opus/48000/2\r\nm=video 9 UDP/TLS/RTP/SAVPF 102 127\r\na=rtpmap:102 H264/90000\r\na=rtpmap:127 H264/90000\r\n"

func TestMediaFingerprintAndPayloadTypes(t *testing.T) {
	if mediaFingerprint(mediaTestSDP) != "sha-256 AB:CD:EF:01" {
		t.Fatal(mediaFingerprint(mediaTestSDP))
	}
	if !mediaFingerprintMatches(mediaTestSDP, "sha-256 ab:cd:ef:01") || !mediaFingerprintMatches(mediaTestSDP, "") || mediaFingerprintMatches(mediaTestSDP, "sha-256 00:11") {
		t.Fatal("fingerprint comparison")
	}
	if opus, h264 := mediaSDPPayloadTypes(mediaTestSDP); opus != 111 || h264 != 102 {
		t.Fatal(opus, h264)
	}
}

func TestMediaQualityMapping(t *testing.T) {
	t0 := time.Now()
	prev := mediaStatsSample{At: t0, Bytes: 1000, Packets: 10, PacketsLost: 0}
	cur := mediaStatsSample{At: t0.Add(2 * time.Second), Bytes: 1000 + 250000, Packets: 110, PacketsLost: 5, RTT: 37 * time.Millisecond,
		Jitter: 0.0042, Width: 1280, Height: 720, FPS: 30}
	q := mediaQualityFrom(prev, cur)
	if q.BitrateKbps != 1000 || q.RTTms != 37 || q.JitterMs != 4.2 || q.Width != 1280 || q.Height != 720 || q.FPS != 30 || q.Dropped != 5 {
		t.Fatalf("%+v", q)
	}
	if q.Loss != 0.048 { // 5 lost of 100 delivered + 5 lost
		t.Fatalf("loss %v", q.Loss)
	}
	cur.FractionLost = 0.25
	if q := mediaQualityFrom(prev, cur); q.Loss != 0.25 {
		t.Fatal("receiver-report loss not preferred")
	}
	if q := mediaQualityFrom(mediaStatsSample{}, cur); q.BitrateKbps != 0 {
		t.Fatal("bitrate from a single sample")
	}
	b, _ := json.Marshal(q)
	for _, key := range []string{"rtt_ms", "loss", "jitter_ms", "bitrate_kbps", "fps", "width", "height", "dropped"} {
		if !json.Valid(b) || !containsKey(b, key) {
			t.Fatal("contract key missing:", key)
		}
	}
	if mediaPath("host", "srflx") != "direct" || mediaPath("relay", "host") != "relay" || mediaPath("host", "relay") != "relay" || mediaPath("", "") != "" {
		t.Fatal("path mapping")
	}
}

func containsKey(b []byte, key string) bool {
	var m map[string]interface{}
	_ = json.Unmarshal(b, &m)
	_, ok := m[key]
	return ok
}

func TestMediaStatePayloadAndCandidate(t *testing.T) {
	q := mediaQuality{RTTms: 1}
	p := mediaStatePayload("active", "direct", &q, nil, map[string]interface{}{"playing": true, "position_s": 3.5})
	if p["state"] != "active" || p["path"] != "direct" || p["playing"] != true || p["position_s"] != 3.5 {
		t.Fatalf("%v", p)
	}
	if _, ok := p["needs_local_action"]; ok {
		t.Fatal("nla present")
	}
	p = mediaStatePayload("needs_local_action", "", nil, map[string]interface{}{"code": "ffmpeg_missing", "message": "x"}, nil)
	if p["needs_local_action"].(map[string]interface{})["code"] != "ffmpeg_missing" {
		t.Fatal(p)
	}
	mid := "0"
	c, ok := parseMediaCandidate(json.RawMessage(`{"candidate":"candidate:1 1 udp 2 10.0.0.2 5000 typ host","sdpMid":"0","sdpMLineIndex":0}`))
	if !ok || c.SDPMid == nil || *c.SDPMid != mid || c.SDPMLineIndex == nil {
		t.Fatalf("flat %+v", c)
	}
	c, ok = parseMediaCandidate(json.RawMessage(`{"candidate":{"candidate":"candidate:1 1 udp 2 10.0.0.2 5000 typ host","sdpMid":"1"}}`))
	if !ok || *c.SDPMid != "1" {
		t.Fatalf("nested %+v", c)
	}
	if _, ok := parseMediaCandidate(json.RawMessage(`{}`)); ok {
		t.Fatal("empty accepted")
	}
}
