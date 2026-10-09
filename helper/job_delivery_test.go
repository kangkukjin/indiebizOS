package main

import (
	"fmt"
	"testing"
)

func TestDeliveryPersistsAndRetriesOnlyResult(t *testing.T) {
	cfg := &Config{Base: "https://test.invalid", Key: "test", DataDir: t.TempDir()}
	d, err := openJobDelivery(cfg)
	if err != nil {
		t.Fatal(err)
	}
	j := Job{ID: "a", Code: "{}"}
	n := 0
	run := func(Job) map[string]interface{} { n++; return map[string]interface{}{"exit": 0} }
	d.execute(j, run)
	d.flush(func(string, map[string]interface{}) error { return fmt.Errorf("offline") })
	again, err := openJobDelivery(cfg)
	if err != nil {
		t.Fatal(err)
	}
	sent := 0
	again.flush(func(id string, r map[string]interface{}) error {
		sent++
		if id != "a" {
			t.Fatal(id)
		}
		return nil
	})
	again.execute(j, run)
	if n != 1 || sent != 1 {
		t.Fatalf("executions=%d results=%d", n, sent)
	}
	again.flush(func(string, map[string]interface{}) error { t.Fatal("acked result resent"); return nil })
}

func TestDeliveryInterruptedJobNeverRunsAgain(t *testing.T) {
	cfg := &Config{Base: "https://test.invalid", Key: "test", DataDir: t.TempDir()}
	d, _ := openJobDelivery(cfg)
	j := Job{ID: "a", Code: "{}"}
	if err := d.save(deliveryRecord{Job: j, Owner: "old-process", State: "running"}); err != nil {
		t.Fatal(err)
	}
	d.flush(func(id string, r map[string]interface{}) error {
		t.Fatal("실행 여부 불명인 작업을 먼저 완료 처리하면 안 됨")
		return nil
	})
	d.execute(j, func(Job) map[string]interface{} { t.Fatal("uncertain command rerun"); return nil })
}

func TestDeliveryRejectsDifferentCommandWithSameID(t *testing.T) {
	cfg := &Config{Base: "https://test.invalid", Key: "test", DataDir: t.TempDir()}
	d, _ := openJobDelivery(cfg)
	d.execute(Job{ID: "a", Code: "one"}, func(Job) map[string]interface{} { return map[string]interface{}{"exit": 0} })
	r := d.execute(Job{ID: "a", Code: "two"}, func(Job) map[string]interface{} { t.Fatal("conflict ran"); return nil })
	if r["error"] != "job_conflict" {
		t.Fatal(r)
	}
}

func TestDeliveryImmediateAckDoesNotSendTwice(t *testing.T) {
	d, _ := openJobDelivery(&Config{Base: "test", Key: "test", DataDir: t.TempDir()})
	d.execute(Job{ID: "a", Code: "{}"}, func(Job) map[string]interface{} { return map[string]interface{}{"exit": 0} })
	d.acknowledge("a")
	d.flush(func(string, map[string]interface{}) error { t.Fatal("already acknowledged"); return nil })
}
