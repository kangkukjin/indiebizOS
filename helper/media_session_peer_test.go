//go:build !legacy

package main

import (
	"context"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/pion/rtp"
	"github.com/pion/webrtc/v4"
)

// mediaLoopback wires the helper's answerer peer to an in-process pion offerer
// (standing in for the hub's browser engine) over host candidates.
type mediaLoopback struct {
	peer    *mediaPeer
	offerer *webrtc.PeerConnection
	video   chan *rtp.Packet // first packets the offerer receives on its video track
	audio   chan *rtp.Packet
	events  chan mediaPeerEvent // answerer events other than trickle candidates
}

func newMediaLoopback(t *testing.T, d mediaDirection, offererSends bool) *mediaLoopback {
	t.Helper()
	peer, err := newMediaPeer([]mediaICEServer{{URLs: nil}}, d)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(peer.close)
	offerer, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = offerer.Close() })
	lb := &mediaLoopback{peer: peer, offerer: offerer, video: make(chan *rtp.Packet, 64), audio: make(chan *rtp.Packet, 64), events: make(chan mediaPeerEvent, 64)}
	if d.SendVideo {
		if _, err := offerer.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo, webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
			t.Fatal(err)
		}
	}
	if d.SendAudio {
		if _, err := offerer.AddTransceiverFromKind(webrtc.RTPCodecTypeAudio, webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
			t.Fatal(err)
		}
	}
	offerer.OnTrack(func(tr *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		for {
			pkt, _, err := tr.ReadRTP()
			if err != nil {
				return
			}
			ch := lb.video
			if tr.Kind() == webrtc.RTPCodecTypeAudio {
				ch = lb.audio
			}
			select {
			case ch <- pkt:
			default:
			}
		}
	})
	// Offerer candidates are trickled before the offer is applied: exercises buffering.
	offerer.OnICECandidate(func(c *webrtc.ICECandidate) {
		if c == nil {
			return
		}
		init := c.ToJSON()
		_ = peer.addCandidate(mediaCandidateInit{Candidate: init.Candidate, SDPMid: init.SDPMid, SDPMLineIndex: init.SDPMLineIndex, UsernameFragment: init.UsernameFragment})
	})
	return lb
}

// negotiate runs offer → answer and pumps the answerer's trickle candidates back.
func (lb *mediaLoopback) negotiate(t *testing.T) string {
	t.Helper()
	offer, err := lb.offerer.CreateOffer(nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := lb.offerer.SetLocalDescription(offer); err != nil {
		t.Fatal(err)
	}
	answer, err := lb.peer.handleOffer(offer.SDP)
	if err != nil {
		t.Fatal(err)
	}
	if mediaFingerprint(answer) == "" {
		t.Fatal("answer without fingerprint")
	}
	if err := lb.offerer.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeAnswer, SDP: answer}); err != nil {
		t.Fatal(err)
	}
	go func() {
		for {
			select {
			case <-lb.peer.closed:
				return
			case <-lb.peer.notify:
				for _, ev := range lb.peer.events() {
					if ev.Kind == "candidate" && ev.Candidate != nil {
						c := ev.Candidate
						_ = lb.offerer.AddICECandidate(webrtc.ICECandidateInit{Candidate: c.Candidate, SDPMid: c.SDPMid, SDPMLineIndex: c.SDPMLineIndex, UsernameFragment: c.UsernameFragment})
						continue
					}
					select {
					case lb.events <- ev:
					default:
					}
				}
			}
		}
	}()
	return answer
}

func mediaWaitConnected(t *testing.T, peer *mediaPeer) {
	t.Helper()
	deadline := time.Now().Add(15 * time.Second)
	for !peer.connected() {
		if time.Now().After(deadline) {
			t.Fatal("ICE never connected:", peer.pc.ICEConnectionState())
		}
		time.Sleep(50 * time.Millisecond)
	}
}

// synthetic H.264 single-NAL packets (no ffmpeg needed)
func mediaFeedSynthetic(ctx context.Context, port int) {
	conn, err := net.DialUDP("udp4", nil, &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: port})
	if err != nil {
		return
	}
	defer conn.Close()
	payload := append([]byte{0x65, 0x88, 0x84, 0x00}, []byte(strings.Repeat("idr", 40))...)
	for i := uint16(1); ctx.Err() == nil; i++ {
		pkt := rtp.Packet{Header: rtp.Header{Version: 2, Marker: true, PayloadType: 96, SequenceNumber: i, Timestamp: uint32(i) * 6000, SSRC: 0x1234}, Payload: payload}
		raw, _ := pkt.Marshal()
		_, _ = conn.Write(raw)
		time.Sleep(20 * time.Millisecond)
	}
}

func TestMediaPeerLoopbackSendsLocalRTP(t *testing.T) {
	lb := newMediaLoopback(t, mediaDirection{SendVideo: true}, false)
	port, err := lb.peer.openInput("video")
	if err != nil || port == 0 {
		t.Fatal("input port", port, err)
	}
	answer := lb.negotiate(t)
	if _, h264 := mediaSDPPayloadTypes(answer); h264 == 0 {
		t.Fatal("answer negotiated no H264")
	}
	mediaWaitConnected(t, lb.peer)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go mediaFeedSynthetic(ctx, port)
	select {
	case pkt := <-lb.video:
		if len(pkt.Payload) < 4 || pkt.Payload[0] != 0x65 {
			t.Fatalf("unexpected payload %x", pkt.Payload[:4])
		}
		if pkt.SSRC == 0x1234 {
			t.Fatal("SSRC not rewritten by the track binding")
		}
	case <-time.After(15 * time.Second):
		t.Fatal("offerer received no RTP; fed:", lb.peer.fed.Load())
	}
	if lb.peer.fed.Load() == 0 {
		t.Fatal("reader forwarded nothing")
	}
	if p := lb.peer.path(); p != "direct" {
		t.Fatal("path", p)
	}
	// mute/camera-off stops forwarding without tearing down the track
	lb.peer.paused.Store(true)
	before := lb.peer.fed.Load()
	time.Sleep(200 * time.Millisecond)
	if lb.peer.fed.Load() != before {
		t.Fatal("camera off still forwards")
	}
	lb.peer.paused.Store(false)
	time.Sleep(300 * time.Millisecond)
	prev := lb.peer.sample()
	time.Sleep(600 * time.Millisecond)
	cur := lb.peer.sample()
	if cur.Bytes <= prev.Bytes || cur.Packets <= prev.Packets {
		t.Fatalf("sender stats not advancing: %+v -> %+v", prev, cur)
	}
	q := mediaQualityFrom(prev, cur)
	if q.BitrateKbps <= 0 {
		t.Fatalf("quality %+v", q)
	}
}

func TestMediaPeerLoopbackForwardsRemoteRTP(t *testing.T) {
	lb := newMediaLoopback(t, mediaDirection{RecvAudio: true}, true)
	track, err := webrtc.NewTrackLocalStaticRTP(webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeOpus, ClockRate: 48000, Channels: 2}, "audio", "hub")
	if err != nil {
		t.Fatal(err)
	}
	sender, err := lb.offerer.AddTrack(track)
	if err != nil {
		t.Fatal(err)
	}
	go func() {
		buf := make([]byte, 1500)
		for {
			if _, _, err := sender.Read(buf); err != nil {
				return
			}
		}
	}()
	answer := lb.negotiate(t)
	opus, _ := mediaSDPPayloadTypes(answer)
	if opus == 0 {
		t.Fatal("no opus in answer")
	}
	mediaWaitConnected(t, lb.peer)
	// stand-in for ffplay: a loopback UDP listener
	sink, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 0})
	if err != nil {
		t.Fatal(err)
	}
	defer sink.Close()
	port := sink.LocalAddr().(*net.UDPAddr).Port
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		for i := uint16(1); ctx.Err() == nil; i++ {
			_ = track.WriteRTP(&rtp.Packet{Header: rtp.Header{Version: 2, PayloadType: 111, SequenceNumber: i, Timestamp: uint32(i) * 960, SSRC: 77}, Payload: []byte{0xfc, 0xff, 0xfe}})
			time.Sleep(20 * time.Millisecond)
		}
	}()
	deadline := time.After(15 * time.Second)
	forwarded := false
	for !forwarded {
		select {
		case ev := <-lb.events:
			if ev.Kind == "track" && ev.Track != nil {
				if err := lb.peer.forwardRemote(ev.Track, port, 99); err != nil {
					t.Fatal(err)
				}
				forwarded = true
			}
		case <-deadline:
			t.Fatal("no remote track event")
		}
	}
	buf := make([]byte, 1500)
	_ = sink.SetReadDeadline(time.Now().Add(10 * time.Second))
	n, _, err := sink.ReadFromUDP(buf)
	if err != nil {
		t.Fatal("ffplay side got nothing:", err)
	}
	var pkt rtp.Packet
	if pkt.Unmarshal(buf[:n]) != nil || pkt.PayloadType != 99 || len(pkt.Payload) != 3 {
		t.Fatalf("forwarded packet %+v", pkt.Header)
	}
}

// Real ffmpeg as a fake camera (lavfi testsrc → libx264 → RTP). Skipped with
// -short, when ffmpeg is absent, or when INDIEBIZ_MEDIA_FFMPEG_TEST=0.
func TestMediaPeerFFmpegTestSource(t *testing.T) {
	if testing.Short() || os.Getenv("INDIEBIZ_MEDIA_FFMPEG_TEST") == "0" {
		t.Skip("short or disabled")
	}
	home, _ := os.UserHomeDir()
	ffmpeg := mediaFindBinary("ffmpeg", "", "", runtime.GOOS, os.Getenv("PATH"), mediaFFmpegCandidates(runtime.GOOS, "", home))
	if ffmpeg == "" {
		t.Skip("ffmpeg not installed")
	}
	if enc := mediaEncoders(context.Background(), ffmpeg); !enc["libx264"] {
		t.Skip("ffmpeg without libx264")
	}
	lb := newMediaLoopback(t, mediaDirection{SendVideo: true}, false)
	port, err := lb.peer.openInput("video")
	if err != nil {
		t.Fatal(err)
	}
	lb.negotiate(t)
	mediaWaitConnected(t, lb.peer)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	args := []string{"-hide_banner", "-loglevel", "error", "-nostdin", "-re", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15", "-t", "20",
		"-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-profile:v", "baseline",
		"-x264-params", "keyint=15:scenecut=0:repeat-headers=1", "-f", "rtp", "-payload_type", "96", "rtp://127.0.0.1:" + strconv.Itoa(port) + "?pkt_size=1200"}
	cmd := exec.CommandContext(ctx, ffmpeg, args...)
	cmd.Dir = t.TempDir()
	var tail mediaTail
	cmd.Stderr = &tail
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { cancel(); _ = cmd.Wait() }()
	got := 0
	deadline := time.After(20 * time.Second)
	for got < 20 {
		select {
		case pkt := <-lb.video:
			if len(pkt.Payload) == 0 {
				t.Fatal("empty H.264 payload")
			}
			got++
		case <-deadline:
			t.Fatalf("received %d packets; fed %d; ffmpeg: %s", got, lb.peer.fed.Load(), tail.String())
		}
	}
	if _, err := os.Stat(filepath.Join(cmd.Dir)); err != nil {
		t.Fatal(err)
	}
}
