//go:build windows

package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"image"
	"image/jpeg"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

var screenUser32 = syscall.NewLazyDLL("user32.dll")
var screenGDI = syscall.NewLazyDLL("gdi32.dll")

func ucall(name string, args ...uintptr) uintptr {
	v, _, _ := screenUser32.NewProc(name).Call(args...)
	return v
}
func gcall(name string, args ...uintptr) uintptr {
	v, _, _ := screenGDI.NewProc(name).Call(args...)
	return v
}
func screenWorkerCommand(ctx context.Context, root string) (*exec.Cmd, error) {
	path, e := os.Executable()
	if e != nil {
		return nil, e
	}
	return exec.CommandContext(ctx, path, "--screen-worker"), nil
}
func prepareScreen(root string) error { return nil }
func screenMetric(n uintptr) int      { return int(int32(ucall("GetSystemMetrics", n))) }

type dibHeader struct {
	Size                   uint32
	Width, Height          int32
	Planes, BitCount       uint16
	Compression, SizeImage uint32
	XPels, YPels           int32
	ClrUsed, ClrImportant  uint32
}

func windowsFrame() ([]byte, error) {
	w, h := screenMetric(78), screenMetric(79)
	if w < 1 || h < 1 || w > 16384 || h > 16384 {
		return nil, fmt.Errorf("no interactive desktop")
	}
	dc := ucall("GetDC", 0)
	if dc == 0 {
		return nil, fmt.Errorf("desktop unavailable")
	}
	defer ucall("ReleaseDC", 0, dc)
	mem := gcall("CreateCompatibleDC", dc)
	defer gcall("DeleteDC", mem)
	hdr := dibHeader{Size: 40, Width: int32(w), Height: -int32(h), Planes: 1, BitCount: 32}
	var bits unsafe.Pointer
	bmp := gcall("CreateDIBSection", dc, uintptr(unsafe.Pointer(&hdr)), 0, uintptr(unsafe.Pointer(&bits)), 0, 0)
	if bmp == 0 || bits == nil {
		return nil, fmt.Errorf("capture unavailable")
	}
	defer gcall("DeleteObject", bmp)
	old := gcall("SelectObject", mem, bmp)
	defer gcall("SelectObject", mem, old)
	if gcall("BitBlt", mem, 0, 0, uintptr(w), uintptr(h), dc, uintptr(screenMetric(76)), uintptr(screenMetric(77)), 0x40CC0020) == 0 {
		return nil, fmt.Errorf("desktop access denied")
	}
	// Cursor coordinates use the same physical desktop space as the bitmap.
	type cursorInfo struct {
		Size, Flags uint32
		Cursor      uintptr
		X, Y        int32
	}
	ci := cursorInfo{Size: uint32(unsafe.Sizeof(cursorInfo{}))}
	if ucall("GetCursorInfo", uintptr(unsafe.Pointer(&ci))) != 0 && ci.Flags == 1 {
		ucall("DrawIconEx", mem, uintptr(int(ci.X)-screenMetric(76)), uintptr(int(ci.Y)-screenMetric(77)), ci.Cursor, 0, 0, 0, 0, 3)
	}
	src := unsafe.Slice((*byte)(bits), w*h*4)
	tw := w
	if tw > 1600 {
		tw = 1600
	}
	th := h * tw / w
	if th < 1 {
		th = 1
	}
	dst := image.NewRGBA(image.Rect(0, 0, tw, th))
	for y := 0; y < th; y++ {
		for x := 0; x < tw; x++ {
			a := ((y*h/th)*w + x*w/tw) * 4
			b := y*dst.Stride + x*4
			dst.Pix[b] = src[a+2]
			dst.Pix[b+1] = src[a+1]
			dst.Pix[b+2] = src[a]
			dst.Pix[b+3] = 255
		}
	}
	var out bytes.Buffer
	err := jpeg.Encode(&out, dst, &jpeg.Options{Quality: 65})
	return out.Bytes(), err
}
func screenVK(code string) byte {
	if len(code) == 4 && code[:3] == "Key" {
		return code[3]
	}
	if len(code) == 6 && code[:5] == "Digit" {
		return code[5]
	}
	if len(code) > 1 && code[0] == 'F' {
		if n, e := strconv.Atoi(code[1:]); e == nil && n >= 1 && n <= 24 {
			return byte(0x6f + n)
		}
	}
	if len(code) == 7 && code[:6] == "Numpad" && code[6] >= '0' && code[6] <= '9' {
		return 0x60 + code[6] - '0'
	}
	return map[string]byte{"Backspace": 8, "Tab": 9, "Enter": 13, "NumpadEnter": 13, "ShiftLeft": 0xa0, "ShiftRight": 0xa1, "ControlLeft": 0xa2, "ControlRight": 0xa3, "AltLeft": 0xa4, "AltRight": 0xa5, "CapsLock": 20, "Escape": 27, "Space": 32, "PageUp": 33, "PageDown": 34, "End": 35, "Home": 36, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40, "Insert": 45, "Delete": 46, "MetaLeft": 91, "MetaRight": 92, "ContextMenu": 93, "NumLock": 144, "ScrollLock": 145, "Semicolon": 186, "Equal": 187, "Comma": 188, "Minus": 189, "Period": 190, "Slash": 191, "Backquote": 192, "BracketLeft": 219, "Backslash": 220, "BracketRight": 221, "Quote": 222, "NumpadMultiply": 106, "NumpadAdd": 107, "NumpadSubtract": 109, "NumpadDecimal": 110, "NumpadDivide": 111}[code]
}
func nativeScreenWorkerMain() int {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	if p := screenUser32.NewProc("SetProcessDpiAwarenessContext"); p.Find() == nil {
		p.Call(^uintptr(3))
	} else {
		ucall("SetProcessDPIAware")
	}
	held := map[byte]bool{}
	buttons := 0
	reset := func() {
		for k := range held {
			ucall("keybd_event", uintptr(k), 0, 2, 0)
			delete(held, k)
		}
		for i, up := range []uintptr{4, 16, 64} {
			if buttons&(1<<i) != 0 {
				ucall("mouse_event", up, 0, 0, 0, 0)
			}
		}
		buttons = 0
	}
	defer reset()
	scan := bufio.NewScanner(os.Stdin)
	scan.Buffer(make([]byte, 65536), 65536)
	out := json.NewEncoder(os.Stdout)
	for scan.Scan() {
		var m screenMessage
		if json.Unmarshal(scan.Bytes(), &m) != nil {
			out.Encode(map[string]string{"error": "invalid input"})
			continue
		}
		result := map[string]interface{}{}
		switch m.Type {
		case "frame":
			b, e := windowsFrame()
			if e != nil {
				result["error"] = "화면 공유는 로그인한 Windows 데스크톱에서 사용할 수 있습니다."
			} else {
				result["image"] = base64.StdEncoding.EncodeToString(b)
			}
		case "reset":
			reset()
		case "pointer":
			x := screenMetric(76) + int(m.X*float64(screenMetric(78)-1))
			y := screenMetric(77) + int(m.Y*float64(screenMetric(79)-1))
			ucall("SetCursorPos", uintptr(x), uintptr(y))
			for i, pair := range [][2]uintptr{{2, 4}, {8, 16}, {32, 64}} {
				if (buttons^m.Buttons)&(1<<i) != 0 {
					f := pair[1]
					if m.Buttons&(1<<i) != 0 {
						f = pair[0]
					}
					ucall("mouse_event", f, 0, 0, 0, 0)
				}
			}
			buttons = m.Buttons
		case "wheel":
			if m.DY != 0 {
				ucall("mouse_event", 0x800, 0, 0, uintptr(int32(-m.DY)), 0)
			}
			if m.DX != 0 {
				ucall("mouse_event", 0x1000, 0, 0, uintptr(int32(m.DX)), 0)
			}
		case "key":
			if vk := screenVK(m.Code); vk != 0 {
				var f uintptr
				if !m.Down {
					f = 2
					delete(held, vk)
				} else {
					held[vk] = true
				}
				if vk >= 33 && vk <= 46 || vk == 91 || vk == 92 || vk == 0xa3 || vk == 0xa5 {
					f |= 1
				}
				ucall("keybd_event", uintptr(vk), 0, f, 0)
			}
		case "text":
			for _, v := range utf16.Encode([]rune(m.Text)) {
				for _, flags := range []uint32{4, 6} {
					var in [40]byte
					binary.LittleEndian.PutUint32(in[0:], 1)
					binary.LittleEndian.PutUint16(in[10:], v)
					binary.LittleEndian.PutUint32(in[12:], flags)
					ucall("SendInput", 1, uintptr(unsafe.Pointer(&in[0])), 40)
				}
			}
		default:
			result["error"] = "unsupported input"
		}
		if out.Encode(result) != nil {
			return 1
		}
	}
	return 0
}
