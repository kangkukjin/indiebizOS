package main

import (
	"context"
	"time"
)

// mediaSessionCapabilities is the sync capability block (contract §2
// capabilities): computed from binaries present and device enumeration,
// cached 10 minutes by mediaProbe.
func (r *residentRuntime) mediaSessionCapabilities() map[string]interface{} {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	caps := mediaProbe(ctx, "", r.cfg.DataDir)
	rep := caps.report(mediaEngineVersion(), true)
	if !mediaEngineBuilt {
		rep["camera"], rep["microphone"], rep["speaker"], rep["display"], rep["playback"] = false, false, false, false, false
	}
	return rep
}
