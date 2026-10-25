package main

import (
	"errors"
	"fmt"
	"os/exec"
	"os/user"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

const residentRunKey = `Software\Microsoft\Windows\CurrentVersion\Run`

// New installations use the current user's Run key. Creating an ONLOGON task
// can require elevation even though its action runs as the logged-in user.
// Existing scheduled-task installations retain their restart/update contract.
func residentWindowsAutostart(cfg *Config, exe string, remove bool) error {
	name := residentServiceName(cfg)
	current, err := residentReadRun(registry.CURRENT_USER, residentRunKey, name)
	if err != nil {
		return err
	}
	if current != "" {
		return residentWriteRun(registry.CURRENT_USER, residentRunKey, name, exe, remove)
	}
	query := exec.Command("schtasks", "/Query", "/TN", name, "/XML")
	configureResidentDetached(query)
	if existing, queryErr := query.Output(); queryErr == nil {
		if !remove {
			currentUser, userErr := user.Current()
			if userErr == nil && residentLoginTaskMatches(residentWindowsOutput(existing), exe, currentUser.Uid, currentUser.Username) {
				return nil
			}
		}
		args := []string{"/Create", "/F", "/IT", "/SC", "ONLOGON", "/TN", name, "/TR", `"` + exe + `"`}
		if remove {
			args = []string{"/Delete", "/F", "/TN", name}
		}
		cmd := exec.Command("schtasks", args...)
		configureResidentDetached(cmd)
		out, err := cmd.CombinedOutput()
		if err != nil {
			return fmt.Errorf("schtasks: %s: %w", residentWindowsOutput(out), err)
		}
		return nil
	}
	// Also makes cleanup of a failed first installation (no task) idempotent.
	return residentWriteRun(registry.CURRENT_USER, residentRunKey, name, exe, remove)
}

func residentReadRun(hive registry.Key, path, name string) (string, error) {
	key, err := registry.OpenKey(hive, path, registry.QUERY_VALUE)
	if errors.Is(err, registry.ErrNotExist) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	defer key.Close()
	value, _, err := key.GetStringValue(name)
	if errors.Is(err, registry.ErrNotExist) {
		return "", nil
	}
	return value, err
}

func residentWriteRun(hive registry.Key, path, name, exe string, remove bool) error {
	if remove {
		key, err := registry.OpenKey(hive, path, registry.SET_VALUE)
		if errors.Is(err, registry.ErrNotExist) {
			return nil
		}
		if err != nil {
			return err
		}
		defer key.Close()
		err = key.DeleteValue(name)
		if errors.Is(err, registry.ErrNotExist) {
			return nil
		}
		return err
	}
	value := `"` + exe + `"`
	if exe == "" || strings.ContainsAny(exe, "\"\r\n\x00") || len(utf16.Encode([]rune(value))) > 260 {
		return fmt.Errorf("자동 시작 실행파일 경로가 잘못되었거나 너무 깁니다: %s", exe)
	}
	key, _, err := registry.CreateKey(hive, path, registry.SET_VALUE)
	if err != nil {
		return err
	}
	defer key.Close()
	return key.SetStringValue(name, value)
}

func residentWindowsCanRestart(cfg *Config) bool {
	value, err := residentReadRun(registry.CURRENT_USER, residentRunKey, residentServiceName(cfg))
	if err != nil {
		return false
	}
	if value != "" {
		return value == `"`+residentExecutable(cfg.DataDir)+`"`
	}
	query := exec.Command("schtasks", "/Query", "/TN", residentServiceName(cfg))
	configureResidentDetached(query)
	return query.Run() == nil
}

func residentWindowsRestart(cfg *Config) error {
	value, err := residentReadRun(registry.CURRENT_USER, residentRunKey, residentServiceName(cfg))
	if err != nil {
		return err
	}
	var cmd *exec.Cmd
	if value != "" {
		// Never execute a command read from the registry: only our installed file.
		if value != `"`+residentExecutable(cfg.DataDir)+`"` {
			return fmt.Errorf("자동 시작 경로가 설치된 헬퍼와 다릅니다")
		}
		cmd = exec.Command(residentExecutable(cfg.DataDir))
		cmd.Dir = cfg.DataDir
		configureResidentDetached(cmd)
		return cmd.Start()
	}
	cmd = exec.Command("schtasks", "/Run", "/TN", residentServiceName(cfg))
	configureResidentDetached(cmd)
	return cmd.Run()
}

func residentWindowsOutput(raw []byte) string {
	// schtasks /XML may emit a UTF-16LE document even with redirected output.
	start := 0
	if len(raw) >= 2 && raw[0] == 0xff && raw[1] == 0xfe {
		start = 2
	}
	if start == 2 || (len(raw) >= 4 && raw[0] == '<' && raw[1] == 0 && raw[3] == 0) {
		units := make([]uint16, 0, (len(raw)-start)/2)
		for i := start; i+1 < len(raw); i += 2 {
			units = append(units, uint16(raw[i])|uint16(raw[i+1])<<8)
		}
		return strings.TrimSpace(string(utf16.Decode(units)))
	}
	if utf8.Valid(raw) {
		return strings.TrimSpace(string(raw))
	}
	// Console utilities emit the OEM code page when no UTF-8 console is attached
	// (the resident installer is a GUI executable). CP_OEMCP=1 includes Korean 949.
	out := make([]uint16, len(raw))
	n, err := windows.MultiByteToWideChar(1, 0, &raw[0], int32(len(raw)), &out[0], int32(len(out)))
	if err != nil {
		return fmt.Sprintf("출력 디코딩 실패 [%x]", raw)
	}
	return strings.TrimSpace(string(utf16.Decode(out[:n])))
}
