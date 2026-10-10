package main

import (
	"fmt"
	"github.com/gorilla/websocket"
	"net/url"
	"time"
)

type residentTransport struct {
	base  string
	conn  *websocket.Conn
	retry time.Time
}

func (t *residentTransport) close() {
	if t.conn != nil {
		_ = t.conn.Close()
		t.conn = nil
	}
}
func (t *residentTransport) sync(body map[string]interface{}) (map[string]interface{}, error) {
	if t.conn == nil && time.Now().After(t.retry) {
		u, e := url.Parse(t.base)
		if e != nil {
			return nil, e
		}
		if u.Scheme != "https" && u.Hostname() != "127.0.0.1" && u.Hostname() != "localhost" {
			return nil, fmt.Errorf("HTTPS required")
		}
		if u.Scheme == "https" {
			u.Scheme = "wss"
		} else {
			u.Scheme = "ws"
		}
		u.Path += "/limb/resident/ws"
		dialer := websocket.Dialer{HandshakeTimeout: 5 * time.Second}
		conn, response, e := dialer.Dial(u.String(), nil)
		if response != nil && response.Body != nil {
			response.Body.Close()
		}
		if e == nil {
			t.conn = conn
			conn.SetReadLimit(16 * 1024 * 1024)
		} else {
			t.retry = time.Now().Add(time.Minute)
		}
	}
	if t.conn != nil {
		_ = t.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
		e := t.conn.WriteJSON(body)
		var result map[string]interface{}
		if e == nil {
			_ = t.conn.SetReadDeadline(time.Now().Add(45 * time.Second))
			e = t.conn.ReadJSON(&result)
		}
		if e == nil {
			return result, nil
		}
		t.close()
		t.retry = time.Now().Add(time.Minute)
	}
	return residentPost(t.base+"/limb/resident/sync", body)
}
