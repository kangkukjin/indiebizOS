package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

// Playback (content delivery, contract §7): the session-scoped player. mpv is
// driven over its JSON IPC so position/pause/volume are real, not estimated;
// afplay (macOS audio fallback) only reports coarse state.

type mediaPlaybackState struct {
	Playing   bool    `json:"playing"`
	Paused    bool    `json:"paused"`
	PositionS float64 `json:"position_s"`
	DurationS float64 `json:"duration_s,omitempty"`
	Volume    float64 `json:"volume"`
	Control   bool    `json:"control"` // pause/seek/volume honoured
	Ended     bool    `json:"ended,omitempty"`
}

type mediaPlayback struct {
	cmd     *exec.Cmd
	release func()
	ipc     io.ReadWriteCloser
	ipcPath string
	mu      sync.Mutex
	reqID   int
	pending map[int]chan json.RawMessage
	started time.Time
	volume  float64
	coarse  bool
	done    chan struct{}
	exitErr error
	events  chan string
}

// mediaIPCPath picks the mpv IPC endpoint for this OS. Unix sockets live in the
// OS temp dir under a short name: sun_path is 104 bytes on macOS, and the
// helper's data dir (or a test tempdir) can exceed that.
func mediaIPCPath(_ string, sid string) string {
	if runtime.GOOS == "windows" {
		return `\\.\pipe\indiebiz-media-` + sid[:12]
	}
	return filepath.Join(os.TempDir(), "ibz-media-"+sid[:12]+".sock")
}

// startMediaPlayback launches the player for source at position. The supervisor
// (when not under test) reaps the player if the helper dies.
func startMediaPlayback(ctx context.Context, r *residentRuntime, jid, dir, source string, content mediaContent, mode string) (*mediaPlayback, map[string]interface{}) {
	home, _ := os.UserHomeDir()
	mpv, missing := residentSelectMediaPlayer(source, mode, runtime.GOOS, r.cfg.DataDir, os.Getenv("PATH"), mediaPlayerCandidates(runtime.GOOS, "", home))
	if missing != nil {
		return nil, missing
	}
	p := &mediaPlayback{pending: map[int]chan json.RawMessage{}, volume: 100, done: make(chan struct{}), events: make(chan string, 16)}
	if content.HasVolume {
		p.volume = content.Volume
	}
	var cmd *exec.Cmd
	if mpv != "" {
		p.ipcPath = mediaIPCPath(dir, jid)
		args := []string{"--no-config", "--no-terminal", "--idle=no", "--keep-open=no", "--input-ipc-server=" + p.ipcPath,
			fmt.Sprintf("--start=%g", content.PositionS), fmt.Sprintf("--volume=%g", p.volume)}
		if content.Paused {
			args = append(args, "--pause")
		}
		if mode != "interactive" {
			args = append(args, "--no-video")
		}
		args = append(args, "--", source)
		cmd = exec.CommandContext(ctx, mpv, args...)
	} else {
		vol := p.volume
		cmd = exec.CommandContext(ctx, "/usr/bin/afplay", residentAfplayArgs(source, &vol)...)
		p.coarse = true
	}
	cmd.Dir = dir
	cmd.Stdout, cmd.Stderr = io.Discard, io.Discard
	cmd, p.release = mediaSuperviseProcess(ctx, r, cmd, jid+"-play")
	if err := cmd.Start(); err != nil {
		p.release()
		return nil, errResult("content_unavailable", "플레이어를 시작하지 못했습니다: "+err.Error())
	}
	p.cmd, p.started = cmd, time.Now()
	go func() { p.exitErr = cmd.Wait(); p.release(); close(p.done) }()
	if !p.coarse {
		if err := p.connectIPC(ctx); err != nil {
			p.close()
			return nil, errResult("content_unavailable", "플레이어 제어 통로를 열지 못했습니다")
		}
	}
	return p, nil
}

// mediaSuperviseProcess wraps a long-lived media child in the resident supervisor
// so a helper crash still ends capture/playback (tests run the child directly).
func mediaSuperviseProcess(ctx context.Context, r *residentRuntime, cmd *exec.Cmd, jid string) (*exec.Cmd, func()) {
	if r == nil || strings.HasSuffix(os.Args[0], ".test") {
		configureResidentDetached(cmd)
		cmd.WaitDelay = 2 * time.Second
		return cmd, func() {}
	}
	stdout, stderr := cmd.Stdout, cmd.Stderr
	supervised, release, err := residentSupervise(ctx, cmd, r.cfg.DataDir, jid)
	if err != nil {
		configureResidentDetached(cmd)
		return cmd, func() {}
	}
	supervised.Stdout, supervised.Stderr = stdout, stderr
	return supervised, release
}

func (p *mediaPlayback) connectIPC(ctx context.Context) error {
	deadline := time.Now().Add(8 * time.Second)
	var conn io.ReadWriteCloser
	var err error
	for {
		conn, err = mediaIPCDial(p.ipcPath)
		if err == nil {
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-p.done:
			return fmt.Errorf("player exited")
		case <-time.After(150 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			return err
		}
	}
	p.ipc = conn
	go p.readIPC()
	return nil
}

func (p *mediaPlayback) readIPC() {
	scanner := bufio.NewScanner(p.ipc)
	scanner.Buffer(make([]byte, 65536), 1024*1024)
	for scanner.Scan() {
		var msg struct {
			RequestID *int            `json:"request_id"`
			Event     string          `json:"event"`
			Data      json.RawMessage `json:"data"`
			Error     string          `json:"error"`
		}
		if json.Unmarshal(scanner.Bytes(), &msg) != nil {
			continue
		}
		if msg.RequestID != nil {
			p.mu.Lock()
			ch := p.pending[*msg.RequestID]
			delete(p.pending, *msg.RequestID)
			p.mu.Unlock()
			if ch != nil {
				if msg.Error != "" && msg.Error != "success" {
					ch <- nil
				} else {
					ch <- msg.Data
				}
			}
		} else if msg.Event != "" {
			select {
			case p.events <- msg.Event:
			default:
			}
		}
	}
}

// command sends one mpv IPC command and waits ≤2 s for its reply.
func (p *mediaPlayback) command(args ...interface{}) (json.RawMessage, error) {
	if p.ipc == nil {
		return nil, fmt.Errorf("no control channel")
	}
	ch := make(chan json.RawMessage, 1)
	p.mu.Lock()
	p.reqID++
	id := p.reqID
	p.pending[id] = ch
	line, _ := json.Marshal(map[string]interface{}{"command": args, "request_id": id})
	_, err := p.ipc.Write(append(line, '\n'))
	p.mu.Unlock()
	if err != nil {
		return nil, err
	}
	select {
	case data := <-ch:
		if data == nil {
			return nil, fmt.Errorf("mpv refused")
		}
		return data, nil
	case <-time.After(2 * time.Second):
		p.mu.Lock()
		delete(p.pending, id)
		p.mu.Unlock()
		return nil, fmt.Errorf("mpv timeout")
	}
}

func (p *mediaPlayback) property(name string) (float64, bool, error) {
	data, err := p.command("get_property", name)
	if err != nil {
		return 0, false, err
	}
	var f float64
	if json.Unmarshal(data, &f) == nil {
		return f, false, nil
	}
	var b bool
	if json.Unmarshal(data, &b) == nil {
		return 0, b, nil
	}
	return 0, false, fmt.Errorf("unexpected property type")
}

// state reports the real player state (mpv) or the coarse afplay estimate.
func (p *mediaPlayback) state() mediaPlaybackState {
	s := mediaPlaybackState{Volume: p.volume, Control: !p.coarse}
	select {
	case <-p.done:
		s.Ended = true
		return s
	default:
	}
	s.Playing = true
	if p.coarse {
		s.PositionS = time.Since(p.started).Seconds()
		return s
	}
	if pos, _, err := p.property("time-pos"); err == nil {
		s.PositionS = pos
	}
	if _, paused, err := p.property("pause"); err == nil {
		s.Paused = paused
		s.Playing = !paused
	}
	if dur, _, err := p.property("duration"); err == nil {
		s.DurationS = dur
	}
	if vol, _, err := p.property("volume"); err == nil {
		s.Volume = vol
	}
	return s
}

// apply honours an update frame; returns false when the player cannot be controlled.
func (p *mediaPlayback) apply(u mediaUpdate) bool {
	if p.coarse {
		return false
	}
	ok := true
	if u.Paused != nil {
		_, err := p.command("set_property", "pause", *u.Paused)
		ok = ok && err == nil
	}
	if u.PositionS != nil && *u.PositionS >= 0 {
		_, err := p.command("seek", *u.PositionS, "absolute")
		ok = ok && err == nil
	}
	if u.Volume != nil {
		_, err := p.command("set_property", "volume", *u.Volume)
		ok = ok && err == nil
		if err == nil {
			p.volume = *u.Volume
		}
	}
	return ok
}

func (p *mediaPlayback) close() {
	if p.ipc != nil {
		_, _ = p.command("quit")
		_ = p.ipc.Close()
	}
	if p.release != nil {
		p.release() // supervisor lease: the player tree ends even if Kill below is skipped
	}
	if p.cmd != nil && p.cmd.Process != nil {
		select {
		case <-p.done:
		case <-time.After(2 * time.Second):
			_ = p.cmd.Process.Kill()
			<-p.done
		}
	}
	if p.ipcPath != "" && runtime.GOOS != "windows" {
		_ = os.Remove(p.ipcPath)
	}
}
