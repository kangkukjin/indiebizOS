package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"path/filepath"
	"strings"
)

// Wire contract: docs/MEDIA_SESSION_CONTRACT.md §6 (hub → device envelope).
// Everything here is pure data handling so the legacy build parses and refuses
// the op with the same codes as the full build.

type mediaGrant struct {
	SessionID string   `json:"session_id"`
	Role      string   `json:"role"`
	Device    string   `json:"device"`
	Tracks    []string `json:"tracks"`
	ExpiresAt float64  `json:"expires_at"`
	Token     string   `json:"token"`
}

type mediaTrack struct {
	ID     string `json:"id"`
	Kind   string `json:"kind"`   // audio | video
	Source string `json:"source"` // mic | camera | playback | screen
	From   string `json:"from"`
	To     string `json:"to"`
	State  string `json:"state,omitempty"`
	// Helper extensions (optional, contract §6 does not list them yet).
	Device      string `json:"device,omitempty"`
	Width       int    `json:"width,omitempty"`
	Height      int    `json:"height,omitempty"`
	FPS         int    `json:"fps,omitempty"`
	BitrateKbps int    `json:"bitrate_kbps,omitempty"`
}

type mediaICEServer struct {
	URLs       []string `json:"urls"`
	Username   string   `json:"username,omitempty"`
	Credential string   `json:"credential,omitempty"`
}

type mediaLease struct {
	LeaseS     float64 `json:"lease_s"`
	KeepaliveS float64 `json:"keepalive_s"`
	ReconnectS float64 `json:"reconnect_s"`
}

type mediaContent struct {
	Ref       string  `json:"ref,omitempty"`
	URL       string  `json:"url,omitempty"`
	Path      string  `json:"path,omitempty"`
	PositionS float64 `json:"position_s"`
	Paused    bool    `json:"paused"`
	Volume    float64 `json:"volume"`
	HasVolume bool    `json:"-"`
}

type mediaEnvelope struct {
	Op         string           `json:"op"`
	SessionID  string           `json:"session_id"`
	Grant      mediaGrant       `json:"grant"`
	Purpose    string           `json:"purpose"`
	Tracks     []mediaTrack     `json:"tracks"`
	ICEServers []mediaICEServer `json:"ice_servers"`
	Lease      mediaLease       `json:"lease"`
	Stream     struct {
		URL string      `json:"url"`
		LAN terminalLAN `json:"lan"`
	} `json:"stream"`
	Content    *mediaContent `json:"content"`
	Timeout    int           `json:"timeout"`
	Secret     string        `json:"secret,omitempty"`      // optional: signs §3 frames when present
	FFmpegPath string        `json:"ffmpeg_path,omitempty"` // optional override (hub-pushed binary)
	// Note: `generation` in the job envelope is the registration generation
	// (string, checked by execute). The negotiation generation starts at 0 and
	// follows the hub's offer frames.
}

var mediaPurposes = map[string]bool{"camera": true, "microphone": true, "speaker": true, "playback": true}

// parseMediaEnvelope validates the §6 envelope. Errors carry the contract's
// failure codes so the caller can return them unchanged.
func parseMediaEnvelope(code string) (*mediaEnvelope, string, error) {
	var env mediaEnvelope
	if err := json.Unmarshal([]byte(code), &env); err != nil {
		return nil, "invalid_command", err
	}
	var raw struct {
		Content *struct {
			Volume *float64 `json:"volume"`
		} `json:"content"`
	}
	_ = json.Unmarshal([]byte(code), &raw)
	if env.Op != "media_session" {
		return nil, "invalid_command", fmt.Errorf("op must be media_session")
	}
	if !residentValidID(env.SessionID) {
		return nil, "invalid_command", fmt.Errorf("invalid session_id")
	}
	if env.Grant.SessionID != env.SessionID || env.Grant.Token == "" || env.Grant.Role == "" {
		return nil, "permission_required", fmt.Errorf("grant missing or for another session")
	}
	if !mediaPurposes[env.Purpose] {
		return nil, "unsupported_track", fmt.Errorf("unknown purpose %q", env.Purpose)
	}
	for i, t := range env.Tracks {
		if t.Kind != "audio" && t.Kind != "video" {
			return nil, "unsupported_track", fmt.Errorf("track %d: kind must be audio or video", i)
		}
		if t.Device != "" && (strings.HasPrefix(t.Device, "-") || strings.ContainsAny(t.Device, "\x00\n")) {
			return nil, "unsupported_track", fmt.Errorf("track %d: invalid device", i)
		}
	}
	if env.Lease.KeepaliveS <= 0 {
		env.Lease.KeepaliveS = 5
	}
	if env.Lease.LeaseS <= 0 {
		env.Lease.LeaseS = 20
	}
	if env.Lease.ReconnectS <= 0 {
		env.Lease.ReconnectS = 30
	}
	if env.Purpose == "playback" {
		if env.Content == nil || (env.Content.URL == "" && env.Content.Path == "") {
			return nil, "content_unavailable", fmt.Errorf("playback needs content.url or content.path")
		}
		if raw.Content != nil && raw.Content.Volume != nil {
			env.Content.HasVolume = true
			if env.Content.Volume < 0 || env.Content.Volume > 100 {
				return nil, "invalid_command", fmt.Errorf("volume must be 0..100")
			}
		}
		if env.Content.Path != "" && (!filepath.IsAbs(env.Content.Path) || strings.HasPrefix(env.Content.Path, "-")) {
			return nil, "content_unavailable", fmt.Errorf("content.path must be absolute")
		}
		if env.Content.PositionS < 0 {
			env.Content.PositionS = 0
		}
	}
	if env.FFmpegPath != "" && !filepath.IsAbs(env.FFmpegPath) {
		return nil, "invalid_command", fmt.Errorf("ffmpeg_path must be absolute")
	}
	if env.Stream.URL != "" {
		u, err := url.Parse(env.Stream.URL)
		if err != nil || (u.Scheme != "wss" && !(u.Scheme == "ws" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost"))) {
			return nil, "invalid_command", fmt.Errorf("stream.url must be wss")
		}
	}
	return &env, "", nil
}

// role is the device's own role in the session (grant.role, "device" by default).
func (env *mediaEnvelope) role() string {
	if env.Grant.Role != "" {
		return env.Grant.Role
	}
	return "device"
}

// mediaDirection describes what the device must send and receive, derived from
// the track list (from/to the device role) or, when the list is empty, from purpose.
type mediaDirection struct {
	SendVideo, SendAudio, RecvAudio, RecvVideo bool
	Video, Audio                               mediaTrack // send-side track specs (device, size, fps)
}

func (env *mediaEnvelope) direction() mediaDirection {
	var d mediaDirection
	role := env.role()
	for _, t := range env.Tracks {
		if t.State == "rejected" || t.State == "ended" {
			continue
		}
		switch {
		case t.From == role && t.Kind == "video":
			d.SendVideo, d.Video = true, t
		case t.From == role && t.Kind == "audio":
			d.SendAudio, d.Audio = true, t
		case t.To == role && t.Kind == "audio":
			d.RecvAudio = true
		case t.To == role && t.Kind == "video":
			d.RecvVideo = true
		}
	}
	if len(env.Tracks) == 0 || (!d.SendVideo && !d.SendAudio && !d.RecvAudio && !d.RecvVideo) {
		switch env.Purpose {
		case "camera":
			d.SendVideo = true
		case "microphone":
			d.SendAudio = true
		case "speaker":
			d.RecvAudio = true
		}
	}
	return d
}

// contentURL resolves the playback source. Relative hub paths (§7
// /media/content/<ref>) are joined to the hub base and carry the session grant
// token as the contract requires; absolute URLs and local paths pass through.
func (env *mediaEnvelope) contentURL(base string) (string, error) {
	if env.Content == nil {
		return "", fmt.Errorf("no content")
	}
	if env.Content.Path != "" {
		return env.Content.Path, nil
	}
	raw := env.Content.URL
	if strings.HasPrefix(raw, "/") {
		b, err := url.Parse(base)
		if err != nil || b.Host == "" {
			return "", fmt.Errorf("invalid hub base")
		}
		u, err := url.Parse(raw)
		if err != nil {
			return "", err
		}
		u.Scheme, u.Host = b.Scheme, b.Host
		u.Path = strings.TrimRight(b.Path, "/") + u.Path
		q := u.Query()
		if q.Get("token") == "" {
			q.Set("token", env.Grant.Token)
		}
		u.RawQuery = q.Encode()
		return u.String(), nil
	}
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "https" && u.Scheme != "http") {
		return "", fmt.Errorf("content url must be http(s)")
	}
	return raw, nil
}

// mediaUpdate is the change set carried by an `update` frame (§2 changes shape,
// accepted flat or nested under "changes").
type mediaUpdate struct {
	Mute      *bool
	Camera    *bool
	Paused    *bool
	PositionS *float64
	Volume    *float64
}

func parseMediaUpdate(payload json.RawMessage) mediaUpdate {
	var u mediaUpdate
	var body struct {
		Changes *json.RawMessage `json:"changes"`
		Mute    *bool            `json:"mute"`
		Camera  *bool            `json:"camera"`
		Content *struct {
			Paused    *bool    `json:"paused"`
			PositionS *float64 `json:"position_s"`
			Volume    *float64 `json:"volume"`
		} `json:"content"`
		Paused    *bool    `json:"paused"`
		PositionS *float64 `json:"position_s"`
		Volume    *float64 `json:"volume"`
	}
	if json.Unmarshal(payload, &body) != nil {
		return u
	}
	if body.Changes != nil {
		return parseMediaUpdate(*body.Changes)
	}
	u.Mute, u.Camera, u.Paused, u.PositionS, u.Volume = body.Mute, body.Camera, body.Paused, body.PositionS, body.Volume
	if body.Content != nil {
		u.Paused, u.PositionS, u.Volume = body.Content.Paused, body.Content.PositionS, body.Content.Volume
	}
	if u.Volume != nil && (*u.Volume < 0 || *u.Volume > 100) {
		u.Volume = nil
	}
	return u
}
