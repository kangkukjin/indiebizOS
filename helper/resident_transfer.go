package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"time"
)

// Only idempotent transfer protocol messages are retried, never shell effects.
func (r *residentRuntime) transferCall(ctx context.Context, tid string, body map[string]interface{}) (map[string]interface{}, error) {
	body["key"] = r.cfg.Key
	body["installation_id"] = r.cfg.InstallationID
	for attempt := 0; ; attempt++ {
		out, err := residentPostContext(ctx, r.cfg.Base+"/limb/resident/transfers/"+tid, body)
		if err == nil || ctx.Err() != nil || attempt >= 4 || !transferTransient(err) {
			return out, err
		}
		timer := time.NewTimer(time.Duration(1<<attempt) * 200 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return nil, ctx.Err()
		case <-timer.C:
		}
	}
}
func transferTransient(err error) bool {
	var httpErr *residentHTTPError
	if errors.As(err, &httpErr) {
		return httpErr.status == 408 || httpErr.status == 429 || httpErr.status >= 500
	}
	var netErr net.Error
	return errors.As(err, &netErr) || errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF)
}
func fileDigest(path string) (string, int64, error) {
	f, e := os.Open(path)
	if e != nil {
		return "", 0, e
	}
	defer f.Close()
	s, e := f.Stat()
	if e != nil || !s.Mode().IsRegular() {
		return "", 0, fmt.Errorf("regular_file_required; archive folders before transfer")
	}
	h := sha256.New()
	n, e := io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), n, e
}
func (r *residentRuntime) transfer(ctx context.Context, c Command, tid string) map[string]interface{} {
	if !residentValidID(tid) {
		return errResult("invalid_transfer_id", "")
	}
	res, e := r.transferFile(ctx, c, tid)
	if e != nil {
		failure := errResult("transfer_failed", e.Error())
		if ctx.Err() != nil {
			failure["cancelled"] = ctx.Err() == context.Canceled
			failure["timeout"] = ctx.Err() == context.DeadlineExceeded
		}
		return failure
	}
	return res
}
func (r *residentRuntime) transferFile(ctx context.Context, c Command, tid string) (map[string]interface{}, error) {
	meta, e := r.transferCall(ctx, tid, map[string]interface{}{})
	if e != nil {
		return nil, e
	}
	path := c.Path
	if path == "" {
		return nil, fmt.Errorf("path_required")
	}
	if meta["direction"] == "from_pc" {
		hash, size, e := fileDigest(path)
		if e != nil {
			return nil, e
		}
		meta, e = r.transferCall(ctx, tid, map[string]interface{}{"action": "meta", "size": size, "sha256": hash})
		if e != nil {
			return nil, e
		}
		if meta["state"] == "committed" {
			return meta, nil
		}
		offset := int64(meta["offset"].(float64))
		f, e := os.Open(path)
		if e != nil {
			return nil, e
		}
		defer f.Close()
		if _, e = f.Seek(offset, 0); e != nil {
			return nil, e
		}
		buf := make([]byte, 128*1024)
		for offset < size {
			if e = ctx.Err(); e != nil {
				return nil, e
			}
			n, e := f.Read(buf)
			if e != nil {
				return nil, e
			}
			next, e := r.transferCall(ctx, tid, map[string]interface{}{"action": "write", "offset": offset, "data": base64.StdEncoding.EncodeToString(buf[:n])})
			if e != nil {
				return nil, e
			}
			acknowledged, ok := next["offset"].(float64)
			if !ok || int64(acknowledged) != offset+int64(n) {
				return nil, fmt.Errorf("invalid_chunk_ack")
			}
			offset += int64(n)
		}
		return r.transferCall(ctx, tid, map[string]interface{}{"action": "commit"})
	}
	if meta["state"] != "committed" {
		return nil, fmt.Errorf("source_not_committed")
	}
	size := int64(meta["size"].(float64))
	hash := meta["sha256"].(string)
	// A completed retry never overwrites an unrelated destination.
	if _, e = os.Stat(path); e == nil {
		old, _, e := fileDigest(path)
		if e == nil && old == hash {
			return map[string]interface{}{"path": path, "sha256": hash, "state": "committed"}, nil
		}
		return nil, fmt.Errorf("destination_exists")
	}
	if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
		return nil, e
	}
	partial := path + ".indiebiz-" + tid + ".part"
	f, e := os.OpenFile(partial, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return nil, e
	}
	offset := st.Size()
	if offset > size {
		return nil, fmt.Errorf("partial_larger_than_source")
	}
	if _, e = f.Seek(offset, 0); e != nil {
		return nil, e
	}
	for offset < size {
		if e = ctx.Err(); e != nil {
			return nil, e
		}
		chunk, e := r.transferCall(ctx, tid, map[string]interface{}{"action": "read", "offset": offset, "chunk_size": 128 * 1024})
		if e != nil {
			return nil, e
		}
		data, e := base64.StdEncoding.DecodeString(chunk["data"].(string))
		if e != nil || len(data) == 0 {
			return nil, fmt.Errorf("invalid_chunk")
		}
		if int64(len(data))+offset > size {
			return nil, fmt.Errorf("oversized_chunk")
		}
		if _, e = f.Write(data); e != nil {
			return nil, e
		}
		if e = f.Sync(); e != nil {
			return nil, e
		}
		offset += int64(len(data))
	}
	if e = f.Close(); e != nil {
		return nil, e
	}
	got, _, e := fileDigest(partial)
	if e != nil {
		return nil, e
	}
	if got != hash {
		return nil, fmt.Errorf("hash_mismatch")
	}
	// Hard link provides a no-clobber commit; both files live on the destination filesystem.
	if e = os.Link(partial, path); e != nil {
		return nil, e
	}
	if e = os.Remove(partial); e != nil {
		return nil, e
	}
	return map[string]interface{}{"path": path, "sha256": hash, "size": size, "state": "committed"}, nil
}
