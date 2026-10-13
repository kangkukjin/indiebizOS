//go:build !legacy

package main

import (
	"bytes"
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type mediaSession struct {
	r      *residentRuntime
	env    *mediaEnvelope
	jid    string
	dir    string
	ctx    context.Context
	cancel context.CancelFunc
	caps   mediaCaps
	out    *mediaOutbox
	in     *mediaInbox

	conn    *mediaConn
	inbound chan mediaSignal
	lost    chan *mediaConn

	peer           *mediaPeer
	play           *mediaPlayback
	captureDone    chan error
	captureRelease func()
	captureTail    mediaTail
	playerRelease  func()
	recvAudioPort  int
	recvVideoPort  int
	recvAudioPT    uint8
	recvVideoPT    uint8
	receiverOn     bool

	state   string
	path    string
	prev    mediaStatsSample
	quality mediaQuality
	ended   bool
}

// mediaConn is one authenticated media WS; the reader goroutine owns reads and
// reports loss with its own pointer so a replaced connection cannot confuse the loop.
type mediaConn struct {
	ws *websocket.Conn
	mu sync.Mutex
}

func (c *mediaConn) write(v interface{}) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	_ = c.ws.SetWriteDeadline(time.Now().Add(5 * time.Second))
	return c.ws.WriteJSON(v)
}
func (c *mediaConn) close() { _ = c.ws.Close() }

// mediaTail keeps the last bytes of a subprocess's stderr for diagnostics.
type mediaTail struct {
	mu  sync.Mutex
	buf []byte
}

func (t *mediaTail) Write(b []byte) (int, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.buf = append(t.buf, b...)
	if len(t.buf) > 2048 {
		t.buf = t.buf[len(t.buf)-2048:]
	}
	return len(b), nil
}
func (t *mediaTail) String() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return string(bytes.TrimSpace(t.buf))
}

// dial connects LAN-first (pinned certificate from the envelope), then the
// envelope's stream.url, then the hub base. Auth frame = {key, installation_id,
// grant}: the grant token travels only on this socket.
func (s *mediaSession) dial() (*mediaConn, error) {
	spec := terminalSpec{Config: *s.r.cfg, ID: s.env.SessionID, LAN: s.env.Stream.LAN, Channel: "media"}
	var ws *websocket.Conn
	if ws = dialTerminalLAN(s.ctx, spec); ws == nil {
		address := s.env.Stream.URL
		if address == "" {
			var err error
			if address, err = streamURL(s.r.cfg.Base, s.env.SessionID, "media"); err != nil {
				return nil, err
			}
		}
		dialer := websocket.Dialer{HandshakeTimeout: 10 * time.Second}
		var response *http.Response
		var err error
		ws, response, err = dialer.DialContext(s.ctx, address, nil)
		if response != nil && response.Body != nil {
			response.Body.Close()
		}
		if err != nil {
			return nil, err
		}
	}
	c := &mediaConn{ws: ws}
	ws.SetReadLimit(1 << 20)
	auth := map[string]interface{}{"key": s.r.cfg.Key, "installation_id": s.r.cfg.InstallationID, "grant": s.env.Grant}
	var ready struct {
		Type  string `json:"type"`
		Error string `json:"error"`
	}
	_ = ws.SetReadDeadline(time.Now().Add(10 * time.Second))
	if err := c.write(auth); err != nil || ws.ReadJSON(&ready) != nil || ready.Type != "ready" {
		c.close()
		if ready.Error != "" {
			return nil, fmt.Errorf("%s", ready.Error)
		}
		return nil, fmt.Errorf("media_auth")
	}
	if err := c.write(map[string]interface{}{"type": "ready", "capabilities": s.caps.report(mediaEngineVersion(), true)}); err != nil {
		c.close()
		return nil, err
	}
	return c, nil
}

// connect retries the dial until within seconds elapse.
func (s *mediaSession) connect(within float64) error {
	deadline := time.Now().Add(time.Duration(within * float64(time.Second)))
	wait := time.Second
	for {
		c, err := s.dial()
		if err == nil {
			s.conn = c
			go s.read(c)
			return nil
		}
		if s.ctx.Err() != nil || time.Now().Add(wait).After(deadline) || err.Error() == "session_ended" {
			return err
		}
		select {
		case <-s.ctx.Done():
			return s.ctx.Err()
		case <-time.After(wait):
		}
		if wait < 5*time.Second {
			wait *= 2
		}
	}
}

// read pumps accepted frames from one connection until it fails.
func (s *mediaSession) read(c *mediaConn) {
	idle := time.Duration(s.env.Lease.LeaseS*2*float64(time.Second)) + 10*time.Second
	for {
		var f mediaSignal
		_ = c.ws.SetReadDeadline(time.Now().Add(idle))
		if err := c.ws.ReadJSON(&f); err != nil {
			select {
			case s.lost <- c:
			case <-s.ctx.Done():
			}
			return
		}
		if f.Type == "heartbeat" || f.Type == "ready" || !s.in.accept(&f) {
			continue
		}
		select {
		case s.inbound <- f:
		case <-s.ctx.Done():
			return
		}
	}
}

// reconnect replaces a lost connection within lease.reconnect_s; the WebRTC
// leg keeps running meanwhile. Beyond the window the session ends.
func (s *mediaSession) reconnect(c *mediaConn) map[string]interface{} {
	if c != s.conn || s.ended {
		return nil
	}
	s.conn.close()
	s.conn = nil
	s.state = "reconnecting"
	if err := s.connect(s.env.Lease.ReconnectS); err != nil {
		s.ended = true
		s.cleanup()
		return errResult("signaling_unavailable", "미디어 시그널 통로를 다시 연결하지 못했습니다")
	}
	if s.peer != nil && s.peer.connected() {
		s.state = "active"
	}
	s.reportState()
	return nil
}

func (s *mediaSession) send(kind string, payload interface{}) error {
	if s.conn == nil {
		return fmt.Errorf("not connected")
	}
	f, err := s.out.frame(kind, payload)
	if err != nil {
		return err
	}
	return s.conn.write(f)
}

// startEngine builds the peer, opens capture ports and launches ffmpeg.
func (s *mediaSession) startEngine(d mediaDirection) map[string]interface{} {
	peer, err := newMediaPeer(s.env.ICEServers, d)
	if err != nil {
		return errResult("connectivity_failed", "media engine: "+err.Error())
	}
	s.peer = peer
	if d.SendVideo || d.SendAudio {
		spec := mediaCaptureSpec{FFmpeg: s.caps.FFmpegPath, GOOS: runtime.GOOS, Encoders: s.caps.Encoders, Devices: s.caps.Devices,
			Video: d.SendVideo, Audio: d.SendAudio, VideoDevice: d.Video.Device, AudioDevice: d.Audio.Device,
			Width: d.Video.Width, Height: d.Video.Height, FPS: d.Video.FPS, BitrateKbps: d.Video.BitrateKbps}
		if d.SendVideo {
			if spec.VideoPort, err = peer.openInput("video"); err != nil {
				return errResult("device_busy", err.Error())
			}
		}
		if d.SendAudio {
			if spec.AudioPort, err = peer.openInput("audio"); err != nil {
				return errResult("device_busy", err.Error())
			}
		}
		args, err := mediaCaptureArgs(spec)
		if err != nil {
			res := errResult("needs_local_action", err.Error())
			res["needs_local_action"] = map[string]interface{}{"code": "device_missing", "message": err.Error()}
			return res
		}
		spec.defaults()
		peer.width, peer.height, peer.fps = spec.Width, spec.Height, spec.FPS
		cmd := exec.CommandContext(s.ctx, spec.FFmpeg, args...)
		cmd.Dir = s.dir
		cmd.Stderr = &s.captureTail
		cmd, s.captureRelease = mediaSuperviseProcess(s.ctx, s.r, cmd, s.jid+"-cap")
		if err := cmd.Start(); err != nil {
			return errResult("device_busy", "ffmpeg: "+err.Error())
		}
		s.captureDone = make(chan error, 1)
		go func() { s.captureDone <- cmd.Wait() }()
	}
	if d.RecvAudio || d.RecvVideo {
		if d.RecvAudio {
			s.recvAudioPort = mediaFreeUDPPort()
		}
		if d.RecvVideo {
			s.recvVideoPort = mediaFreeUDPPort()
		}
	}
	return nil
}

// startReceiver launches ffplay once the answer fixes the payload types.
func (s *mediaSession) startReceiver(answerSDP string) {
	if s.receiverOn || (s.recvAudioPort == 0 && s.recvVideoPort == 0) {
		return
	}
	opus, h264 := mediaSDPPayloadTypes(answerSDP)
	audioPort, videoPort := s.recvAudioPort, s.recvVideoPort
	if opus == 0 {
		audioPort = 0
	}
	if h264 == 0 {
		videoPort = 0
	}
	if audioPort == 0 && videoPort == 0 {
		return
	}
	s.recvAudioPT, s.recvVideoPT = opus, h264
	sdpPath := filepath.Join(s.dir, "recv.sdp")
	if err := os.WriteFile(sdpPath, []byte(mediaPlaybackSDP(audioPort, opus, videoPort, h264)), 0600); err != nil {
		return
	}
	cmd := exec.CommandContext(s.ctx, s.caps.FFplayPath, mediaPlayArgs(sdpPath, videoPort > 0 && s.caps.Display)...)
	cmd.Dir = s.dir
	cmd.Stderr = &s.captureTail
	cmd, s.playerRelease = mediaSuperviseProcess(s.ctx, s.r, cmd, s.jid+"-out")
	if err := cmd.Start(); err != nil {
		return
	}
	s.receiverOn = true
	go func() { _ = cmd.Wait() }()
}

// mediaFreeUDPPort reserves a loopback port number for a subprocess listener.
func mediaFreeUDPPort() int {
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 0})
	if err != nil {
		return 0
	}
	port := conn.LocalAddr().(*net.UDPAddr).Port
	_ = conn.Close()
	return port
}
