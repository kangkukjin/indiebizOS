package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func mediaTestEnvelope(purpose string, extra map[string]interface{}) string {
	sid := residentID()
	body := map[string]interface{}{"op": "media_session", "resident": true, "generation": "generation", "session_id": sid,
		"grant":   map[string]interface{}{"session_id": sid, "role": "device", "device": "pc-1", "tracks": []string{"v0"}, "expires_at": 1.0e12, "token": "tok"},
		"purpose": purpose, "tracks": []map[string]interface{}{{"id": "v0", "kind": "video", "source": "camera", "from": "device", "to": "hub"}},
		"lease":  map[string]interface{}{"lease_s": 20, "keepalive_s": 5, "reconnect_s": 30},
		"stream": map[string]interface{}{"url": "wss://hub.example/limb/resident/media/" + sid}, "timeout": 86400}
	for k, v := range extra {
		body[k] = v
	}
	b, _ := json.Marshal(body)
	return string(b)
}

func TestMediaEnvelopeParse(t *testing.T) {
	env, code, err := parseMediaEnvelope(mediaTestEnvelope("camera", nil))
	if err != nil {
		t.Fatal(code, err)
	}
	if env.role() != "device" || env.Lease.KeepaliveS != 5 || !env.direction().SendVideo || env.direction().RecvAudio {
		t.Fatalf("unexpected parse: %+v", env)
	}
	// registration generation string must not collide with negotiation generation
	var extra struct {
		Generation string `json:"generation"`
	}
	if json.Unmarshal([]byte(mediaTestEnvelope("camera", nil)), &extra) != nil || extra.Generation != "generation" {
		t.Fatal("registration generation lost")
	}
}

func TestMediaEnvelopeRefusals(t *testing.T) {
	cases := []struct {
		name, code string
		body       string
	}{
		{"bad purpose", "unsupported_track", mediaTestEnvelope("teleport", nil)},
		{"grant for other session", "permission_required", mediaTestEnvelope("camera", map[string]interface{}{"grant": map[string]interface{}{"session_id": residentID(), "role": "device", "token": "x"}})},
		{"no token", "permission_required", strings.Replace(mediaTestEnvelope("camera", nil), `"token":"tok"`, `"token":""`, 1)},
		{"playback without content", "content_unavailable", mediaTestEnvelope("playback", nil)},
		{"relative content path", "content_unavailable", mediaTestEnvelope("playback", map[string]interface{}{"content": map[string]interface{}{"path": "song.mp3"}})},
		{"volume out of range", "invalid_command", mediaTestEnvelope("playback", map[string]interface{}{"content": map[string]interface{}{"url": "/media/content/ab", "volume": 140}})},
		{"relative ffmpeg_path", "invalid_command", mediaTestEnvelope("camera", map[string]interface{}{"ffmpeg_path": "bin/ffmpeg"})},
		{"plain ws stream", "invalid_command", mediaTestEnvelope("camera", map[string]interface{}{"stream": map[string]interface{}{"url": "ws://hub.example/x"}})},
		{"bad track kind", "unsupported_track", mediaTestEnvelope("camera", map[string]interface{}{"tracks": []map[string]interface{}{{"kind": "smell"}}})},
		{"device flag injection", "unsupported_track", mediaTestEnvelope("camera", map[string]interface{}{"tracks": []map[string]interface{}{{"kind": "video", "device": "-f evil"}}})},
		{"not an envelope", "invalid_command", `{"op":"shell"}`},
	}
	for _, c := range cases {
		if _, code, err := parseMediaEnvelope(c.body); err == nil || code != c.code {
			t.Errorf("%s: got code %q err %v, want %q", c.name, code, err, c.code)
		}
	}
}

func TestMediaEnvelopeDirectionAndContentURL(t *testing.T) {
	env, _, err := parseMediaEnvelope(mediaTestEnvelope("speaker", map[string]interface{}{"tracks": []map[string]interface{}{
		{"id": "a0", "kind": "audio", "source": "mic", "from": "hub", "to": "device"},
		{"id": "v1", "kind": "video", "source": "camera", "from": "hub", "to": "device", "state": "rejected"}}}))
	if err != nil {
		t.Fatal(err)
	}
	d := env.direction()
	if !d.RecvAudio || d.RecvVideo || d.SendAudio || d.SendVideo {
		t.Fatalf("direction %+v", d)
	}
	env, _, _ = parseMediaEnvelope(mediaTestEnvelope("microphone", map[string]interface{}{"tracks": []interface{}{}}))
	if d := env.direction(); !d.SendAudio || d.SendVideo {
		t.Fatalf("purpose fallback %+v", d)
	}
	env, _, err = parseMediaEnvelope(mediaTestEnvelope("playback", map[string]interface{}{"content": map[string]interface{}{"ref": "ab", "url": "/media/content/ab", "position_s": 12.5, "volume": 70}}))
	if err != nil {
		t.Fatal(err)
	}
	u, err := env.contentURL("https://hub.example/base/")
	if err != nil || u != "https://hub.example/base/media/content/ab?token=tok" {
		t.Fatalf("content url %q %v", u, err)
	}
	if !env.Content.HasVolume || env.Content.Volume != 70 || env.Content.PositionS != 12.5 {
		t.Fatalf("content fields %+v", env.Content)
	}
	env, _, _ = parseMediaEnvelope(mediaTestEnvelope("playback", map[string]interface{}{"content": map[string]interface{}{"url": "https://radio.example/live.m3u8"}}))
	if u, _ := env.contentURL("https://hub.example"); u != "https://radio.example/live.m3u8" {
		t.Fatal("absolute url altered:", u)
	}
	env, _, _ = parseMediaEnvelope(mediaTestEnvelope("playback", map[string]interface{}{"content": map[string]interface{}{"url": "ftp://x/y"}}))
	if _, err := env.contentURL("https://hub.example"); err == nil {
		t.Fatal("ftp accepted")
	}
}

func TestMediaUpdateParse(t *testing.T) {
	u := parseMediaUpdate(json.RawMessage(`{"expected_revision":3,"changes":{"mute":true,"content":{"paused":true,"position_s":40,"volume":55}}}`))
	if u.Mute == nil || !*u.Mute || u.Paused == nil || !*u.Paused || u.PositionS == nil || *u.PositionS != 40 || u.Volume == nil || *u.Volume != 55 {
		t.Fatalf("nested: %+v", u)
	}
	u = parseMediaUpdate(json.RawMessage(`{"camera":false,"volume":500}`))
	if u.Camera == nil || *u.Camera || u.Volume != nil {
		t.Fatalf("flat: %+v", u)
	}
	if u := parseMediaUpdate(json.RawMessage(`garbage`)); u.Mute != nil || u.Paused != nil {
		t.Fatal("garbage parsed")
	}
}

// The op is refused before any parsing unless the resident envelope carries the
// current registration generation (same gate as every other resident op).
func TestMediaSessionRequiresCurrentGeneration(t *testing.T) {
	r := residentTestRuntime(t)
	body := map[string]interface{}{}
	_ = json.Unmarshal([]byte(mediaTestEnvelope("camera", nil)), &body)
	body["generation"] = "stale"
	b, _ := json.Marshal(body)
	if res := r.execute(t.Context(), Job{residentID(), string(b)}); res["error"] != "stale_registration" {
		t.Fatal(res)
	}
	delete(body, "resident")
	b, _ = json.Marshal(body)
	if res := r.execute(t.Context(), Job{residentID(), string(b)}); res["error"] != "stale_registration" {
		t.Fatal(res)
	}
}
