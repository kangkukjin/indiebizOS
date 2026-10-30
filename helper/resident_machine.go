package main

import (
	"bytes"
	"fmt"
	"os"
)

// Compatibility marker, not an authenticity check: the normal digest/transport
// validation still applies. Never replace a service worker with a legacy helper
// that interprets its service arguments as an ordinary interactive launch.
const residentMachineProtocol = "IndieBizResidentMachineWorkerProtocol/v1/20261030"

func residentMachineCheckUpdate(path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if !bytes.Contains(raw, []byte(residentMachineProtocol)) {
		return fmt.Errorf("candidate does not support the managed service worker protocol")
	}
	return nil
}

// Session 0 has no user's desktop/audio. Do not advertise or attempt a window
// that nobody can see, and do not silently re-route a system install into HKCU.
func residentMachineOperation(op string) bool {
	switch op {
	case "shell", "python", "read", "write", "list", "info", "transfer", "update", "wake":
		return true
	}
	return false
}
