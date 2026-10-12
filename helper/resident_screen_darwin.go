//go:build darwin

package main

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func materializeScreen(root string) (string, error) {
	path := filepath.Join(root, "IndieBiz Screen.app", "Contents", "MacOS", "IndieBiz Screen")
	if e := os.MkdirAll(filepath.Dir(path), 0700); e != nil {
		return "", e
	}
	old, _ := os.ReadFile(path)
	if sha256.Sum256(old) != sha256.Sum256(screenNative) {
		if e := os.WriteFile(path+".new", screenNative, 0700); e != nil {
			return "", e
		}
		if e := os.Rename(path+".new", path); e != nil {
			return "", e
		}
	}
	plist := `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>com.indiebiz.screen</string><key>CFBundleName</key><string>IndieBiz Screen</string><key>CFBundleExecutable</key><string>IndieBiz Screen</string><key>CFBundlePackageType</key><string>APPL</string><key>LSUIElement</key><true/><key>NSHighResolutionCapable</key><true/></dict></plist>`
	if e := os.WriteFile(filepath.Join(filepath.Dir(filepath.Dir(path)), "Info.plist"), []byte(plist), 0600); e != nil {
		return "", e
	}
	return path, nil
}
func screenWorkerCommand(ctx context.Context, root string) (*exec.Cmd, error) {
	path, e := materializeScreen(root)
	if e != nil {
		return nil, e
	}
	return exec.CommandContext(ctx, path), nil
}
func prepareScreen(root string) error {
	path, e := materializeScreen(root)
	if e != nil {
		return e
	}
	if e = exec.Command(path, "--permissions").Run(); e != nil {
		return fmt.Errorf("화면 기록·손쉬운 사용 권한을 허용하세요: %w", e)
	}
	return nil
}
func nativeScreenWorkerMain() int { return 1 }
