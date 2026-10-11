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
