//go:build !legacy

package main

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v4"
)

// A fake hub: the media WS endpoint (§4 auth, §6 ready) plus, for speaker, the
// offerer side of the WebRTC leg. It records every device frame.
type mediaFakeHub struct {
	t      *testing.T
	srv    *httptest.Server
	sid    string
	mu     sync.Mutex
	frames []mediaSignal
	auth   map[string]interface{}
	ready  map[string]interface{}
	raw    []string
	seq    int
	handle func(h *mediaFakeHub, ws *websocket.Conn)
	done   chan struct{} // closed when the handler returns (happens-before for its flags)
}

func newMediaFakeHub(t *testing.T, sid string, handle func(h *mediaFakeHub, ws *websocket.Conn)) *mediaFakeHub {
	h := &mediaFakeHub{t: t, sid: sid, handle: handle, done: make(chan struct{})}
	upgrader := websocket.Upgrader{}
	h.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/limb/resident/media/"+sid {
			http.Error(w, "wrong path", 404)
			return
		}
		ws, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer ws.Close()
		var auth map[string]interface{}
		if ws.ReadJSON(&auth) != nil {
			return
		}
		h.mu.Lock()
		h.auth = auth
		h.mu.Unlock()
		if auth["key"] != "limb_key" || auth["grant"] == nil {
			_ = ws.WriteJSON(map[string]string{"type": "error", "error": "permission_required"})
			return
		}
		_ = ws.WriteJSON(map[string]string{"type": "ready"})
		var ready map[string]interface{}
		if ws.ReadJSON(&ready) != nil {
			return
		}
		h.mu.Lock()
		h.ready = ready
		h.mu.Unlock()
		defer close(h.done)
		handle(h, ws)
	}))
	t.Cleanup(h.srv.Close)
	return h
}

// wait blocks until the hub handler has returned (the device closed its socket).
func (h *mediaFakeHub) wait(t *testing.T) {
	t.Helper()
	select {
	case <-h.done:
	case <-time.After(20 * time.Second):
		t.Fatal("hub handler still running")
	}
}

func (h *mediaFakeHub) url() string {
	return "ws" + strings.TrimPrefix(h.srv.URL, "http") + "/limb/resident/media/" + h.sid
}

// next reads one device frame (recording it) or fails after the timeout.
func (h *mediaFakeHub) next(ws *websocket.Conn, timeout time.Duration) (mediaSignal, bool) {
	_ = ws.SetReadDeadline(time.Now().Add(timeout))
	_, raw, err := ws.ReadMessage()
	if err != nil {
		return mediaSignal{}, false
	}
	var f mediaSignal
	_ = json.Unmarshal(raw, &f)
	h.mu.Lock()
	h.frames = append(h.frames, f)
	h.raw = append(h.raw, string(raw))
	h.mu.Unlock()
	return f, true
}

func (h *mediaFakeHub) send(ws *websocket.Conn, kind string, payload interface{}) {
	h.seq++
	body, _ := json.Marshal(payload)
	_ = ws.WriteJSON(map[string]interface{}{"v": 1, "session_id": h.sid, "msg_id": residentID(), "from": "hub", "to": "device",
		"generation": 0, "seq": h.seq, "expires_at": float64(time.Now().Add(time.Minute).UnixNano()) / 1e9, "type": kind, "payload": json.RawMessage(body)})
}

func mediaTestRuntime(t *testing.T) *residentRuntime {
	r := residentTestRuntime(t)
	r.cfg.Key, r.cfg.Base = "limb_key", "https://hub.example"
	return r
}

func mediaSilentWAV(t *testing.T) string {
	path := filepath.Join(t.TempDir(), "silence.wav")
	const rate, seconds = 8000, 3
	data := make([]byte, rate*2*seconds)
	header := make([]byte, 44)
	copy(header[0:], "RIFF")
	binary.LittleEndian.PutUint32(header[4:], uint32(36+len(data)))
	copy(header[8:], "WAVEfmt ")
	binary.LittleEndian.PutUint32(header[16:], 16)
	binary.LittleEndian.PutUint16(header[20:], 1)
	binary.LittleEndian.PutUint16(header[22:], 1)
	binary.LittleEndian.PutUint32(header[24:], rate)
	binary.LittleEndian.PutUint32(header[28:], rate*2)
	binary.LittleEndian.PutUint16(header[32:], 2)
	binary.LittleEndian.PutUint16(header[34:], 16)
	copy(header[36:], "data")
	binary.LittleEndian.PutUint32(header[40:], uint32(len(data)))
	if err := os.WriteFile(path, append(header, data...), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func mediaTestJob(t *testing.T, purpose string, hub *mediaFakeHub, extra map[string]interface{}) Job {
	body := map[string]interface{}{}
	_ = json.Unmarshal([]byte(mediaTestEnvelope(purpose, extra)), &body)
	body["session_id"] = hub.sid
	body["grant"].(map[string]interface{})["session_id"] = hub.sid
	body["stream"] = map[string]interface{}{"url": hub.url()}
	body["lease"] = map[string]interface{}{"lease_s": 6, "keepalive_s": 1, "reconnect_s": 3}
	b, _ := json.Marshal(body)
	return Job{residentID(), string(b)}
}

// The token travels only in the auth frame; every §3 frame carries the device
// role, the session and an increasing seq.
func (h *mediaFakeHub) assertFrames(t *testing.T) {
	t.Helper()
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.auth["installation_id"] == nil || h.auth["grant"].(map[string]interface{})["token"] != "tok" {
		t.Fatalf("auth frame %v", h.auth)
	}
	if h.ready["type"] != "ready" || h.ready["capabilities"] == nil {
		t.Fatalf("device ready %v", h.ready)
	}
	caps := h.ready["capabilities"].(map[string]interface{})
	if caps["engine"] != mediaEngineVersion() || caps["playback"] != true {
		t.Fatalf("capabilities %v", caps)
	}
	last := 0
	for i, f := range h.frames {
		if f.V != 1 || f.SessionID != h.sid || f.From != "device" || f.To != "hub" || len(f.MsgID) != 32 || f.ExpiresAt == 0 {
			t.Fatalf("frame %d malformed: %+v", i, f)
		}
		if f.Seq <= last {
			t.Fatalf("seq not increasing at frame %d: %+v", i, f)
		}
		last = f.Seq
		if strings.Contains(h.raw[i], "tok") {
			t.Fatalf("grant token leaked into frame %d", i)
		}
	}
}

func (h *mediaFakeHub) count(kind string) int {
	h.mu.Lock()
	defer h.mu.Unlock()
	n := 0
	for _, f := range h.frames {
		if f.Type == kind {
			n++
		}
	}
	return n
}

func TestMediaSessionPlaybackOverHubWS(t *testing.T) {
	r := mediaTestRuntime(t)
	sid := residentID()
	var pausedSeen, ended bool
	hub := newMediaFakeHub(t, sid, func(h *mediaFakeHub, ws *websocket.Conn) {
		deadline := time.Now().Add(25 * time.Second)
		sentUpdate, sentEnd := false, false
		for time.Now().Before(deadline) {
			f, ok := h.next(ws, 25*time.Second)
			if !ok {
				ended = sentEnd
				return
			}
			var p map[string]interface{}
			_ = json.Unmarshal(f.Payload, &p)
			switch f.Type {
			case "state":
				if nla, ok := p["needs_local_action"]; ok && nla != nil {
					sentEnd = true
					h.send(ws, "end", map[string]string{"reason": "hub_end"})
					continue
				}
				if p["playing"] == true && !sentUpdate {
					sentUpdate = true
					h.send(ws, "update", map[string]interface{}{"expected_revision": 1, "changes": map[string]interface{}{"content": map[string]interface{}{"paused": true, "volume": 40}}})
					continue
				}
				if sentUpdate && (p["paused"] == true || p["control"] == false) && h.count("keepalive") >= 2 {
					pausedSeen = p["paused"] == true
					sentEnd = true
					h.send(ws, "end", map[string]string{"reason": "hub_end"})
				}
			}
		}
	})
	job := mediaTestJob(t, "playback", hub, map[string]interface{}{"content": map[string]interface{}{"path": mediaSilentWAV(t), "position_s": 0.5, "volume": 20}})
	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
	defer cancel()
	res := r.execute(ctx, job)
	hub.wait(t)
	hub.assertFrames(t)
	if res["error"] == "needs_media_player" || res["error"] == "needs_local_action" {
		if hub.count("state") == 0 {
			t.Fatalf("needs_local_action not reported before giving up: %v", res)
		}
		t.Skip("no player on this machine:", res["message"])
	}
	if res["closed"] != true || res["reason"] != "hub_end" || !ended {
		t.Fatalf("result %v (ended=%v)", res, ended)
	}
	if hub.count("keepalive") < 2 || hub.count("state") < 2 {
		t.Fatalf("keepalive %d state %d", hub.count("keepalive"), hub.count("state"))
	}
	if !pausedSeen {
		t.Log("player without control channel (afplay) — pause not verified")
	}
}

func TestMediaSessionSpeakerNegotiatesOverHubWS(t *testing.T) {
	r := mediaTestRuntime(t)
	sid := residentID()
	var gotAnswer, gotActive, wsClosed bool
	var nla map[string]interface{}
	hub := newMediaFakeHub(t, sid, func(h *mediaFakeHub, ws *websocket.Conn) {
		offerer, err := webrtc.NewPeerConnection(webrtc.Configuration{})
		if err != nil {
			t.Error(err)
			return
		}
		defer offerer.Close()
		track, _ := webrtc.NewTrackLocalStaticRTP(webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeOpus, ClockRate: 48000, Channels: 2}, "audio", "hub")
		sender, _ := offerer.AddTrack(track)
		go func() {
			buf := make([]byte, 1500)
			for {
				if _, _, err := sender.Read(buf); err != nil {
					return
				}
			}
		}()
		var wmu sync.Mutex
		offerer.OnICECandidate(func(c *webrtc.ICECandidate) {
			if c == nil {
				return
			}
			wmu.Lock()
			defer wmu.Unlock()
			h.send(ws, "candidate", c.ToJSON())
		})
		offer, _ := offerer.CreateOffer(nil)
		_ = offerer.SetLocalDescription(offer)
		wmu.Lock()
		h.send(ws, "offer", map[string]string{"sdp": offer.SDP, "fingerprint": mediaFingerprint(offer.SDP)})
		wmu.Unlock()
		stop := make(chan struct{})
		defer close(stop)
		go func() {
			for i := uint16(1); ; i++ {
				select {
				case <-stop:
					return
				case <-time.After(20 * time.Millisecond):
					_ = track.WriteRTP(&rtp.Packet{Header: rtp.Header{Version: 2, PayloadType: 111, SequenceNumber: i, Timestamp: uint32(i) * 960, SSRC: 5}, Payload: []byte{0xfc, 0xff, 0xfe}})
				}
			}
		}()
		deadline := time.Now().Add(30 * time.Second)
		for time.Now().Before(deadline) {
			f, ok := h.next(ws, 30*time.Second)
			if !ok {
				wsClosed = gotActive // the device closes its socket after the hub's end
				return
			}
			var p map[string]interface{}
			_ = json.Unmarshal(f.Payload, &p)
			switch f.Type {
			case "answer":
				sdp, _ := p["sdp"].(string)
				if !mediaFingerprintMatches(sdp, p["fingerprint"].(string)) {
					t.Error("answer fingerprint mismatch")
				}
				gotAnswer = offerer.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeAnswer, SDP: sdp}) == nil
			case "candidate":
				if c, ok := parseMediaCandidate(f.Payload); ok {
					_ = offerer.AddICECandidate(webrtc.ICECandidateInit{Candidate: c.Candidate, SDPMid: c.SDPMid, SDPMLineIndex: c.SDPMLineIndex})
				}
			case "state":
				if v, ok := p["needs_local_action"].(map[string]interface{}); ok {
					nla = v
					continue
				}
				if p["state"] == "active" && p["path"] == "direct" && h.count("keepalive") >= 1 {
					gotActive = true
					wmu.Lock()
					h.send(ws, "end", map[string]string{"reason": "hub_end"})
					wmu.Unlock()
				}
			}
		}
	})
	job := mediaTestJob(t, "speaker", hub, map[string]interface{}{"tracks": []map[string]interface{}{{"id": "a0", "kind": "audio", "source": "mic", "from": "hub", "to": "device"}}})
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	res := r.execute(ctx, job)
	hub.wait(t)
	hub.assertFrames(t)
	if nla != nil {
		if res["error"] != "needs_local_action" || res["needs_local_action"].(map[string]interface{})["code"] != nla["code"] {
			t.Fatalf("needs_local_action mismatch: %v vs %v", res, nla)
		}
		t.Skip("no ffplay on this machine:", nla["message"])
	}
	if !gotAnswer || !gotActive || !wsClosed {
		t.Fatalf("answer=%v active=%v closed=%v result=%v", gotAnswer, gotActive, wsClosed, res)
	}
	if res["closed"] != true || res["reason"] != "hub_end" || res["path"] != "direct" {
		t.Fatalf("result %v", res)
	}
	if hub.count("candidate") == 0 || hub.count("candidates_done") != 1 {
		t.Fatalf("trickle: %d candidates, %d done", hub.count("candidate"), hub.count("candidates_done"))
	}
	if _, err := os.Stat(filepath.Join(r.cfg.DataDir, "spool", "media-"+job.ID)); !os.IsNotExist(err) {
		t.Fatal("session workspace not removed")
	}
}

// Cancelling the job (hub cancel) ends the session with an `end` frame.
func TestMediaSessionCancelSendsEnd(t *testing.T) {
	r := mediaTestRuntime(t)
	sid := residentID()
	gotEnd := make(chan string, 1)
	hub := newMediaFakeHub(t, sid, func(h *mediaFakeHub, ws *websocket.Conn) {
		for {
			f, ok := h.next(ws, 20*time.Second)
			if !ok {
				return
			}
			if f.Type == "end" {
				var p map[string]string
				_ = json.Unmarshal(f.Payload, &p)
				gotEnd <- p["reason"]
				return
			}
		}
	})
	job := mediaTestJob(t, "playback", hub, map[string]interface{}{"content": map[string]interface{}{"path": mediaSilentWAV(t)}})
	ctx, cancel := context.WithCancel(context.Background())
	go func() { time.Sleep(1500 * time.Millisecond); cancel() }()
	res := r.execute(ctx, job)
	hub.wait(t)
	select {
	case reason := <-gotEnd:
		if reason != "cancelled" && reason != "needs_local_action" {
			t.Fatal("end reason", reason)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("no end frame after cancel; result", res)
	}
	if res["cancelled"] != true && res["error"] != "needs_local_action" {
		t.Fatalf("result %v", res)
	}
}
