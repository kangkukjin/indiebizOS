// screen.go — 손발의 눈. 그 PC 의 화면을 캡처해 허브로 올린다.
//
// 왜 필요한가: 1단계 손발은 셸만 있었다 — 명령을 던지고 stdout/exit code 만 받으니
// AI 가 "눈 감고 타이핑"하는 셈이었다. 설치 마법사 다이얼로그도, 에러 팝업도, 창이
// 정말 떴는지도 보이지 않아 검증 없이 다음 명령으로 넘어갔다. 눈이 생기면 셸 결과를
// 시각으로 확인하고(see→verify), 나아가 GUI 를 조작할 수 있다(input.go 의 손과 짝).
//
// 얇은 바이너리 원칙: Go 표준 라이브러리엔 화면 캡처가 없고, 외부 캡처 라이브러리는
// 대개 CGo 를 끌어와 크로스컴파일(단일 실행파일·런타임 0)을 깨뜨린다. 그래서 **각 OS 에
// 원래 있는 도구로 셸아웃**해 PNG 파일을 얻고, 축소·인코딩만 stdlib(image/*)로 한다.
//   · macOS  : screencapture (OS 기본 탑재)
//   · Windows: PowerShell + .NET System.Drawing (OS 기본 탑재)
//   · Linux  : grim/scrot/import/gnome-screenshot 중 있는 것 (없을 수 있음 → 정직한 실패)
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	// 허브로 올리는 이미지의 기본 가로 상한. 원본 해상도(레티나 3024px 등)를 그대로 보내면
	// 통화가 수 MB 로 붓고 모델 입력도 어차피 축소된다. 1280 은 화면 글자가 읽히는 하한선.
	defaultMaxWidth = 1280
	// 통화 상한(base64 이전 바이트). 넘으면 품질·크기를 낮춰 다시 인코딩한다.
	maxImageBytes = 1400 * 1024
	// PNG 가 이보다 크면 JPEG 로 바꾼다 — 사진 같은 배경(월페이퍼)에선 PNG 가 폭증한다.
	pngPreferBelow = 420 * 1024
	captureTimeout = 25 * time.Second
)

// === 좌표계 기억 — "AI 가 본 그림 위의 좌표"를 그대로 받기 위한 장치 ===
//
// 정확한 클릭의 급소가 여기다. AI 는 축소된 이미지(예 1280px)를 보고 "여기를 눌러"라고
// 말하는데, 실제 입력은 그 PC 의 좌표계에서 일어난다. 그 사이엔 배율이 둘이나 낀다:
//   ① 축소 배율 : 캡처 원본(1920px) → 전송 이미지(1280px)
//   ② 픽셀↔포인트: 레티나 맥은 캡처가 픽셀(3024)인데 클릭은 논리 포인트(1512)로 받는다
// 이 환산을 AI 에게 시키면 반드시 틀린다(그리고 왜 빗나갔는지 알 수도 없다). 그래서
// 캡처할 때마다 배율을 여기 적어두고, 입력 op 가 이미지 좌표를 자동으로 옮긴다.
type shotFrame struct {
	imgW, imgH     int // 허브로 보낸 이미지 크기 = AI 가 본 좌표계
	pointW, pointH int // 그 PC 의 입력 좌표계(맥=논리 포인트, 그 외=픽셀)
	valid          bool
}

var lastShot shotFrame

// mapPoint — 이미지 좌표(AI 가 본 것) → 입력 좌표(그 PC). 캡처 이력이 없으면 그대로 쓴다.
func mapPoint(x, y int) (int, int) {
	s := lastShot
	if !s.valid || s.imgW <= 0 || s.imgH <= 0 {
		return x, y
	}
	return x * s.pointW / s.imgW, y * s.pointH / s.imgH
}

// logicalScreenSize — 입력이 쓰는 좌표계 크기. 맥은 캡처가 **픽셀**인데 클릭은 **논리
// 포인트**로 받는다(레티나면 2배 차이 → 클릭이 화면 왼쪽 위 1/4 에만 떨어진다).
//
// ★함정 기록: 처음엔 Finder 의 `bounds of window of desktop` 으로 물었는데, Finder 가
// AppleEvent 에 응답하지 않으면 -1712 로 **행이 걸린다**(실측 2분). 매 캡처가 그만큼
// 멈추므로 폐기했다. system_profiler 는 느리지만(1~3초) 행이 없고, 한 번만 재면 되므로
// 헬퍼 수명 동안 캐시한다.
var (
	logicalOnce sync.Once
	logicalW    int
	logicalH    int
)

func logicalScreenSize(capW, capH int) (int, int) {
	if runtime.GOOS != "darwin" {
		return capW, capH // 윈도우·리눅스는 캡처와 입력이 같은 픽셀 좌표계
	}
	logicalOnce.Do(func() {
		// "UI Looks like: 1512 x 982" = 논리 포인트(레티나), 없으면 "Resolution: 1920 x 1080"
		out, err := runOutTimeout(12*time.Second, "system_profiler", "SPDisplaysDataType")
		if err != nil {
			return
		}
		for _, line := range strings.Split(out, "\n") {
			t := strings.TrimSpace(line)
			for _, key := range []string{"UI Looks like:", "Resolution:"} {
				if !strings.HasPrefix(t, key) {
					continue
				}
				var w, h int
				if n, _ := fmt.Sscanf(strings.TrimSpace(strings.TrimPrefix(t, key)),
					"%d x %d", &w, &h); n == 2 && w > 0 && h > 0 {
					if key == "UI Looks like:" { // 논리 크기가 더 정확 — 찾으면 확정
						logicalW, logicalH = w, h
						return
					}
					if logicalW == 0 {
						logicalW, logicalH = w, h // Resolution 은 잠정값(뒤에 UI Looks like 나오면 덮임)
					}
				}
			}
		}
	})
	if logicalW > 0 && logicalH > 0 {
		return logicalW, logicalH
	}
	return capW, capH // 못 재면 1:1 — 비레티나에선 정확, 레티나면 아래 경고가 붙는다
}

// doScreen — {op:"screen"} 봉투 처리. 결과 통화에 base64 이미지를 싣는다.
//
// 파라미터(전부 선택): max_width(기본 1280) / format("png"|"jpeg"|"auto", 기본 auto) /
// quality(JPEG 품질, 기본 82) / display(다중 모니터 인덱스, 1부터 — mac/linux 일부만)
func doScreen(c Command) map[string]interface{} {
	tmp, err := os.CreateTemp("", "indiebiz-screen-*.png")
	if err != nil {
		return errResult("tmp_failed", err.Error())
	}
	path := tmp.Name()
	tmp.Close()
	defer os.Remove(path)

	tool, err := captureScreen(path, c.Display)
	if err != nil {
		return errResult("capture_failed", err.Error())
	}

	raw, err := os.ReadFile(path)
	if err != nil || len(raw) == 0 {
		return errResult("capture_empty",
			"캡처 도구는 실행됐지만 이미지가 비었습니다(권한 거부일 수 있습니다). "+screenPermissionHint())
	}

	img, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil {
		return errResult("decode_failed", err.Error())
	}
	ow, oh := img.Bounds().Dx(), img.Bounds().Dy()

	maxW := c.MaxWidth
	if maxW <= 0 {
		maxW = defaultMaxWidth
	}
	scaled := downscale(img, maxW)
	w, h := scaled.Bounds().Dx(), scaled.Bounds().Dy()

	quality := c.Quality
	if quality <= 0 || quality > 100 {
		quality = 82
	}
	data, media, err := encodeBounded(scaled, c.Format, quality)
	if err != nil {
		return errResult("encode_failed", err.Error())
	}

	// 이 그림이 곧 AI 의 좌표계가 된다 — 입력 op 가 참조하도록 배율을 기록.
	pw, ph := logicalScreenSize(ow, oh)
	lastShot = shotFrame{imgW: w, imgH: h, pointW: pw, pointH: ph, valid: true}

	return map[string]interface{}{
		"op": "screen", "b64": base64.StdEncoding.EncodeToString(data),
		"media_type": media, "width": w, "height": h,
		"orig_width": ow, "orig_height": oh,
		"bytes": len(data), "tool": tool,
	}
}

// encodeBounded — maxImageBytes 안에 들어올 때까지 인코딩. format 이 auto(기본)면
// PNG 를 먼저 시도하고(글자 선명), 너무 크면 JPEG 로 내려간다.
func encodeBounded(img image.Image, format string, quality int) ([]byte, string, error) {
	tryPNG := func() ([]byte, error) {
		var buf bytes.Buffer
		err := png.Encode(&buf, img)
		return buf.Bytes(), err
	}
	tryJPEG := func(q int) ([]byte, error) {
		var buf bytes.Buffer
		err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: q})
		return buf.Bytes(), err
	}

	switch format {
	case "png":
		b, err := tryPNG()
		if err != nil {
			return nil, "", err
		}
		if len(b) <= maxImageBytes {
			return b, "image/png", nil
		}
		// png 를 명시했어도 상한은 지킨다 — 통화가 터지는 것보다 형식이 바뀌는 게 낫다.
	case "jpeg", "jpg":
		// 아래 JPEG 경로로
	default: // auto
		if b, err := tryPNG(); err == nil && len(b) <= pngPreferBelow {
			return b, "image/png", nil
		}
	}

	for q := quality; q >= 40; q -= 15 {
		b, err := tryJPEG(q)
		if err != nil {
			return nil, "", err
		}
		if len(b) <= maxImageBytes {
			return b, "image/jpeg", nil
		}
	}
	b, err := tryJPEG(35)
	if err != nil {
		return nil, "", err
	}
	return b, "image/jpeg", nil
}

// downscale — 박스 평균 축소. stdlib 엔 리사이즈가 없고 x/image 는 외부 모듈이라
// 직접 구현한다. 최근접(nearest)은 화면 글자를 뭉개므로 평균을 쓴다(축소엔 이게 정석).
// 확대는 하지 않는다(원본보다 크게 만들 이유가 없다).
func downscale(src image.Image, maxW int) image.Image {
	b := src.Bounds()
	sw, sh := b.Dx(), b.Dy()
	if sw <= maxW || sw == 0 || sh == 0 {
		return src
	}
	dw := maxW
	dh := sh * dw / sw
	if dh < 1 {
		dh = 1
	}
	dst := image.NewRGBA(image.Rect(0, 0, dw, dh))
	for dy := 0; dy < dh; dy++ {
		y0 := b.Min.Y + dy*sh/dh
		y1 := b.Min.Y + (dy+1)*sh/dh
		if y1 <= y0 {
			y1 = y0 + 1
		}
		for dx := 0; dx < dw; dx++ {
			x0 := b.Min.X + dx*sw/dw
			x1 := b.Min.X + (dx+1)*sw/dw
			if x1 <= x0 {
				x1 = x0 + 1
			}
			var sr, sg, sb, n uint64
			for y := y0; y < y1; y++ {
				for x := x0; x < x1; x++ {
					r, g, bl, _ := src.At(x, y).RGBA() // 16bit
					sr += uint64(r)
					sg += uint64(g)
					sb += uint64(bl)
					n++
				}
			}
			if n == 0 {
				n = 1
			}
			i := dst.PixOffset(dx, dy)
			dst.Pix[i+0] = uint8(sr / n >> 8)
			dst.Pix[i+1] = uint8(sg / n >> 8)
			dst.Pix[i+2] = uint8(sb / n >> 8)
			dst.Pix[i+3] = 255
		}
	}
	return dst
}

// captureScreen — OS 기본 도구로 path 에 PNG 를 남긴다. 반환값 = 쓴 도구 이름(감사용).
func captureScreen(path string, display int) (string, error) {
	switch runtime.GOOS {
	case "darwin":
		// -x 무음(셔터음 없음), -C 커서 제외 안 함(기본), -t png
		args := []string{"-x", "-t", "png"}
		if display > 0 {
			args = append(args, "-D", strconv.Itoa(display))
		}
		args = append(args, path)
		if err := runCapture("screencapture", args...); err != nil {
			return "", fmt.Errorf("screencapture 실패: %w — %s", err, screenPermissionHint())
		}
		return "screencapture", nil
	case "windows":
		return "powershell", captureWindows(path)
	default:
		return captureLinux(path)
	}
}

// captureWindows — .NET System.Drawing 으로 가상 화면(다중 모니터 전체)을 PNG 로.
// OS 기본 탑재라 추가 설치가 없다. 백슬래시·따옴표를 피해 한 줄로 넘긴다.
func captureWindows(path string) error {
	ps := "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; " +
		"$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; " +
		"$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; " +
		"$g = [System.Drawing.Graphics]::FromImage($bmp); " +
		"$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size); " +
		"$bmp.Save('" + path + "', [System.Drawing.Imaging.ImageFormat]::Png); " +
		"$g.Dispose(); $bmp.Dispose()"
	if err := runCapture("powershell", "-NoProfile", "-NonInteractive", "-Command", ps); err != nil {
		return fmt.Errorf("PowerShell 캡처 실패: %w (세션 0 서비스나 잠긴 화면에서는 캡처가 검게 나올 수 있습니다)", err)
	}
	return nil
}

// captureLinux — 배포판·디스플레이 서버(X11/Wayland)마다 도구가 달라 있는 것을 찾는다.
// 하나도 없으면 정직하게 실패하고 설치 안내를 준다(있는 척하지 않는다).
func captureLinux(path string) (string, error) {
	type cand struct {
		bin  string
		args []string
	}
	cands := []cand{
		{"grim", []string{path}},                        // Wayland
		{"scrot", []string{"-o", path}},                 // X11
		{"import", []string{"-window", "root", path}},   // ImageMagick
		{"gnome-screenshot", []string{"-f", path}},      // GNOME
		{"spectacle", []string{"-b", "-n", "-o", path}}, // KDE
	}
	var tried []string
	for _, c := range cands {
		if _, err := exec.LookPath(c.bin); err != nil {
			continue
		}
		tried = append(tried, c.bin)
		if err := runCapture(c.bin, c.args...); err == nil {
			if st, err := os.Stat(path); err == nil && st.Size() > 0 {
				return c.bin, nil
			}
		}
	}
	if len(tried) == 0 {
		return "", fmt.Errorf("이 PC 에 화면 캡처 도구가 없습니다 — grim(Wayland) 또는 scrot/imagemagick(X11) 설치가 필요합니다")
	}
	return "", fmt.Errorf("캡처 도구(%v)를 실행했지만 이미지를 얻지 못했습니다(Wayland 권한이나 헤드리스 세션일 수 있습니다)", tried)
}

func runCapture(bin string, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), captureTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, bin, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := oneLine(stderr.String(), 200)
		if msg != "" {
			return fmt.Errorf("%v: %s", err, msg)
		}
		return err
	}
	return nil
}

// screenPermissionHint — macOS 는 화면 기록 권한이 없으면 캡처가 조용히 빈 이미지가 된다.
// 이 마찰은 버그가 아니라 그 PC 주인이 보는 **가시적 동의** 지점이다 — 안내만 정확히 한다.
func screenPermissionHint() string {
	if runtime.GOOS == "darwin" {
		return "맥이면 시스템 설정 > 개인정보 보호 및 보안 > 화면 기록 에서 이 헬퍼(또는 터미널)를 허용한 뒤 헬퍼를 재실행하세요."
	}
	return "화면 접근 권한과 그래픽 세션(로그인 상태)을 확인하세요."
}
