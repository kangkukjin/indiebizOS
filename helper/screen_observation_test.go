package main

import (
	"context"
	"image"
	"image/color"
	"reflect"
	"runtime"
	"testing"
	"time"
)

func TestScreenUniformObservation(t *testing.T) {
	img := image.NewRGBA(image.Rect(3, 4, 13, 14))
	for _, c := range []color.RGBA{{0, 0, 0, 255}, {255, 255, 255, 255}} {
		for y := 4; y < 14; y++ {
			for x := 3; x < 13; x++ {
				img.Set(x, y, c)
			}
		}
		got := screenImageObservation(img)
		if got["image_observation"] != "uniform" || got["warning"] == nil {
			t.Fatal(got)
		}
		img.Set(12, 13, color.RGBA{12, 34, 56, 255})
		if got := screenImageObservation(img); got["image_observation"] != "non_uniform" || got["warning"] != nil {
			t.Fatal(got)
		}
	}
}

func TestScreenObservationSlotAndQueuedCancel(t *testing.T) {
	r := residentTestRuntime(t)
	r.active["one"], r.active["two"] = func() {}, func() {}
	j := residentTestJob(t, map[string]interface{}{"op": "screen"}) // Invalid GUI mode: no real capture.
	if !residentObservation(j) {
		t.Fatal("screen does not use observation slot")
	}
	if err := r.record(residentRecord{Job: j, State: "queued"}); err != nil {
		t.Fatal(err)
	}
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	r.wg.Wait()
	if got := residentReadRecord(t, r, j); got.State != "done" || got.Result["error"] != "needs_interactive" {
		t.Fatal(got)
	}
	j = residentTestJob(t, map[string]interface{}{"op": "screen", "mode": "interactive"})
	if err := r.record(residentRecord{Job: j, State: "queued"}); err != nil {
		t.Fatal(err)
	}
	r.cancelQueued(j.ID)
	if err := r.schedule(); err != nil {
		t.Fatal(err)
	}
	r.wg.Wait()
	if got := residentReadRecord(t, r, j); got.Result["cancelled"] != true {
		t.Fatal(got)
	}
}

func TestCaptureHonorsParentCancellation(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX fixture")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	start := time.Now()
	if err := runCapture(ctx, "/bin/sleep", "10"); err == nil {
		t.Fatal("capture ignored cancellation")
	}
	if time.Since(start) > time.Second {
		t.Fatal("capture did not stop promptly")
	}
}

func TestAfplayVolumeArguments(t *testing.T) {
	if got := residentAfplayArgs("/a file.wav", nil); !reflect.DeepEqual(got, []string{"/a file.wav"}) {
		t.Fatal(got)
	}
	for volume, want := range map[float64]string{0: "0", 25: "0.25", 100: "1"} {
		if got := residentAfplayArgs("/a file.wav", &volume); !reflect.DeepEqual(got, []string{"-v", want, "/a file.wav"}) {
			t.Fatal(got)
		}
	}
}
