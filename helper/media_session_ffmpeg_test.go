package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

const avfListing = `[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [1] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x1] [1] ZoomAudioDevice
Error opening input file .`

const dshowListing = `[dshow @ 0x1] "Integrated Webcam" (video)
[dshow @ 0x1]   Alternative name "@device_pnp_..."
[dshow @ 0x1] "Microphone (Realtek Audio)" (audio)
dummy: Immediate exit requested`

func TestMediaDeviceListings(t *testing.T) {
	d := parseAVFoundationDevices(avfListing)
	if len(d.Video) != 1 || d.Video[0].Name != "FaceTime HD Camera" || d.Video[0].Index != 0 || len(d.Audio) != 2 || d.Audio[1].Index != 1 {
		t.Fatalf("%+v", d)
	}
	d = parseDShowDevices(dshowListing)
	if len(d.Video) != 1 || d.Video[0].Name != "Integrated Webcam" || len(d.Audio) != 1 || d.Audio[0].Name != "Microphone (Realtek Audio)" {
		t.Fatalf("%+v", d)
	}
	if sel, ok := mediaPickDevice("darwin", parseAVFoundationDevices(avfListing).Audio, "ZoomAudioDevice"); !ok || sel != "1" {
		t.Fatal("darwin picks index", sel, ok)
	}
	if sel, ok := mediaPickDevice("windows", d.Video, ""); !ok || sel != "Integrated Webcam" {
		t.Fatal("windows picks name", sel, ok)
	}
	if _, ok := mediaPickDevice("darwin", nil, ""); ok {
		t.Fatal("empty list picked")
	}
}

func TestMediaFindBinary(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("exec bits")
	}
	root := t.TempDir()
	mk := func(p string) string {
		_ = os.MkdirAll(filepath.Dir(p), 0o755)
		_ = os.WriteFile(p, []byte("#!/bin/sh\n"), 0o755)
		return p
	}
	data := filepath.Join(root, "data")
	override := mk(filepath.Join(root, "pushed", "ffmpeg"))
	if got := mediaFindBinary("ffmpeg", override, data, "linux", "", nil); got != override {
		t.Fatal("override ignored", got)
	}
	if got := mediaFindBinary("ffmpeg", "", data, "linux", "", nil); got != "" {
		t.Fatal("found nothing expected", got)
	}
	inData := mk(filepath.Join(data, "bin", "ffmpeg"))
	if got := mediaFindBinary("ffmpeg", filepath.Join(root, "missing", "ffmpeg"), data, "linux", "", nil); got != inData {
		t.Fatal("data dir bin not used", got)
	}
	onPath := mk(filepath.Join(root, "path", "ffplay"))
	if got := mediaFindBinary("ffplay", "", data, "linux", filepath.Join(root, "path"), nil); got != onPath {
		t.Fatal("PATH not used", got)
	}
	cand := mk(filepath.Join(root, "opt", "ffplay"))
	if got := mediaFindBinary("ffplay", "", "", "linux", "", []string{filepath.Join(root, "opt")}); got != cand {
		t.Fatal("candidate not used", got)
	}
	_ = os.WriteFile(filepath.Join(root, "opt", "ffmpeg"), []byte("x"), 0o644) // not executable
	if got := mediaFindBinary("ffmpeg", "", "", "linux", "", []string{filepath.Join(root, "opt")}); got != "" {
		t.Fatal("non-executable accepted", got)
	}
}

func TestMediaCaptureArgs(t *testing.T) {
	devices := parseAVFoundationDevices(avfListing)
	spec := mediaCaptureSpec{FFmpeg: "/x/ffmpeg", GOOS: "darwin", Encoders: map[string]bool{"h264_videotoolbox": true, "libx264": true, "libopus": true},
		Devices: devices, Video: true, Audio: true, VideoPort: 5000, AudioPort: 5002}
	args, err := mediaCaptureArgs(spec)
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(args, " ")
	for _, want := range []string{"-f avfoundation -framerate 30 -video_size 1280x720 -i 0:none", "-f avfoundation -i none:0", "-map 0:v:0", "-map 1:a:0",
		"-c:v h264_videotoolbox", "-profile:v baseline", "-payload_type 96 rtp://127.0.0.1:5000?pkt_size=1200", "-c:a libopus", "-payload_type 111 rtp://127.0.0.1:5002?pkt_size=1200", "-nostdin"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("missing %q in %s", want, joined)
		}
	}
	spec.Encoders = map[string]bool{"libx264": true, "libopus": true}
	spec.Width, spec.Height, spec.FPS, spec.BitrateKbps = 640, 360, 15, 600
	spec.VideoDevice, spec.AudioDevice = "FaceTime HD Camera", "ZoomAudioDevice"
	args, _ = mediaCaptureArgs(spec)
	joined = strings.Join(args, " ")
	for _, want := range []string{"-c:v libx264 -preset ultrafast -tune zerolatency", "keyint=30:scenecut=0", "-b:v 600k", "-video_size 640x360", "-i none:1"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("missing %q in %s", want, joined)
		}
	}
	spec.Encoders = map[string]bool{"libopus": true}
	if _, err := mediaCaptureArgs(spec); err == nil {
		t.Fatal("no H.264 encoder accepted")
	}
	spec.Encoders = map[string]bool{"libx264": true}
	if _, err := mediaCaptureArgs(spec); err == nil {
		t.Fatal("no Opus encoder accepted")
	}
	spec.Encoders["libopus"] = true
	spec.VideoDevice = "Nonexistent"
	if _, err := mediaCaptureArgs(spec); err == nil {
		t.Fatal("unknown camera accepted")
	}
	win := mediaCaptureSpec{GOOS: "windows", Encoders: map[string]bool{"libx264": true}, Devices: parseDShowDevices(dshowListing), Video: true, VideoPort: 7000}
	args, err = mediaCaptureArgs(win)
	if err != nil || !strings.Contains(strings.Join(args, " "), "-f dshow -framerate 30 -video_size 1280x720 -i video=Integrated Webcam") {
		t.Fatal(err, args)
	}
	lin := mediaCaptureSpec{GOOS: "linux", Encoders: map[string]bool{"libx264": true}, Devices: mediaDevices{Video: []mediaDevice{{0, "/dev/video0"}}}, Video: true, VideoPort: 7000}
	args, err = mediaCaptureArgs(lin)
	if err != nil || !strings.Contains(strings.Join(args, " "), "-f v4l2 -framerate 30 -video_size 1280x720 -i /dev/video0") {
		t.Fatal(err, args)
	}
}

func TestMediaPlaybackSDPAndArgs(t *testing.T) {
	sdp := mediaPlaybackSDP(5004, 111, 5006, 102)
	for _, want := range []string{"v=0\r\n", "c=IN IP4 127.0.0.1\r\n", "m=audio 5004 RTP/AVP 111\r\na=rtpmap:111 opus/48000/2\r\n", "m=video 5006 RTP/AVP 102\r\na=rtpmap:102 H264/90000\r\na=fmtp:102 packetization-mode=1\r\n"} {
		if !strings.Contains(sdp, want) {
			t.Fatalf("missing %q in %q", want, sdp)
		}
	}
	if strings.Contains(mediaPlaybackSDP(5004, 111, 0, 0), "m=video") {
		t.Fatal("video line without port")
	}
	args := strings.Join(mediaPlayArgs("/tmp/recv.sdp", false), " ")
	if !strings.Contains(args, "-protocol_whitelist file,udp,rtp") || !strings.Contains(args, "-nodisp") || !strings.Contains(args, "-autoexit -i /tmp/recv.sdp") {
		t.Fatal(args)
	}
	if strings.Contains(strings.Join(mediaPlayArgs("/tmp/recv.sdp", true), " "), "-nodisp") {
		t.Fatal("window suppressed")
	}
	sid := residentID()
	p := mediaIPCPath(t.TempDir(), sid)
	if runtime.GOOS == "windows" {
		if !strings.HasPrefix(p, `\\.\pipe\indiebiz-media-`) {
			t.Fatal(p)
		}
	} else if !strings.HasSuffix(p, ".sock") || !strings.Contains(p, sid[:12]) {
		t.Fatal(p)
	}
}

func TestMediaCapsReportShape(t *testing.T) {
	rep := mediaCaps{Camera: true, FFmpeg: true}.report("pion/v4.2.23", true)
	for _, k := range []string{"camera", "microphone", "speaker", "playback", "display", "ffmpeg", "engine"} {
		if _, ok := rep[k]; !ok {
			t.Fatal("missing", k)
		}
	}
	if rep["engine"] != "pion/v4.2.23" || rep["camera"] != true || rep["speaker"] != false {
		t.Fatal(rep)
	}
}
