//go:build linux

package main

import (
	"context"
	_ "embed"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

//go:embed desktop_native/linux.py
var screenLinux []byte

func linuxScreenScript(root string) (string, error) {
	path := filepath.Join(root, "screen-worker.py")
	return path, os.WriteFile(path, screenLinux, 0600)
}
func screenWorkerCommand(ctx context.Context, root string) (*exec.Cmd, error) {
	path, e := linuxScreenScript(root)
	if e != nil {
		return nil, e
	}
	return exec.CommandContext(ctx, "python3", "-u", path, root), nil
}
func prepareScreen(root string) error {
	check := exec.Command("python3", "-c", "import gi,dbus; gi.require_version('Gst','1.0'); gi.require_version('Gdk','3.0'); from gi.repository import Gst,Gdk; Gst.init(None); assert Gst.ElementFactory.find('jpegenc'); assert Gst.ElementFactory.find('pipewiresrc') if __import__('os').environ.get('WAYLAND_DISPLAY') else Gst.ElementFactory.find('ximagesrc')")
	if check.Run() != nil || (os.Getenv("WAYLAND_DISPLAY") == "" && !hasBin("xdotool")) {
		var install []string
		switch {
		case hasBin("apt-get"):
			install = []string{"apt-get", "install", "-y", "python3-gi", "python3-dbus", "gir1.2-gtk-3.0", "gir1.2-gstreamer-1.0", "gstreamer1.0-plugins-good", "gstreamer1.0-pipewire", "xdotool"}
		case hasBin("dnf"):
			install = []string{"dnf", "install", "-y", "python3-gobject", "python3-dbus", "gtk3", "gstreamer1-plugins-good", "pipewire-gstreamer", "xdotool"}
		case hasBin("pacman"):
			install = []string{"pacman", "-S", "--needed", "--noconfirm", "python-gobject", "python-dbus", "gtk3", "gst-plugins-good", "gst-plugin-pipewire", "xdotool"}
		default:
			return fmt.Errorf("Linux 화면 공유에 Python GI·GStreamer·PipeWire 또는 X11 도구가 필요합니다.")
		}
		if !hasBin("pkexec") {
			return fmt.Errorf("관리자 인증을 위한 pkexec가 필요합니다.")
		}
		if e := exec.Command("pkexec", install...).Run(); e != nil {
			return fmt.Errorf("화면 공유 구성요소 설치가 완료되지 않았습니다: %w", e)
		}
	}
	path, e := linuxScreenScript(root)
	if e != nil {
		return e
	}
	return exec.Command("python3", path, root, "--permissions").Run()
}
func nativeScreenWorkerMain() int { return 1 }
