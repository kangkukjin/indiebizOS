//go:build !legacy

package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// media_session op (docs/MEDIA_SESSION_CONTRACT.md §5 "extension", §6): the job
// lives as long as the session, like `desktop`. The device is always the
// answerer; the hub (browser engine) offers. Cancel = end.

func (r *residentRuntime) mediaSession(ctx context.Context, j Job) map[string]interface{} {
	env, code, err := parseMediaEnvelope(j.Code)
	if err != nil {
		return errResult(code, err.Error())
	}
	timeout := env.Timeout
	if timeout <= 0 || timeout > 86400 {
		timeout = 86400
	}
	ctx, cancel := context.WithTimeout(ctx, time.Duration(timeout)*time.Second)
	defer cancel()
	if ctx.Err() != nil {
		return map[string]interface{}{"cancelled": true, "error": ctx.Err().Error()}
	}
	s := &mediaSession{r: r, env: env, jid: j.ID, ctx: ctx, cancel: cancel,
		dir:     filepath.Join(r.cfg.DataDir, "spool", "media-"+j.ID),
		out:     newMediaOutbox(env.SessionID, env.role(), "hub", 0, env.Secret),
		in:      newMediaInbox(env.SessionID, 0),
		inbound: make(chan mediaSignal, 64), lost: make(chan *mediaConn, 4), state: "connecting"}
	if e := os.MkdirAll(s.dir, 0700); e != nil {
		return errResult("workspace", e.Error())
	}
	defer os.RemoveAll(s.dir)
	defer s.cleanup()
	return s.run()
}

func (s *mediaSession) run() map[string]interface{} {
	s.caps = mediaProbe(s.ctx, s.env.FFmpegPath, s.r.cfg.DataDir)
	d := s.env.direction()
	nla := s.preflight(d)
	if err := s.connect(s.env.Lease.ReconnectS); err != nil {
		return errResult("signaling_unavailable", "미디어 시그널 통로에 연결하지 못했습니다")
	}
	if nla != nil {
		_ = s.send("state", mediaStatePayload("needs_local_action", "", nil, nla, nil))
		s.finish("needs_local_action")
		res := errResult("needs_local_action", nla["message"].(string))
		res["needs_local_action"] = nla
		return res
	}
	if s.env.Purpose == "playback" {
		source, err := s.env.contentURL(s.r.cfg.Base)
		if err != nil {
			s.finish("content_unavailable")
			return errResult("content_unavailable", err.Error())
		}
		play, missing := startMediaPlayback(s.ctx, s.r, s.jid, s.dir, source, *s.env.Content, s.r.cfg.Mode)
		if missing != nil {
			nla = map[string]interface{}{"code": missing["error"], "message": missing["message"]}
			_ = s.send("state", mediaStatePayload("needs_local_action", "", nil, nla, nil))
			s.finish("needs_local_action")
			missing["needs_local_action"] = nla
			return missing
		}
		s.play = play
	} else {
		if res := s.startEngine(d); res != nil {
			s.finish(res["error"].(string))
			return res
		}
	}
	s.reportState()
	return s.loop()
}

// preflight maps missing local prerequisites to the contract's
// needs_local_action {code, message}; nil when the purpose can start.
func (s *mediaSession) preflight(d mediaDirection) map[string]interface{} {
	need := func(code, message string) map[string]interface{} {
		return map[string]interface{}{"code": code, "message": message}
	}
	if !mediaEngineBuilt {
		return need("engine_unsupported", "이 헬퍼 빌드에는 미디어 엔진이 없습니다 (legacy)")
	}
	switch {
	case s.env.Purpose == "playback":
		return nil
	case (d.SendVideo || d.SendAudio) && !s.caps.FFmpeg:
		return need("ffmpeg_missing", "ffmpeg 실행파일이 필요합니다 (PATH 또는 헬퍼 데이터 폴더 bin/ffmpeg)")
	case d.SendVideo && !s.caps.Camera:
		return need("camera_missing", "사용할 수 있는 카메라(또는 H.264 인코더)가 없습니다")
	case d.SendAudio && !s.caps.Microphone:
		return need("microphone_missing", "사용할 수 있는 마이크(또는 Opus 인코더)가 없습니다")
	case (d.RecvAudio || d.RecvVideo) && !s.caps.Speaker:
		return need("ffmpeg_missing", "ffplay 실행파일이 필요합니다 (PATH 또는 헬퍼 데이터 폴더 bin/ffplay)")
	case d.RecvVideo && !s.caps.Display:
		return need("display_missing", "영상을 표시할 화면 세션이 없습니다")
	}
	return nil
}

// loop multiplexes signalling, engine events, timers and cancellation.
func (s *mediaSession) loop() map[string]interface{} {
	keepalive := time.NewTicker(time.Duration(s.env.Lease.KeepaliveS * float64(time.Second)))
	defer keepalive.Stop()
	interval := 5 * time.Second
	if s.play != nil {
		interval = 2 * time.Second
	}
	report := time.NewTicker(interval)
	defer report.Stop()
	var peerNotify chan struct{}
	var playDone chan struct{}
	if s.peer != nil {
		peerNotify = s.peer.notify
	}
	if s.play != nil {
		playDone = s.play.done
	}
	for {
		select {
		case <-s.ctx.Done():
			s.finish("cancelled")
			return map[string]interface{}{"closed": true, "cancelled": true, "session_id": s.env.SessionID}
		case f := <-s.inbound:
			if res := s.handleFrame(f); res != nil {
				return res
			}
		case c := <-s.lost:
			if res := s.reconnect(c); res != nil {
				return res
			}
		case <-keepalive.C:
			_ = s.send("keepalive", map[string]interface{}{})
		case <-report.C:
			s.reportState()
		case <-peerNotify:
			for _, ev := range s.peer.events() {
				if res := s.handlePeerEvent(ev); res != nil {
					return res
				}
			}
		case err := <-s.captureDone:
			nla := map[string]interface{}{"code": "capture_failed", "message": "캡처 프로세스가 종료됐습니다: " + s.captureTail.String() + exitText(err)}
			_ = s.send("state", mediaStatePayload("needs_local_action", s.pathNow(), nil, nla, nil))
			s.finish("needs_local_action")
			res := errResult("needs_local_action", nla["message"].(string))
			res["needs_local_action"] = nla
			return res
		case <-playDone:
			st := s.play.state()
			_ = s.send("state", mediaStatePayload("ended", "", nil, nil, map[string]interface{}{"playing": false, "ended": true, "position_s": st.PositionS}))
			s.finish("content_ended")
			return map[string]interface{}{"closed": true, "session_id": s.env.SessionID, "reason": "content_ended", "player_exit": exitCode(s.play.exitErr)}
		}
	}
}

func exitText(err error) string {
	if err == nil {
		return ""
	}
	return " (" + err.Error() + ")"
}

// handleFrame applies one accepted signal frame; a non-nil result ends the job.
func (s *mediaSession) handleFrame(f mediaSignal) map[string]interface{} {
	switch f.Type {
	case "offer":
		if s.peer == nil {
			return nil // playback carries no WebRTC leg
		}
		var offer struct {
			SDP         string `json:"sdp"`
			Fingerprint string `json:"fingerprint"`
		}
		if json.Unmarshal(f.Payload, &offer) != nil || offer.SDP == "" || !s.out.setGeneration(f.Generation) {
			return nil
		}
		if !mediaFingerprintMatches(offer.SDP, offer.Fingerprint) {
			s.finish("fingerprint_mismatch")
			return errResult("connectivity_failed", "offer fingerprint mismatch")
		}
		answer, err := s.peer.handleOffer(offer.SDP)
		if err != nil {
			s.finish("connectivity_failed")
			return errResult("connectivity_failed", "offer not applicable: "+err.Error())
		}
		if err := s.send("answer", map[string]interface{}{"sdp": answer, "fingerprint": mediaFingerprint(answer)}); err == nil {
			s.startReceiver(answer)
		}
	case "candidate":
		if s.peer == nil {
			return nil
		}
		if c, ok := parseMediaCandidate(f.Payload); ok {
			_ = s.peer.addCandidate(c)
		}
	case "update":
		s.applyUpdate(parseMediaUpdate(f.Payload))
		s.reportState()
	case "end":
		var p struct {
			Reason string `json:"reason"`
		}
		_ = json.Unmarshal(f.Payload, &p)
		res := s.closedResult(p.Reason) // before cleanup drops the engine
		s.ended = true
		s.finish(p.Reason)
		return res
	case "close":
		s.lost <- s.conn
	case "session":
		var p struct {
			Session struct {
				State string `json:"state"`
			} `json:"session"`
		}
		if json.Unmarshal(f.Payload, &p) == nil && p.Session.State == "ended" {
			res := s.closedResult("session_ended")
			s.ended = true
			s.finish("session_ended")
			return res
		}
	}
	return nil
}

func (s *mediaSession) closedResult(reason string) map[string]interface{} {
	res := map[string]interface{}{"closed": true, "session_id": s.env.SessionID, "reason": reason, "generation": s.out.current()}
	if s.peer != nil {
		res["path"], res["quality"] = s.path, s.quality
	}
	return res
}

func (s *mediaSession) applyUpdate(u mediaUpdate) {
	if s.play != nil {
		s.play.apply(u)
	}
	if s.peer != nil {
		if u.Mute != nil {
			s.peer.muted.Store(*u.Mute)
		}
		if u.Camera != nil {
			s.peer.paused.Store(!*u.Camera)
		}
	}
}

func (s *mediaSession) handlePeerEvent(ev mediaPeerEvent) map[string]interface{} {
	switch ev.Kind {
	case "candidate":
		_ = s.send("candidate", ev.Candidate)
	case "candidates_done":
		_ = s.send("candidates_done", map[string]interface{}{})
	case "ice":
		switch ev.State {
		case "connected", "completed":
			if s.state != "active" {
				s.state = "active"
				s.reportState()
			}
		case "disconnected":
			s.state = "reconnecting"
			s.reportState()
		case "failed":
			s.finish("connectivity_failed")
			return errResult("connectivity_failed", "ICE failed")
		}
	case "track":
		if ev.Track == nil {
			return nil
		}
		port, pt := s.recvAudioPort, s.recvAudioPT
		if ev.State == "video" {
			port, pt = s.recvVideoPort, s.recvVideoPT
		}
		if port > 0 && pt > 0 {
			_ = s.peer.forwardRemote(ev.Track, port, pt)
		}
	}
	return nil
}

// reportState sends the §3 state payload (quality from the engine, playback
// fields for content sessions).
func (s *mediaSession) reportState() {
	var q *mediaQuality
	extra := map[string]interface{}{}
	if s.peer != nil {
		cur := s.peer.sample()
		s.quality = mediaQualityFrom(s.prev, cur)
		s.prev = cur
		s.path = s.peer.path()
		q = &s.quality
	}
	if s.play != nil {
		st := s.play.state()
		extra["playing"], extra["paused"], extra["position_s"], extra["volume"], extra["control"] = st.Playing, st.Paused, st.PositionS, st.Volume, st.Control
		if st.DurationS > 0 {
			extra["duration_s"] = st.DurationS
		}
		if st.Playing && s.state != "active" {
			s.state = "active"
		}
	}
	_ = s.send("state", mediaStatePayload(s.state, s.path, q, nil, extra))
}

func (s *mediaSession) pathNow() string {
	if s.peer != nil {
		return s.peer.path()
	}
	return ""
}

// finish tells the hub the session ends (best effort) and releases the engine.
func (s *mediaSession) finish(reason string) {
	if reason == "" {
		reason = "ended"
	}
	if !s.ended {
		_ = s.send("end", map[string]interface{}{"reason": reason})
	}
	s.ended = true
	s.cleanup()
}

func (s *mediaSession) cleanup() {
	if s.play != nil {
		s.play.close()
		s.play = nil
	}
	if s.peer != nil {
		s.peer.close()
		s.peer = nil
	}
	if s.captureRelease != nil {
		s.captureRelease()
		s.captureRelease = nil
	}
	if s.playerRelease != nil {
		s.playerRelease()
		s.playerRelease = nil
	}
	s.cancel()
	if s.conn != nil {
		s.conn.close()
		s.conn = nil
	}
}
