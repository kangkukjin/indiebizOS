package main

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"github.com/gorilla/websocket"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

func TestBinaryWireLostAckReconnectAndRead(t *testing.T) {
	r := residentTestRuntime(t)
	var mu sync.Mutex
	var saved []byte
	writes := 0
	upgrade := websocket.Upgrader{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		conn, err := upgrade.Upgrade(w, req, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		var auth map[string]interface{}
		if conn.ReadJSON(&auth) != nil {
			return
		}
		if auth["key"] != r.cfg.Key {
			t.Error("missing auth")
			return
		}
		conn.WriteJSON(map[string]interface{}{"type": "ready", "version": 1, "route": "public"})
		for {
			kind, data, err := conn.ReadMessage()
			if err != nil {
				return
			}
			if kind == websocket.BinaryMessage {
				if binary.BigEndian.Uint64(data[:8]) != 0 {
					t.Error("wrong offset")
					return
				}
				mu.Lock()
				writes++
				n := writes
				saved = append([]byte(nil), data[8:]...)
				mu.Unlock()
				if n == 1 {
					return
				} // server committed, acknowledgement lost
				conn.WriteJSON(map[string]interface{}{"offset": len(data) - 8})
			} else {
				var body map[string]interface{}
				json.Unmarshal(data, &body)
				if body["action"] == "read" {
					mu.Lock()
					batch := append(make([]byte, 8), saved...)
					mu.Unlock()
					conn.WriteMessage(websocket.BinaryMessage, batch)
				}
			}
		}
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	wire := newTransferWire(r, residentID(), map[string]interface{}{"binary": map[string]interface{}{"version": float64(1)}})
	defer wire.close()
	payload := make([]byte, 1024*1024)
	for i := range payload {
		payload[i] = byte(i)
	}
	out, err := wire.call(context.Background(), map[string]interface{}{"action": "write", "offset": int64(0), "data": payload})
	if err != nil || out["offset"] != float64(len(payload)) {
		t.Fatal(out, err)
	}
	out, err = wire.call(context.Background(), map[string]interface{}{"action": "read", "offset": int64(0), "chunk_size": 1024 * 1024})
	if err != nil {
		t.Fatal(err)
	}
	got, err := transferBytes(out["data"])
	if err != nil || string(got) != string(payload) {
		t.Fatal("payload changed", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if writes != 2 {
		t.Fatalf("writes=%d", writes)
	}
}

func TestScreenQualityBoundsAndHysteresis(t *testing.T) {
	q := screenQuality{}
	for i := 0; i < 50; i++ {
		q.observe(time.Second)
	}
	width, quality := q.dimensions()
	if width != 640 || quality != 35 || q.interval() != time.Second/3 {
		t.Fatal(q, width, quality)
	}
	for i := 0; i < 59; i++ {
		q.observe(time.Millisecond)
	}
	if q.level != 3 {
		t.Fatal("recovered too quickly")
	}
	q.observe(time.Millisecond)
	if q.level != 2 {
		t.Fatal("never recovers")
	}
	for i := 0; i < 200; i++ {
		q.observe(time.Millisecond)
	}
	if q.level != 0 {
		t.Fatal(q)
	}
}
