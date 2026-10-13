package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Signal frames: docs/MEDIA_SESSION_CONTRACT.md §3. Transport-agnostic — the
// media WS carries these plus the hub's own {type:"ready"|"heartbeat"|"close"}
// transport frames, which have no v/seq and are passed through untouched.

type mediaSignal struct {
	V          int             `json:"v"`
	SessionID  string          `json:"session_id"`
	MsgID      string          `json:"msg_id"`
	From       string          `json:"from"`
	To         string          `json:"to"`
	Generation int             `json:"generation"`
	Seq        int             `json:"seq"`
	ExpiresAt  float64         `json:"expires_at"`
	Type       string          `json:"type"`
	Payload    json.RawMessage `json:"payload,omitempty"`
	MAC        string          `json:"mac,omitempty"`
}

// mediaOutbox numbers outgoing frames: one increasing seq per generation
// (keepalive shares the counter — the hub only renews the lease on a higher seq).
type mediaOutbox struct {
	mu         sync.Mutex
	sessionID  string
	from, to   string
	generation int
	seq        int
	secret     []byte
	ttl        time.Duration
	now        func() time.Time
}

func newMediaOutbox(sessionID, from, to string, generation int, secret string) *mediaOutbox {
	o := &mediaOutbox{sessionID: sessionID, from: from, to: to, generation: generation, ttl: 30 * time.Second, now: time.Now}
	if secret != "" {
		o.secret = []byte(secret)
	}
	return o
}

// setGeneration adopts a newer negotiation generation and restarts the seq.
func (o *mediaOutbox) setGeneration(g int) bool {
	o.mu.Lock()
	defer o.mu.Unlock()
	if g < o.generation {
		return false
	}
	if g > o.generation {
		o.generation, o.seq = g, 0
	}
	return true
}

func (o *mediaOutbox) current() int { o.mu.Lock(); defer o.mu.Unlock(); return o.generation }

func (o *mediaOutbox) frame(kind string, payload interface{}) (map[string]interface{}, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	o.mu.Lock()
	o.seq++
	f := map[string]interface{}{"v": 1, "session_id": o.sessionID, "msg_id": residentID(), "from": o.from, "to": o.to,
		"generation": o.generation, "seq": o.seq, "expires_at": float64(o.now().Add(o.ttl).UnixNano()) / 1e9,
		"type": kind, "payload": json.RawMessage(body)}
	secret := o.secret
	o.mu.Unlock()
	if secret != nil {
		f["mac"] = mediaMAC(secret, f)
	}
	return f, nil
}

// mediaMAC = HMAC-SHA256(secret, canonical_json(frame without mac)); canonical =
// sorted keys, no whitespace (Go's map marshalling).
func mediaMAC(secret []byte, frame map[string]interface{}) string {
	clean := map[string]interface{}{}
	for k, v := range frame {
		if k != "mac" {
			clean[k] = v
		}
	}
	b, _ := json.Marshal(clean)
	m := hmac.New(sha256.New, secret)
	m.Write(b)
	return hex.EncodeToString(m.Sum(nil))
}

// mediaInbox drops stale frames: lower generation, replayed/old seq within a
// generation, expired, or for another session. Transport frames (no v) pass.
type mediaInbox struct {
	mu         sync.Mutex
	sessionID  string
	generation int
	seen       int
	now        func() time.Time
}

func newMediaInbox(sessionID string, generation int) *mediaInbox {
	return &mediaInbox{sessionID: sessionID, generation: generation, seen: 0, now: time.Now}
}

// accept returns false for frames to discard. The hub's offer may open a new
// generation; the inbox moves forward with it and restarts its seq watermark.
func (b *mediaInbox) accept(f *mediaSignal) bool {
	if f.V == 0 && f.Seq == 0 && f.Generation == 0 {
		return true // hub transport frame (ready/heartbeat/close/session)
	}
	if f.V != 1 || f.SessionID != b.sessionID {
		return false
	}
	if f.ExpiresAt > 0 && float64(b.now().UnixNano())/1e9 > f.ExpiresAt {
		return false
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if f.Generation < b.generation {
		return false
	}
	if f.Generation > b.generation {
		b.generation, b.seen = f.Generation, 0
	}
	if f.Seq <= b.seen {
		return false
	}
	b.seen = f.Seq
	return true
}

func (b *mediaInbox) current() int { b.mu.Lock(); defer b.mu.Unlock(); return b.generation }

// mediaFingerprint extracts the DTLS fingerprint ("sha-256 AB:CD:…") from an SDP.
func mediaFingerprint(sdp string) string {
	for _, line := range strings.Split(sdp, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "a=fingerprint:") {
			return strings.TrimSpace(strings.TrimPrefix(line, "a=fingerprint:"))
		}
	}
	return ""
}

// mediaFingerprintMatches is lenient about case and about an absent envelope
// fingerprint (the SDP's own is then authoritative); it rejects a present mismatch.
func mediaFingerprintMatches(sdp, claimed string) bool {
	if claimed == "" {
		return true
	}
	return strings.EqualFold(strings.Join(strings.Fields(mediaFingerprint(sdp)), " "), strings.Join(strings.Fields(claimed), " "))
}

// mediaQuality is the contract's quality object. Rates are derived from two
// cumulative samples; a single sample yields zeros for bitrate.
type mediaQuality struct {
	RTTms       float64 `json:"rtt_ms"`
	Loss        float64 `json:"loss"`
	JitterMs    float64 `json:"jitter_ms"`
	BitrateKbps float64 `json:"bitrate_kbps"`
	FPS         int     `json:"fps"`
	Width       int     `json:"width"`
	Height      int     `json:"height"`
	Dropped     int64   `json:"dropped"`
}

// mediaStatsSample is engine-neutral: the pion wrapper fills it, tests fill it by hand.
type mediaStatsSample struct {
	At            time.Time
	RTT           time.Duration // selected candidate pair / remote-inbound RTT
	Bytes         uint64        // cumulative bytes sent (sender) or received (receiver)
	Packets       uint64        // cumulative packets in the same direction
	PacketsLost   int64         // cumulative, as reported by the far/near side
	Jitter        float64       // seconds (RTP jitter / clock rate)
	FractionLost  float64       // 0..1 from the latest receiver report, if any
	Width, Height int
	FPS           int
}

func mediaQualityFrom(prev, cur mediaStatsSample) mediaQuality {
	q := mediaQuality{Width: cur.Width, Height: cur.Height, FPS: cur.FPS, Dropped: cur.PacketsLost}
	if cur.RTT > 0 {
		q.RTTms = math.Round(float64(cur.RTT)/float64(time.Millisecond)*10) / 10
	}
	if cur.Jitter > 0 {
		q.JitterMs = math.Round(cur.Jitter*1000*10) / 10
	}
	if cur.FractionLost > 0 {
		q.Loss = math.Round(cur.FractionLost*1000) / 1000
	} else if delta := int64(cur.Packets) - int64(prev.Packets); delta > 0 && cur.PacketsLost > prev.PacketsLost {
		lost := cur.PacketsLost - prev.PacketsLost
		q.Loss = math.Round(float64(lost)/float64(delta+lost)*1000) / 1000
	}
	if dt := cur.At.Sub(prev.At).Seconds(); dt > 0 && cur.Bytes > prev.Bytes && !prev.At.IsZero() {
		q.BitrateKbps = math.Round(float64(cur.Bytes-prev.Bytes)*8/1000/dt*10) / 10
	}
	if q.Dropped < 0 {
		q.Dropped = 0
	}
	return q
}

// mediaPath maps the selected ICE candidate pair to the contract's path value.
func mediaPath(localType, remoteType string) string {
	if localType == "" && remoteType == "" {
		return ""
	}
	if localType == "relay" || remoteType == "relay" {
		return "relay"
	}
	return "direct"
}

// mediaStatePayload builds the §3 state payload. Extra keys (playback fields)
// are merged in sorted order for stable output.
func mediaStatePayload(state, path string, q *mediaQuality, nla map[string]interface{}, extra map[string]interface{}) map[string]interface{} {
	p := map[string]interface{}{"state": state}
	if path != "" {
		p["path"] = path
	}
	if q != nil {
		p["quality"] = *q
	}
	if nla != nil {
		p["needs_local_action"] = nla
	}
	keys := make([]string, 0, len(extra))
	for k := range extra {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		p[k] = extra[k]
	}
	return p
}

// mediaCandidatePayload reads a trickle candidate from either the flat
// ICECandidateInit shape or one nested under "candidate".
type mediaCandidateInit struct {
	Candidate        string  `json:"candidate"`
	SDPMid           *string `json:"sdpMid,omitempty"`
	SDPMLineIndex    *uint16 `json:"sdpMLineIndex,omitempty"`
	UsernameFragment *string `json:"usernameFragment,omitempty"`
}

func parseMediaCandidate(payload json.RawMessage) (mediaCandidateInit, bool) {
	var flat mediaCandidateInit
	if json.Unmarshal(payload, &flat) == nil && flat.Candidate != "" {
		return flat, true
	}
	var nested struct {
		Candidate mediaCandidateInit `json:"candidate"`
	}
	if json.Unmarshal(payload, &nested) == nil && nested.Candidate.Candidate != "" {
		return nested.Candidate, true
	}
	return mediaCandidateInit{}, false
}

var mediaRTPMap = regexp.MustCompile(`(?mi)^a=rtpmap:(\d+)\s+(opus|H264)/`)

// mediaSDPPayloadTypes finds the negotiated Opus/H264 payload types in an SDP
// (first of each; ffplay's SDP and the forwarded packets use them).
func mediaSDPPayloadTypes(sdp string) (opus, h264 uint8) {
	for _, m := range mediaRTPMap.FindAllStringSubmatch(sdp, -1) {
		pt, _ := strconv.Atoi(m[1])
		switch {
		case strings.EqualFold(m[2], "opus") && opus == 0:
			opus = uint8(pt)
		case strings.EqualFold(m[2], "h264") && h264 == 0:
			h264 = uint8(pt)
		}
	}
	return
}
