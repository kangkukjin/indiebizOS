package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestTransferRetriesSameOffsetAfterTruncatedReply(t *testing.T) {
	r := residentTestRuntime(t)
	data := make([]byte, 400000)
	for i := range data {
		data[i] = byte(i)
	}
	hash := sha256.Sum256(data)
	attempts := map[int]int{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]interface{}
		_ = json.NewDecoder(req.Body).Decode(&body)
		if body["action"] != "read" {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{"direction": "to_pc", "state": "committed", "size": len(data), "sha256": hex.EncodeToString(hash[:])})
			return
		}
		off := int(body["offset"].(float64))
		attempts[off]++
		if attempts[off] == 1 {
			w.Header().Set("Content-Length", "100")
			_, _ = w.Write([]byte(`{"data":`))
			return
		}
		size := int(body["chunk_size"].(float64))
		if size != 128*1024 {
			t.Errorf("chunk size %d", size)
		}
		end := off + size
		if end > len(data) {
			end = len(data)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"data": base64.StdEncoding.EncodeToString(data[off:end]), "offset": end})
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	path := filepath.Join(r.cfg.DataDir, "download")
	got, err := r.transferFile(context.Background(), Command{Path: path}, residentID())
	if err != nil || got["state"] != "committed" {
		t.Fatal(got, err)
	}
	saved, _ := os.ReadFile(path)
	if string(saved) != string(data) || len(attempts) != 4 {
		t.Fatal("data or progress lost")
	}
	for _, n := range attempts {
		if n != 2 {
			t.Fatal(attempts)
		}
	}
}

func TestTransferUploadRetriesLostAcknowledgement(t *testing.T) {
	r := residentTestRuntime(t)
	data := []byte("exact bytes")
	path := filepath.Join(r.cfg.DataDir, "source")
	_ = os.WriteFile(path, data, 0600)
	writes := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]interface{}
		_ = json.NewDecoder(req.Body).Decode(&body)
		var out interface{} = map[string]interface{}{"direction": "from_pc", "offset": 0}
		switch body["action"] {
		case "write":
			writes++
			if body["offset"].(float64) != 0 || body["data"] != base64.StdEncoding.EncodeToString(data) {
				t.Error("changed retry")
			}
			if writes == 1 {
				w.WriteHeader(503)
				return
			}
			out = map[string]interface{}{"offset": len(data)}
		case "commit":
			out = map[string]interface{}{"state": "committed"}
		}
		_ = json.NewEncoder(w).Encode(out)
	}))
	defer server.Close()
	r.cfg.Base = server.URL
	got, err := r.transferFile(context.Background(), Command{Path: path}, residentID())
	if err != nil || got["state"] != "committed" || writes != 2 {
		t.Fatal(got, err, writes)
	}
}

func TestTransferStopsOnPermanentErrorAndCancelsInFlight(t *testing.T) {
	for _, code := range []int{400, 403, 409} {
		t.Run(fmt.Sprint(code), func(t *testing.T) {
			r := residentTestRuntime(t)
			calls := 0
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) { calls++; w.WriteHeader(code) }))
			defer s.Close()
			r.cfg.Base = s.URL
			_, err := r.transferCall(context.Background(), residentID(), map[string]interface{}{})
			if err == nil || calls != 1 {
				t.Fatal(err, calls)
			}
		})
	}
	r := residentTestRuntime(t)
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]interface{}
		_ = json.NewDecoder(req.Body).Decode(&body)
		<-req.Context().Done()
	}))
	defer s.Close()
	r.cfg.Base = s.URL
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	before := time.Now()
	_, err := r.transferCall(ctx, residentID(), map[string]interface{}{})
	if err == nil || ctx.Err() == nil || time.Since(before) > time.Second {
		t.Fatal(err, time.Since(before))
	}
}

func TestPackageManagerCandidatesArePlatformScoped(t *testing.T) {
	for _, name := range packageManagerCandidates("darwin") {
		if name == "apt" {
			t.Fatal("macOS Java apt misidentified as a package manager")
		}
	}
}

func TestEmptyDirectoryIsAnEmptyListOnTheWire(t *testing.T) {
	result := doList(Command{Path: t.TempDir()})
	data, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]interface{}
	_ = json.Unmarshal(data, &decoded)
	files, ok := decoded["files"].([]interface{})
	if !ok || len(files) != 0 {
		t.Fatal(string(data))
	}
}
