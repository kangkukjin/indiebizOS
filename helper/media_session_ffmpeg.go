package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Capture and playback run as ffmpeg/ffplay subprocesses (no cgo): the camera or
// microphone is encoded to RTP on loopback UDP, which the helper forwards into
// the WebRTC engine; received RTP goes the other way into ffplay via an SDP file.

// mediaFFmpegCandidates lists install locations searched after an explicit
// override, the helper data dir bin/, and PATH. root prefixes the system paths
// so tests never see the host's binaries.
func mediaFFmpegCandidates(goos, root, home string) []string {
	sys := func(p string) string { return filepath.Join(root, p) }
	switch goos {
	case "darwin":
		return []string{sys("/opt/homebrew/bin"), sys("/usr/local/bin"), sys("/opt/local/bin")}
	case "windows":
		c := []string{sys(`C:\ffmpeg\bin`), sys(`C:\Program Files\ffmpeg\bin`), sys(`C:\ProgramData\chocolatey\bin`)}
		if home != "" {
			c = append(c, filepath.Join(home, `scoop\shims`), filepath.Join(home, `AppData\Local\Microsoft\WinGet\Links`))
		}
		return c
	default:
		c := []string{sys("/usr/bin"), sys("/usr/local/bin"), sys("/snap/bin")}
		if home != "" {
			c = append(c, filepath.Join(home, ".local/bin"))
		}
		return c
	}
}

// mediaFindBinary resolves ffmpeg/ffplay: override (absolute, executable) →
// <dataDir>/bin → PATH → per-OS locations. Returns "" when absent.
func mediaFindBinary(name, override, dataDir, goos, pathEnv string, candidates []string) string {
	exe := name
	if goos == "windows" {
		exe += ".exe"
	}
	if override != "" {
		if filepath.Base(override) != exe && filepath.Base(override) != name {
			override = filepath.Join(filepath.Dir(override), exe)
		}
		if isExecutableFile(goos, override) {
			return override
		}
	}
	if dataDir != "" {
		if p := filepath.Join(dataDir, "bin", exe); isExecutableFile(goos, p) {
			return p
		}
	}
	for _, dir := range filepath.SplitList(pathEnv) {
		if dir == "" || !filepath.IsAbs(dir) {
			continue
		}
		if p := filepath.Join(dir, exe); isExecutableFile(goos, p) {
			return p
		}
	}
	for _, dir := range candidates {
		if p := filepath.Join(dir, exe); isExecutableFile(goos, p) {
			return p
		}
	}
	return ""
}

type mediaDevice struct {
	Index int
	Name  string
}

type mediaDevices struct {
	Video, Audio []mediaDevice
}

var mediaAVFLine = regexp.MustCompile(`\[(\d+)\]\s+(.+)$`)

// parseAVFoundationDevices reads `ffmpeg -f avfoundation -list_devices true -i ""`.
// Screens ("Capture screen N") are not cameras.
func parseAVFoundationDevices(stderr string) mediaDevices {
	var d mediaDevices
	section := ""
	for _, line := range strings.Split(stderr, "\n") {
		switch {
		case strings.Contains(line, "AVFoundation video devices"):
			section = "video"
			continue
		case strings.Contains(line, "AVFoundation audio devices"):
			section = "audio"
			continue
		}
		m := mediaAVFLine.FindStringSubmatch(strings.TrimSpace(line))
		if m == nil || section == "" || !strings.Contains(line, "AVFoundation") {
			continue
		}
		idx, _ := strconv.Atoi(m[1])
		dev := mediaDevice{idx, strings.TrimSpace(m[2])}
		if section == "video" && !strings.HasPrefix(dev.Name, "Capture screen") {
			d.Video = append(d.Video, dev)
		} else if section == "audio" {
			d.Audio = append(d.Audio, dev)
		}
	}
	return d
}

var mediaDShowLine = regexp.MustCompile(`"([^"]+)"\s+\((video|audio)\)`)

// parseDShowDevices reads `ffmpeg -list_devices true -f dshow -i dummy`.
func parseDShowDevices(stderr string) mediaDevices {
	var d mediaDevices
	for _, line := range strings.Split(stderr, "\n") {
		m := mediaDShowLine.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		if m[2] == "video" {
			d.Video = append(d.Video, mediaDevice{len(d.Video), m[1]})
		} else {
			d.Audio = append(d.Audio, mediaDevice{len(d.Audio), m[1]})
		}
	}
	return d
}

// mediaListDevices enumerates capture devices with the found ffmpeg (≤5 s).
func mediaListDevices(ctx context.Context, ffmpeg, goos string) mediaDevices {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	switch goos {
	case "darwin":
		out, _ := exec.CommandContext(ctx, ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", "").CombinedOutput()
		return parseAVFoundationDevices(string(out))
	case "windows":
		out, _ := exec.CommandContext(ctx, ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy").CombinedOutput()
		return parseDShowDevices(string(out))
	default:
		var d mediaDevices
		nodes, _ := filepath.Glob("/dev/video*")
		for i, n := range nodes {
			d.Video = append(d.Video, mediaDevice{i, n})
		}
		if _, e := os.Stat("/dev/snd"); e == nil {
			d.Audio = append(d.Audio, mediaDevice{0, "default"})
		}
		return d
	}
}

// mediaEncoders reports which H.264/Opus encoders the ffmpeg build offers.
func mediaEncoders(ctx context.Context, ffmpeg string) map[string]bool {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	out, _ := exec.CommandContext(ctx, ffmpeg, "-hide_banner", "-encoders").Output()
	found := map[string]bool{}
	for _, name := range []string{"h264_videotoolbox", "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libopus"} {
		if strings.Contains(string(out), " "+name+" ") {
			found[name] = true
		}
	}
	return found
}

// mediaCaptureSpec is everything a capture command needs; ports are loopback UDP
// listeners the helper already holds.
type mediaCaptureSpec struct {
	FFmpeg        string
	GOOS          string
	Encoders      map[string]bool
	Devices       mediaDevices
	Video, Audio  bool
	VideoDevice   string // name or index from the envelope track; "" = first camera
	AudioDevice   string
	Width, Height int
	FPS           int
	BitrateKbps   int
	VideoPort     int
	AudioPort     int
}

func (s *mediaCaptureSpec) defaults() {
	if s.Width <= 0 || s.Height <= 0 {
		s.Width, s.Height = 1280, 720
	}
	if s.FPS <= 0 {
		s.FPS = 30
	}
	if s.BitrateKbps <= 0 {
		s.BitrateKbps = 1500
	}
}

// mediaPickDevice turns the envelope's device hint into the platform selector.
func mediaPickDevice(goos string, list []mediaDevice, hint string) (string, bool) {
	if hint == "" {
		if len(list) == 0 {
			return "", false
		}
		hint = list[0].Name
	}
	for _, d := range list {
		if d.Name == hint || strconv.Itoa(d.Index) == hint {
			if goos == "darwin" {
				return strconv.Itoa(d.Index), true
			}
			return d.Name, true
		}
	}
	if goos == "linux" && strings.HasPrefix(hint, "/dev/") {
		return hint, true
	}
	return "", false
}

// mediaCaptureArgs builds the ffmpeg argument list. H.264 baseline keeps the
// browser-side decoder happy; zero-latency settings keep the pipe short.
func mediaCaptureArgs(s mediaCaptureSpec) ([]string, error) {
	s.defaults()
	args := []string{"-hide_banner", "-loglevel", "error", "-nostdin", "-fflags", "nobuffer", "-flags", "low_delay"}
	inputIdx := 0 // ffmpeg inputs are ordered video, then audio
	var vsel, asel string
	if s.Video {
		v, ok := mediaPickDevice(s.GOOS, s.Devices.Video, s.VideoDevice)
		if !ok {
			return nil, fmt.Errorf("camera not found")
		}
		vsel = v
	}
	if s.Audio {
		a, ok := mediaPickDevice(s.GOOS, s.Devices.Audio, s.AudioDevice)
		if !ok {
			return nil, fmt.Errorf("microphone not found")
		}
		asel = a
	}
	switch s.GOOS {
	case "darwin":
		if s.Video {
			args = append(args, "-f", "avfoundation", "-framerate", strconv.Itoa(s.FPS), "-video_size", fmt.Sprintf("%dx%d", s.Width, s.Height), "-i", vsel+":none")
		}
		if s.Audio {
			args = append(args, "-f", "avfoundation", "-i", "none:"+asel)
		}
	case "windows":
		if s.Video {
			args = append(args, "-f", "dshow", "-framerate", strconv.Itoa(s.FPS), "-video_size", fmt.Sprintf("%dx%d", s.Width, s.Height), "-i", "video="+vsel)
		}
		if s.Audio {
			args = append(args, "-f", "dshow", "-i", "audio="+asel)
		}
	default:
		if s.Video {
			args = append(args, "-f", "v4l2", "-framerate", strconv.Itoa(s.FPS), "-video_size", fmt.Sprintf("%dx%d", s.Width, s.Height), "-i", vsel)
		}
		if s.Audio {
			args = append(args, "-f", "pulse", "-i", asel)
		}
	}
	if s.Video {
		gop := strconv.Itoa(s.FPS * 2)
		rate := strconv.Itoa(s.BitrateKbps) + "k"
		enc := []string{"-map", strconv.Itoa(inputIdx) + ":v:0", "-an", "-pix_fmt", "yuv420p"}
		switch {
		case s.GOOS == "darwin" && s.Encoders["h264_videotoolbox"]:
			enc = append(enc, "-c:v", "h264_videotoolbox", "-realtime", "1", "-profile:v", "baseline", "-b:v", rate, "-g", gop)
		case s.Encoders["libx264"]:
			enc = append(enc, "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-profile:v", "baseline", "-level", "3.1",
				"-x264-params", "keyint="+gop+":scenecut=0:repeat-headers=1", "-b:v", rate, "-maxrate", rate, "-bufsize", strconv.Itoa(s.BitrateKbps/5)+"k")
		default:
			return nil, fmt.Errorf("no H.264 encoder in ffmpeg")
		}
		args = append(args, enc...)
		args = append(args, "-f", "rtp", "-payload_type", "96", fmt.Sprintf("rtp://127.0.0.1:%d?pkt_size=1200", s.VideoPort))
		inputIdx++
	}
	if s.Audio {
		if !s.Encoders["libopus"] {
			return nil, fmt.Errorf("no Opus encoder in ffmpeg")
		}
		args = append(args, "-map", strconv.Itoa(inputIdx)+":a:0", "-vn", "-c:a", "libopus", "-b:a", "48k", "-ar", "48000", "-ac", "2",
			"-application", "lowdelay", "-frame_duration", "20", "-f", "rtp", "-payload_type", "111", fmt.Sprintf("rtp://127.0.0.1:%d?pkt_size=1200", s.AudioPort))
	}
	return args, nil
}

// mediaPlaybackSDP describes loopback RTP for ffplay (pion "webrtc-to-rtp").
// Payload types are the negotiated ones so ffplay decodes what pion forwards.
func mediaPlaybackSDP(audioPort int, audioPT uint8, videoPort int, videoPT uint8) string {
	var b strings.Builder
	b.WriteString("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=indiebiz media session\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n")
	if audioPort > 0 {
		fmt.Fprintf(&b, "m=audio %d RTP/AVP %d\r\na=rtpmap:%d opus/48000/2\r\na=fmtp:%d minptime=10;useinbandfec=1\r\n", audioPort, audioPT, audioPT, audioPT)
	}
	if videoPort > 0 {
		fmt.Fprintf(&b, "m=video %d RTP/AVP %d\r\na=rtpmap:%d H264/90000\r\na=fmtp:%d packetization-mode=1\r\n", videoPort, videoPT, videoPT, videoPT)
	}
	return b.String()
}

func mediaPlayArgs(sdpPath string, window bool) []string {
	args := []string{"-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,udp,rtp", "-fflags", "nobuffer", "-flags", "low_delay",
		"-probesize", "32", "-analyzeduration", "0", "-autoexit", "-i", sdpPath}
	if !window {
		args = append(args, "-nodisp")
	} else {
		args = append(args, "-window_title", "IndieBiz 미디어")
	}
	return args
}

// mediaCaps is the capability block reported on sync (cached 10 min: it runs
// ffmpeg -list_devices).
type mediaCaps struct {
	Camera, Microphone, Speaker, Display, FFmpeg bool
	FFmpegPath, FFplayPath                       string
	Encoders                                     map[string]bool
	Devices                                      mediaDevices
}

var mediaCapsCache struct {
	mu   sync.Mutex
	at   time.Time
	key  string
	caps mediaCaps
}

func mediaProbe(ctx context.Context, override, dataDir string) mediaCaps {
	key := override + "\x00" + dataDir
	mediaCapsCache.mu.Lock()
	if mediaCapsCache.key == key && time.Since(mediaCapsCache.at) < 10*time.Minute {
		c := mediaCapsCache.caps
		mediaCapsCache.mu.Unlock()
		return c
	}
	mediaCapsCache.mu.Unlock()
	home, _ := os.UserHomeDir()
	goos := runtime.GOOS
	cand := mediaFFmpegCandidates(goos, "", home)
	c := mediaCaps{Encoders: map[string]bool{}}
	c.FFmpegPath = mediaFindBinary("ffmpeg", override, dataDir, goos, os.Getenv("PATH"), cand)
	c.FFplayPath = mediaFindBinary("ffplay", override, dataDir, goos, os.Getenv("PATH"), cand)
	if c.FFmpegPath != "" {
		c.FFmpeg = true
		c.Encoders = mediaEncoders(ctx, c.FFmpegPath)
		c.Devices = mediaListDevices(ctx, c.FFmpegPath, goos)
		h264 := c.Encoders["h264_videotoolbox"] || c.Encoders["libx264"]
		c.Camera = h264 && len(c.Devices.Video) > 0
		c.Microphone = c.Encoders["libopus"] && len(c.Devices.Audio) > 0
	}
	c.Speaker = c.FFplayPath != ""
	c.Display = c.Speaker && (goos != "linux" || os.Getenv("DISPLAY") != "" || os.Getenv("WAYLAND_DISPLAY") != "")
	mediaCapsCache.mu.Lock()
	mediaCapsCache.at, mediaCapsCache.key, mediaCapsCache.caps = time.Now(), key, c
	mediaCapsCache.mu.Unlock()
	return c
}

func (c mediaCaps) report(engine string, playback bool) map[string]interface{} {
	return map[string]interface{}{"camera": c.Camera, "microphone": c.Microphone, "speaker": c.Speaker, "playback": playback,
		"display": c.Display, "ffmpeg": c.FFmpeg, "engine": engine}
}
