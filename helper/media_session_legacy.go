//go:build legacy

package main

import "context"

// Legacy build (Go 1.22, macOS 10.15 Intel): pion/webrtc v4 needs Go 1.24, so
// the media engine is absent. The envelope is still parsed and refused with the
// contract's codes; the capability block says so.

const mediaEngineBuilt = false

func mediaEngineVersion() string { return "" }

func (r *residentRuntime) mediaSession(_ context.Context, j Job) map[string]interface{} {
	if _, code, err := parseMediaEnvelope(j.Code); err != nil {
		return errResult(code, err.Error())
	}
	nla := map[string]interface{}{"code": "engine_unsupported", "message": "이 헬퍼 빌드(legacy)에는 미디어 엔진이 없습니다"}
	res := errResult("needs_local_action", nla["message"].(string))
	res["needs_local_action"] = nla
	return res
}
