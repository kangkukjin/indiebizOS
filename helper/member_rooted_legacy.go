//go:build !go1.25 || legacy

package main

// The standalone legacy helper remains supported; desktop installation requires Go 1.25+.
func (m *MemberRuntime) desktopFileOp(c Command) (map[string]interface{}, bool) {
	return errResult("unsupported", "회원 데스크톱 파일 작업에는 최신 설치 앱이 필요합니다"), true
}
