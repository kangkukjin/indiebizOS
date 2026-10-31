package main

import "time"

type screenQuality struct{ level, stable int }

func (q *screenQuality) observe(elapsed time.Duration) {
	if elapsed > 150*time.Millisecond {
		q.stable = 0
		if q.level < 3 {
			q.level++
		}
		return
	}
	if elapsed < 50*time.Millisecond {
		q.stable++
	} else {
		q.stable = 0
	}
	if q.stable >= 60 && q.level > 0 {
		q.level--
		q.stable = 0
	}
}
func (q *screenQuality) dimensions() (int, int) {
	widths := [4]int{1600, 1280, 960, 640}
	qualities := [4]int{65, 55, 45, 35}
	return widths[q.level], qualities[q.level]
}
func (q *screenQuality) interval() time.Duration {
	fps := [4]int{15, 10, 6, 3}
	return time.Second / time.Duration(fps[q.level])
}
func screenJPEGQuality(value int) int {
	if value < 35 || value > 80 {
		return 65
	}
	return value
}
