package main

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/gorilla/websocket"
)

// One bounded batch and durable acknowledgement in flight; no full-file buffers.
type transferWire struct {
	r      *residentRuntime
	tid    string
	batch  int
	binary bool
	lan    terminalLAN
	conn   *websocket.Conn
	route  string
}

func newTransferWire(r *residentRuntime, tid string, meta map[string]interface{}) *transferWire {
	w := &transferWire{r: r, tid: tid, batch: 128 * 1024}
	if offer, ok := meta["binary"].(map[string]interface{}); ok && offer["version"] == float64(1) {
		w.binary = true
		w.batch = 1024 * 1024
		b, _ := json.Marshal(offer["lan"])
		_ = json.Unmarshal(b, &w.lan)
	}
	return w
}
func transferBytes(value interface{}) ([]byte, error) {
	if data, ok := value.([]byte); ok {
		return data, nil
	}
	if data, ok := value.(string); ok {
		return base64.StdEncoding.DecodeString(data)
	}
	return nil, fmt.Errorf("invalid_transfer_data")
}
func (w *transferWire) close() {
	if w.conn != nil {
		w.conn.Close()
		w.conn = nil
	}
}
func (w *transferWire) connect(ctx context.Context) error {
	conn, err := dialTerminal(ctx, terminalSpec{Config: *w.r.cfg, ID: w.tid, LAN: w.lan, Channel: "transfer"})
	if err != nil {
		return err
	}
	w.conn = conn
	conn.SetReadLimit(1024*1024 + 8)
	conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	stop := context.AfterFunc(ctx, func() { conn.Close() })
	defer stop()
	if err = conn.WriteJSON(map[string]string{"key": w.r.cfg.Key, "installation_id": w.r.cfg.InstallationID}); err != nil {
		return err
	}
	var ready struct {
		Type    string
		Version int
		Route   string
		Error   string
	}
	if err = conn.ReadJSON(&ready); err != nil {
		return err
	}
	if ready.Error != "" {
		return &residentHTTPError{status: 403, body: ready.Error}
	}
	if ready.Type != "ready" || ready.Version != 1 {
		return fmt.Errorf("invalid_transfer_handshake")
	}
	w.route = ready.Route
	return nil
}
func (w *transferWire) call(ctx context.Context, body map[string]interface{}) (map[string]interface{}, error) {
	if !w.binary {
		if body["action"] == "read" {
			if n, ok := body["chunk_size"].(int); ok && n > 512*1024 {
				body["chunk_size"] = 512 * 1024
			}
		}
		if data, ok := body["data"].([]byte); ok {
			body["data"] = base64.StdEncoding.EncodeToString(data)
		}
		return w.r.transferCall(ctx, w.tid, body)
	}
	for attempt := 0; ; attempt++ {
		var out map[string]interface{}
		var err error
		if w.conn == nil {
			err = w.connect(ctx)
			if err != nil && ctx.Err() == nil {
				var denied *residentHTTPError
				if !errors.As(err, &denied) {
					w.close()
					w.binary = false
					w.route = "https-fallback"
					return w.call(ctx, body)
				}
			}
		}
		if err == nil {
			out, err = w.exchange(ctx, body)
		}
		if err == nil {
			out["transport"] = "binary-v1"
			out["route"] = w.route
			return out, nil
		}
		w.close()
		if ctx.Err() != nil || attempt >= 4 || !transferTransient(err) {
			return nil, err
		}
		// Replaying only idempotent batch/meta/read operations. ACK loss is safe.
		w.lan = terminalLAN{} // failed direct connection falls back to the authenticated hub
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(time.Duration(1<<attempt) * 200 * time.Millisecond):
		}
	}
}
func (w *transferWire) exchange(ctx context.Context, body map[string]interface{}) (map[string]interface{}, error) {
	conn := w.conn
	stop := context.AfterFunc(ctx, func() { conn.Close() })
	defer stop()
	conn.SetWriteDeadline(time.Now().Add(45 * time.Second))
	conn.SetReadDeadline(time.Now().Add(45 * time.Second))
	if body["action"] == "write" {
		data, err := transferBytes(body["data"])
		if err != nil {
			return nil, err
		}
		offset := body["offset"].(int64)
		batch := make([]byte, 8+len(data))
		binary.BigEndian.PutUint64(batch, uint64(offset))
		copy(batch[8:], data)
		if err = conn.WriteMessage(websocket.BinaryMessage, batch); err != nil {
			return nil, err
		}
	} else if err := conn.WriteJSON(body); err != nil {
		return nil, err
	}
	kind, data, err := conn.ReadMessage()
	if err != nil {
		return nil, err
	}
	if kind == websocket.BinaryMessage {
		if body["action"] != "read" || len(data) < 8 || binary.BigEndian.Uint64(data[:8]) != uint64(body["offset"].(int64)) {
			return nil, fmt.Errorf("invalid_transfer_offset")
		}
		return map[string]interface{}{"data": data[8:]}, nil
	}
	var out map[string]interface{}
	if err = json.Unmarshal(data, &out); err != nil {
		return nil, err
	}
	if code, ok := out["error"].(string); ok {
		return nil, &residentHTTPError{status: 409, body: code}
	}
	return out, nil
}
