//go:build windows

package main

import "syscall"

// 윈도우 콘솔을 UTF-8(65001) 로 전환 — 한국어 윈도우 기본 콘솔은 CP949 라
// 헬퍼의 한글 안내문이 전부 깨져 보인다. 표준 라이브러리 syscall 만 사용.
func enableUTF8Console() {
	k := syscall.NewLazyDLL("kernel32.dll")
	k.NewProc("SetConsoleOutputCP").Call(65001)
	k.NewProc("SetConsoleCP").Call(65001)
}
