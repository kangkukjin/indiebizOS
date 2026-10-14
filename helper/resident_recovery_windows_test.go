package main

import "testing"

func TestRecoveryLockExcludesDuplicatesAndReleases(t *testing.T) {
	id := residentID()
	release, duplicate, err := residentRecoveryLock(id)
	if err != nil || duplicate {
		t.Fatal(duplicate, err)
	}
	held := true
	t.Cleanup(func() {
		if held {
			release()
		}
	})
	_, duplicate, err = residentRecoveryLock(id)
	if err != nil || !duplicate {
		t.Fatal(duplicate, err)
	}
	release()
	held = false
	again, duplicate, err := residentRecoveryLock(id)
	if err != nil || duplicate {
		t.Fatal(duplicate, err)
	}
	again()
}
