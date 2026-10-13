//go:build !legacy

package main

import (
	"fmt"
	"net"
	"runtime/debug"
	"sync"
	"sync/atomic"
	"time"

	"github.com/pion/interceptor"
	"github.com/pion/interceptor/pkg/stats"
	"github.com/pion/rtcp"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v4"
)

const mediaEngineBuilt = true

// mediaEngineVersion reports "pion/<module version>" from the build info.
func mediaEngineVersion() string {
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, dep := range info.Deps {
			if dep.Path == "github.com/pion/webrtc/v4" {
				return "pion/" + dep.Version
			}
		}
	}
	return "pion/unknown"
}

type mediaPeerEvent struct {
	Kind      string // candidate | candidates_done | ice | connection | track
	Candidate *mediaCandidateInit
	State     string
	Track     *webrtc.TrackRemote
}

// mediaPeer wraps one pion PeerConnection as the answerer: local RTP (from
// ffmpeg on loopback UDP) goes out on TrackLocalStaticRTP; remote RTP is
// forwarded to loopback UDP for ffplay.
type mediaPeer struct {
	pc      *webrtc.PeerConnection
	getter  stats.Getter
	mu      sync.Mutex
	queue   []mediaPeerEvent
	notify  chan struct{}
	tracks  map[string]*webrtc.TrackLocalStaticRTP // "video" | "audio"
	senders map[string]*webrtc.RTPSender
	inputs  map[string]*net.UDPConn
	outputs map[string]*net.UDPConn
	remotes map[string]*webrtc.TrackRemote
	pending []mediaCandidateInit
	remote  bool
	muted   atomic.Bool
	paused  atomic.Bool // camera off
	fed     atomic.Int64
	width   int
	height  int
	fps     int
	closed  chan struct{}
}

func newMediaPeer(servers []mediaICEServer, d mediaDirection) (*mediaPeer, error) {
	m := &webrtc.MediaEngine{}
	if err := m.RegisterDefaultCodecs(); err != nil {
		return nil, err
	}
	reg := &interceptor.Registry{}
	if err := webrtc.ConfigureNack(m, reg); err != nil {
		return nil, err
	}
	if err := webrtc.ConfigureRTCPReports(reg); err != nil {
		return nil, err
	}
	if err := webrtc.ConfigureTWCCSender(m, reg); err != nil {
		return nil, err
	}
	p := &mediaPeer{notify: make(chan struct{}, 1), tracks: map[string]*webrtc.TrackLocalStaticRTP{}, senders: map[string]*webrtc.RTPSender{},
		inputs: map[string]*net.UDPConn{}, outputs: map[string]*net.UDPConn{}, remotes: map[string]*webrtc.TrackRemote{}, closed: make(chan struct{})}
	statsI, err := stats.NewInterceptor()
	if err != nil {
		return nil, err
	}
	statsI.OnNewPeerConnection(func(_ string, g stats.Getter) { p.getter = g })
	reg.Add(statsI)
	config := webrtc.Configuration{}
	for _, s := range servers {
		if len(s.URLs) == 0 {
			continue
		}
		ice := webrtc.ICEServer{URLs: s.URLs, Username: s.Username}
		if s.Credential != "" {
			ice.Credential = s.Credential
		}
		config.ICEServers = append(config.ICEServers, ice)
	}
	api := webrtc.NewAPI(webrtc.WithMediaEngine(m), webrtc.WithInterceptorRegistry(reg))
	pc, err := api.NewPeerConnection(config)
	if err != nil {
		return nil, err
	}
	p.pc = pc
	if d.SendVideo {
		if err := p.addSendTrack("video", webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeH264, ClockRate: 90000,
			SDPFmtpLine: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f"}); err != nil {
			pc.Close()
			return nil, err
		}
	}
	if d.SendAudio {
		if err := p.addSendTrack("audio", webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeOpus, ClockRate: 48000, Channels: 2,
			SDPFmtpLine: "minptime=10;useinbandfec=1"}); err != nil {
			pc.Close()
			return nil, err
		}
	}
	if d.RecvAudio {
		if _, err := pc.AddTransceiverFromKind(webrtc.RTPCodecTypeAudio, webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
			pc.Close()
			return nil, err
		}
	}
	if d.RecvVideo {
		if _, err := pc.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo, webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
			pc.Close()
			return nil, err
		}
	}
	pc.OnICECandidate(func(c *webrtc.ICECandidate) {
		if c == nil {
			p.push(mediaPeerEvent{Kind: "candidates_done"})
			return
		}
		init := c.ToJSON()
		p.push(mediaPeerEvent{Kind: "candidate", Candidate: &mediaCandidateInit{Candidate: init.Candidate, SDPMid: init.SDPMid,
			SDPMLineIndex: init.SDPMLineIndex, UsernameFragment: init.UsernameFragment}})
	})
	pc.OnICEConnectionStateChange(func(s webrtc.ICEConnectionState) { p.push(mediaPeerEvent{Kind: "ice", State: s.String()}) })
	pc.OnConnectionStateChange(func(s webrtc.PeerConnectionState) { p.push(mediaPeerEvent{Kind: "connection", State: s.String()}) })
	pc.OnTrack(func(t *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		p.mu.Lock()
		p.remotes[t.Kind().String()] = t
		p.mu.Unlock()
		p.push(mediaPeerEvent{Kind: "track", Track: t, State: t.Kind().String()})
	})
	return p, nil
}

func (p *mediaPeer) addSendTrack(kind string, codec webrtc.RTPCodecCapability) error {
	track, err := webrtc.NewTrackLocalStaticRTP(codec, kind, "indiebiz-"+kind)
	if err != nil {
		return err
	}
	sender, err := p.pc.AddTrack(track)
	if err != nil {
		return err
	}
	go func() { // drain RTCP so the interceptors (NACK/reports) keep running
		buf := make([]byte, 1500)
		for {
			if _, _, err := sender.Read(buf); err != nil {
				return
			}
		}
	}()
	p.tracks[kind], p.senders[kind] = track, sender
	return nil
}

func (p *mediaPeer) push(ev mediaPeerEvent) {
	p.mu.Lock()
	p.queue = append(p.queue, ev)
	p.mu.Unlock()
	select {
	case p.notify <- struct{}{}:
	default:
	}
}

// events returns and clears the queued engine events (wait on p.notify first).
func (p *mediaPeer) events() []mediaPeerEvent {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := p.queue
	p.queue = nil
	return out
}

// openInput binds a loopback UDP port whose RTP packets feed the send track.
// Payload type and SSRC are rewritten by pion per negotiated binding.
func (p *mediaPeer) openInput(kind string) (int, error) {
	track := p.tracks[kind]
	if track == nil {
		return 0, fmt.Errorf("no %s track", kind)
	}
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 0})
	if err != nil {
		return 0, err
	}
	_ = conn.SetReadBuffer(1 << 20)
	p.inputs[kind] = conn
	go func() {
		buf := make([]byte, 1600)
		for {
			n, _, err := conn.ReadFromUDP(buf)
			if err != nil {
				return
			}
			if p.muted.Load() && kind == "audio" || p.paused.Load() && kind == "video" {
				continue
			}
			var packet rtp.Packet
			if packet.Unmarshal(buf[:n]) != nil {
				continue
			}
			if track.WriteRTP(&packet) == nil {
				p.fed.Add(1)
			}
		}
	}()
	return conn.LocalAddr().(*net.UDPAddr).Port, nil
}

func (p *mediaPeer) updateICE(servers []mediaICEServer) error {
	config := p.pc.GetConfiguration()
	config.ICEServers = nil
	for _, server := range servers {
		config.ICEServers = append(config.ICEServers, webrtc.ICEServer{URLs: server.URLs, Username: server.Username, Credential: server.Credential})
	}
	return p.pc.SetConfiguration(config)
}

// handleOffer applies the hub's offer and returns the local answer SDP.
func (p *mediaPeer) handleOffer(sdp string) (string, error) {
	if err := p.pc.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: sdp}); err != nil {
		return "", err
	}
	p.mu.Lock()
	p.remote = true
	pending := p.pending
	p.pending = nil
	p.mu.Unlock()
	for _, c := range pending {
		_ = p.pc.AddICECandidate(webrtc.ICECandidateInit{Candidate: c.Candidate, SDPMid: c.SDPMid, SDPMLineIndex: c.SDPMLineIndex, UsernameFragment: c.UsernameFragment})
	}
	answer, err := p.pc.CreateAnswer(nil)
	if err != nil {
		return "", err
	}
	if err := p.pc.SetLocalDescription(answer); err != nil {
		return "", err
	}
	return p.pc.LocalDescription().SDP, nil
}

// addCandidate applies a trickled remote candidate, buffering it until an offer
// of the current generation has been applied.
func (p *mediaPeer) addCandidate(c mediaCandidateInit) error {
	p.mu.Lock()
	if !p.remote {
		p.pending = append(p.pending, c)
		p.mu.Unlock()
		return nil
	}
	p.mu.Unlock()
	return p.pc.AddICECandidate(webrtc.ICECandidateInit{Candidate: c.Candidate, SDPMid: c.SDPMid, SDPMLineIndex: c.SDPMLineIndex, UsernameFragment: c.UsernameFragment})
}

// forwardRemote copies a remote track's RTP to loopback UDP port with the
// payload type ffplay's SDP declares; video gets periodic PLIs for keyframes.
func (p *mediaPeer) forwardRemote(track *webrtc.TrackRemote, port int, payloadType uint8) error {
	conn, err := net.DialUDP("udp4", nil, &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: port})
	if err != nil {
		return err
	}
	p.mu.Lock()
	p.outputs[track.Kind().String()] = conn
	p.mu.Unlock()
	if track.Kind() == webrtc.RTPCodecTypeVideo {
		go func() {
			ticker := time.NewTicker(2 * time.Second)
			defer ticker.Stop()
			for {
				select {
				case <-p.closed:
					return
				case <-ticker.C:
					_ = p.pc.WriteRTCP([]rtcp.Packet{&rtcp.PictureLossIndication{MediaSSRC: uint32(track.SSRC())}})
				}
			}
		}()
	}
	go func() {
		defer conn.Close()
		buf := make([]byte, 1600)
		for {
			n, _, err := track.Read(buf)
			if err != nil {
				return
			}
			var packet rtp.Packet
			if packet.Unmarshal(buf[:n]) != nil {
				continue
			}
			packet.Header.PayloadType = payloadType
			raw, err := packet.Marshal()
			if err == nil {
				_, _ = conn.Write(raw)
			}
		}
	}()
	return nil
}

// connected is true while ICE is usable (connected/completed).
func (p *mediaPeer) connected() bool {
	st := p.pc.ICEConnectionState()
	return st == webrtc.ICEConnectionStateConnected || st == webrtc.ICEConnectionStateCompleted
}

// path reports direct|relay from the selected ICE pair ("" before selection).
func (p *mediaPeer) path() string {
	pair, err := p.pc.SCTP().Transport().ICETransport().GetSelectedCandidatePair()
	if err != nil || pair == nil || pair.Local == nil || pair.Remote == nil {
		return ""
	}
	return mediaPath(pair.Local.Typ.String(), pair.Remote.Typ.String())
}

// sample gathers engine statistics into the engine-neutral sample.
func (p *mediaPeer) sample() mediaStatsSample {
	s := mediaStatsSample{At: time.Now(), Width: p.width, Height: p.height, FPS: p.fps}
	if pair, ok := p.pc.SCTP().Transport().ICETransport().GetSelectedCandidatePairStats(); ok && pair.CurrentRoundTripTime > 0 {
		s.RTT = time.Duration(pair.CurrentRoundTripTime * float64(time.Second))
	}
	if p.getter == nil {
		return s
	}
	for _, sender := range p.senders {
		params := sender.GetParameters()
		if len(params.Encodings) == 0 {
			continue
		}
		st := p.getter.Get(uint32(params.Encodings[0].SSRC))
		if st == nil {
			continue
		}
		s.Bytes += st.OutboundRTPStreamStats.BytesSent
		s.Packets += st.OutboundRTPStreamStats.PacketsSent
		s.PacketsLost += st.RemoteInboundRTPStreamStats.PacketsLost
		if st.RemoteInboundRTPStreamStats.Jitter > s.Jitter {
			s.Jitter = st.RemoteInboundRTPStreamStats.Jitter
		}
		if st.RemoteInboundRTPStreamStats.FractionLost > s.FractionLost {
			s.FractionLost = st.RemoteInboundRTPStreamStats.FractionLost
		}
		if s.RTT == 0 && st.RemoteInboundRTPStreamStats.RoundTripTime > 0 {
			s.RTT = st.RemoteInboundRTPStreamStats.RoundTripTime
		}
	}
	p.mu.Lock()
	remotes := make([]*webrtc.TrackRemote, 0, len(p.remotes))
	for _, t := range p.remotes {
		remotes = append(remotes, t)
	}
	p.mu.Unlock()
	for _, t := range remotes {
		st := p.getter.Get(uint32(t.SSRC()))
		if st == nil {
			continue
		}
		s.Bytes += st.InboundRTPStreamStats.BytesReceived
		s.Packets += st.InboundRTPStreamStats.PacketsReceived
		s.PacketsLost += st.InboundRTPStreamStats.PacketsLost
		if st.InboundRTPStreamStats.Jitter > s.Jitter {
			s.Jitter = st.InboundRTPStreamStats.Jitter
		}
	}
	return s
}

func (p *mediaPeer) close() {
	select {
	case <-p.closed:
		return
	default:
		close(p.closed)
	}
	for _, c := range p.inputs {
		_ = c.Close()
	}
	_ = p.pc.Close()
}
