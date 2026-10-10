package main

import (
	"fmt"
	"image"
)

// Report only what pixels prove. A uniform image cannot establish display power,
// capture permissions, a locked session, or the meaning of the displayed content.
func screenImageObservation(img image.Image) map[string]interface{} {
	b := img.Bounds()
	if b.Empty() {
		return nil
	}
	r, g, blue, a := img.At(b.Min.X, b.Min.Y).RGBA()
	for y := b.Min.Y; y < b.Max.Y; y++ {
		for x := b.Min.X; x < b.Max.X; x++ {
			rr, gg, bb, aa := img.At(x, y).RGBA()
			if rr != r || gg != g || bb != blue || aa != a {
				return map[string]interface{}{"image_observation": "non_uniform"}
			}
		}
	}
	return map[string]interface{}{
		"image_observation": "uniform",
		"warning":           fmt.Sprintf("단색 캡처(RGBA=%d,%d,%d,%d)입니다. 화면 전원 꺼짐·잠금·권한 문제인지 실제 단색 화면인지는 이 이미지로 확인할 수 없습니다.", r>>8, g>>8, blue>>8, a>>8),
	}
}
