//go:build !windows

package main

// launchd/systemd already supervise these processes.
func startResidentManaged(cfg *Config) error { return startResident(cfg) }
