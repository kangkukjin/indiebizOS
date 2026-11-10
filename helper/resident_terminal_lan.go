package main

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"fmt"
	"net"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type terminalLAN struct {
	URLs          []string `json:"urls"`
	PreferredURLs []string `json:"preferred_urls"`
	SHA256        string   `json:"sha256"`
}

func terminalURL(base, id string) (string, error) { return streamURL(base, id, "terminal") }

func streamURL(base, id, channel string) (string, error) {
	if channel == "" {
		channel = "terminal"
	}
	if channel != "process" && channel != "terminal" && channel != "screen" && channel != "media" && channel != "transfer" {
		return "", fmt.Errorf("invalid stream channel")
	}
	u, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	if u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost")) {
		return "", fmt.Errorf("HTTPS required")
	}
	u.Scheme = strings.Replace(u.Scheme, "http", "ws", 1)
	u.Path = strings.TrimRight(u.Path, "/") + "/limb/resident/" + channel + "/" + id
	return u.String(), nil
}

func dialTerminal(ctx context.Context, spec terminalSpec) (*websocket.Conn, error) {
	if conn := dialTerminalLAN(ctx, spec); conn != nil {
		return conn, nil
	}
	address, err := streamURL(spec.Config.Base, spec.ID, spec.Channel)
	if err != nil {
		return nil, err
	}
	dialer := websocket.Dialer{HandshakeTimeout: 10 * time.Second}
	conn, response, err := dialer.DialContext(ctx, address, nil)
	if response != nil && response.Body != nil {
		response.Body.Close()
	}
	return conn, err
}

func dialTerminalLAN(ctx context.Context, spec terminalSpec) *websocket.Conn {
	pin, err := hex.DecodeString(spec.LAN.SHA256)
	if err != nil || len(pin) != sha256.Size || len(spec.LAN.URLs) > 8 {
		return nil
	}
	// The fingerprint arrives over the authenticated hub job. Verify it before
	// sending any installation credential. Never trust LAN discovery or a CA bypass.
	config := &tls.Config{MinVersion: tls.VersionTLS12, InsecureSkipVerify: true,
		VerifyPeerCertificate: func(raw [][]byte, _ [][]*x509.Certificate) error {
			if len(raw) == 0 {
				return fmt.Errorf("missing LAN certificate")
			}
			digest := sha256.Sum256(raw[0])
			if subtle.ConstantTimeCompare(digest[:], pin) != 1 {
				return fmt.Errorf("LAN certificate mismatch")
			}
			return nil
		}}
	preferred := map[string]bool{}
	for _, base := range spec.LAN.PreferredURLs {
		preferred[base] = true
	}
	groups := [2][]string{}
	seen := map[string]bool{}
	for _, base := range spec.LAN.URLs {
		address := terminalLANURL(base, spec.ID, spec.Channel)
		if address == "" || seen[address] {
			continue
		}
		seen[address] = true
		group := 1
		if preferred[base] {
			group = 0
		}
		groups[group] = append(groups[group], address)
	}
	// Give the preferred hardware a bounded chance before racing ordinary LAN.
	// A single cold TLS/ARP attempt must not pin a whole transfer to the relay.
	for _, addresses := range groups {
		if len(addresses) == 0 {
			continue
		}
		for attempt := 0; attempt < 2; attempt++ {
			if conn := dialLANGroup(ctx, addresses, config); conn != nil {
				return conn
			}
			if ctx.Err() != nil {
				return nil
			}
			if attempt == 0 {
				select {
				case <-ctx.Done():
					return nil
				case <-time.After(200 * time.Millisecond):
				}
			}
		}
	}
	return nil
}

func terminalLANURL(base, id, channel string) string {
	u, err := url.Parse(base)
	if err != nil {
		return ""
	}
	ip := net.ParseIP(u.Hostname())
	if u.Scheme != "https" || ip == nil || ip.To4() == nil || !(ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast()) || u.User != nil || u.RawQuery != "" || u.Path != "" || u.Fragment != "" {
		return ""
	}
	address, err := streamURL(base, id, channel)
	if err != nil {
		return ""
	}
	return address
}

func dialLANGroup(ctx context.Context, addresses []string, config *tls.Config) *websocket.Conn {
	probe, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	var workers sync.WaitGroup
	var mu sync.Mutex
	var winner *websocket.Conn
	for _, address := range addresses {
		workers.Add(1)
		go func(address string) {
			defer workers.Done()
			dialer := websocket.Dialer{TLSClientConfig: config, HandshakeTimeout: 3 * time.Second}
			conn, response, e := dialer.DialContext(probe, address, nil)
			if response != nil && response.Body != nil {
				response.Body.Close()
			}
			if e != nil {
				return
			}
			mu.Lock()
			defer mu.Unlock()
			if winner == nil {
				winner = conn
				cancel()
			} else {
				conn.Close()
			}
		}(address)
	}
	workers.Wait()
	return winner
}
