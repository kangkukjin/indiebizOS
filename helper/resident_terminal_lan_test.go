package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestTerminalLANPinAndFallback(t *testing.T) {
	var local, relay int32
	serve := func(counter *int32) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			atomic.AddInt32(counter, 1)
			upgrader := websocket.Upgrader{}
			conn, err := upgrader.Upgrade(w, r, nil)
			if err == nil {
				conn.Close()
			}
		}
	}
	lan := httptest.NewTLSServer(serve(&local))
	defer lan.Close()
	public := httptest.NewServer(serve(&relay))
	defer public.Close()
	digest := sha256.Sum256(lan.Certificate().Raw)
	spec := terminalSpec{Config: Config{Base: public.URL}, ID: strings.Repeat("a", 32),
		LAN: terminalLAN{URLs: []string{lan.URL}, SHA256: hex.EncodeToString(digest[:])}}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	conn, err := dialTerminal(ctx, spec)
	if err != nil {
		t.Fatal(err)
	}
	conn.Close()
	if atomic.LoadInt32(&local) != 1 || atomic.LoadInt32(&relay) != 0 {
		t.Fatal("did not prefer LAN")
	}
	spec.LAN.SHA256 = strings.Repeat("0", 64)
	conn, err = dialTerminal(ctx, spec)
	if err != nil {
		t.Fatal(err)
	}
	conn.Close()
	if atomic.LoadInt32(&local) != 1 || atomic.LoadInt32(&relay) != 1 {
		t.Fatal("bad pin reached LAN handler or no fallback")
	}
	spec.LAN.URLs = []string{"http://192.168.1.1:8765", "https://example.com", "https://8.8.8.8"}
	if dialTerminalLAN(ctx, spec) != nil {
		t.Fatal("accepted non-LAN route")
	}
}

func TestTerminalLANColdHandshakeAndPreferredRetry(t *testing.T) {
	var preferred, ordinary, relay int32
	serve := func(counter *int32, cold bool) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			n := atomic.AddInt32(counter, 1)
			if cold && n == 1 {
				http.Error(w, "warming up", http.StatusServiceUnavailable)
				return
			}
			if cold {
				// The old one-second budget incorrectly selected the external relay.
				time.Sleep(1100 * time.Millisecond)
			}
			upgrader := websocket.Upgrader{}
			conn, err := upgrader.Upgrade(w, r, nil)
			if err == nil {
				conn.Close()
			}
		}
	}
	fast := httptest.NewTLSServer(serve(&ordinary, false))
	defer fast.Close()
	cable := httptest.NewTLSServer(serve(&preferred, true))
	defer cable.Close()
	public := httptest.NewServer(serve(&relay, false))
	defer public.Close()
	digest := sha256.Sum256(cable.Certificate().Raw)
	spec := terminalSpec{Config: Config{Base: public.URL}, ID: residentID(), Channel: "transfer",
		LAN: terminalLAN{URLs: []string{fast.URL, cable.URL}, PreferredURLs: []string{cable.URL},
			SHA256: hex.EncodeToString(digest[:])}}
	conn, err := dialTerminal(context.Background(), spec)
	if err != nil {
		t.Fatal(err)
	}
	conn.Close()
	if atomic.LoadInt32(&preferred) != 2 || atomic.LoadInt32(&ordinary) != 0 || atomic.LoadInt32(&relay) != 0 {
		t.Fatal("preferred retry/slow handshake fell back", preferred, ordinary, relay)
	}
	// A disconnected cable must not prevent ordinary LAN from being tried.
	spec.LAN.PreferredURLs = []string{"https://127.0.0.1:1"}
	spec.LAN.URLs = []string{spec.LAN.PreferredURLs[0], fast.URL}
	digest = sha256.Sum256(fast.Certificate().Raw)
	spec.LAN.SHA256 = hex.EncodeToString(digest[:])
	conn, err = dialTerminal(context.Background(), spec)
	if err != nil {
		t.Fatal(err)
	}
	conn.Close()
	if atomic.LoadInt32(&ordinary) != 1 || atomic.LoadInt32(&relay) != 0 {
		t.Fatal("disconnected cable hid ordinary LAN")
	}
}

func TestTerminalLANLinkLocalValidationAndCancellation(t *testing.T) {
	id := residentID()
	for _, address := range []string{"https://169.254.254.233:9876", "https://192.168.0.1:9876"} {
		if terminalLANURL(address, id, "transfer") == "" {
			t.Fatal("rejected direct interface", address)
		}
	}
	for _, address := range []string{"http://169.254.1.1", "https://user@169.254.1.1", "https://169.254.1.1/?key=x", "https://8.8.8.8", "https://example.com"} {
		if terminalLANURL(address, id, "transfer") != "" {
			t.Fatal("accepted unsafe direct URL", address)
		}
	}
	var called int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&called, 1)
	}))
	defer server.Close()
	digest := sha256.Sum256(server.Certificate().Raw)
	spec := terminalSpec{Config: Config{Base: server.URL}, ID: id,
		LAN: terminalLAN{URLs: []string{server.URL}, SHA256: hex.EncodeToString(digest[:])}}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if conn, err := dialTerminal(ctx, spec); conn != nil || err == nil || atomic.LoadInt32(&called) != 0 {
		t.Fatal("cancelled probe opened a connection", err)
	}
}
