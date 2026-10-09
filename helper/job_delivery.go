package main

// 명령을 실행하기 전에 수신을 기록하고, 완료 결과는 허브의 확인까지 보관한다.
// 실행 도중 헬퍼가 죽으면 재실행하지 않고 결과 불명으로 보고한다.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

type deliveryRecord struct {
	Job     Job                    `json:"job"`
	Owner   string                 `json:"owner"`
	State   string                 `json:"state"`
	Result  map[string]interface{} `json:"result,omitempty"`
	Ack     bool                   `json:"ack"`
	Updated int64                  `json:"updated"`
}

type jobDelivery struct {
	dir     string
	owner   string
	mu      sync.Mutex
	pending map[string]deliveryRecord
}

func openJobDelivery(cfg *Config) (*jobDelivery, error) {
	root := cfg.DataDir
	if root == "" {
		home, err := os.UserConfigDir()
		if err != nil {
			return nil, err
		}
		root = filepath.Join(home, "indiebiz-helper")
	}
	hash := sha256.Sum256([]byte(cfg.Base + "\x00" + cfg.Key))
	dir := filepath.Join(root, "delivery", fmt.Sprintf("%x", hash[:16]))
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	return &jobDelivery{dir: dir, owner: fmt.Sprintf("%d-%d", os.Getpid(), time.Now().UnixNano()),
		pending: make(map[string]deliveryRecord)}, nil
}

func (d *jobDelivery) path(id string) string {
	sum := sha256.Sum256([]byte(id))
	return filepath.Join(d.dir, fmt.Sprintf("%x.json", sum[:]))
}

func (d *jobDelivery) save(r deliveryRecord) error {
	b, err := json.Marshal(r)
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(d.dir, ".delivery-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(b)
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err == nil {
		err = os.Rename(f.Name(), d.path(r.Job.ID))
	}
	return err
}

func (d *jobDelivery) execute(j Job, run func(Job) map[string]interface{}) map[string]interface{} {
	d.mu.Lock()
	path := d.path(j.ID)
	// O_EXCL은 같은 작업을 두 실행자가 동시에 접수하는 것도 막는다.
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if os.IsExist(err) {
		b, readErr := os.ReadFile(path)
		var r deliveryRecord
		parseErr := json.Unmarshal(b, &r)
		d.mu.Unlock()
		if readErr != nil || parseErr != nil {
			return errResult("delivery_unknown", "작업 기록을 확인할 수 없어 재실행하지 않습니다")
		}
		if r.Job.Code != j.Code {
			return errResult("job_conflict", "같은 작업 ID의 내용이 다릅니다")
		}
		if r.State == "completed" {
			return r.Result
		}
		// 원래 작업의 최종 결과를 기다린다. 중복 수신은 새 결과를 확정하지 않는다.
		return nil
	}
	if err != nil {
		d.mu.Unlock()
		return errResult("delivery_storage", err.Error())
	}
	r := deliveryRecord{Job: j, Owner: d.owner, State: "running", Updated: time.Now().Unix()}
	b, err := json.Marshal(r)
	if err == nil {
		_, err = f.Write(b)
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	d.mu.Unlock()
	if err != nil {
		return errResult("delivery_storage", err.Error())
	}
	release := holdAwake()
	result := run(j)
	release()
	r.State, r.Result, r.Updated = "completed", result, time.Now().Unix()
	d.mu.Lock()
	if err := d.save(r); err != nil {
		// 디스크 오류 중에도 현재 프로세스는 결과를 유지하고 다음 flush에서 다시 저장한다.
		fmt.Fprintf(os.Stderr, "결과 저장 재시도 예정: %v\n", err)
	}
	d.pending[j.ID] = r
	d.mu.Unlock()
	return result
}

// 즉시 회신이 확인된 경우 다음 outbox 주기에 같은 결과를 다시 보내지 않는다.
func (d *jobDelivery) acknowledge(id string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	r, ok := d.pending[id]
	if !ok {
		return
	}
	r.Ack = true
	r.Updated = time.Now().Unix()
	if d.save(r) == nil {
		delete(d.pending, id)
	}
}

func (d *jobDelivery) flush(send func(string, map[string]interface{}) error) {
	d.mu.Lock()
	entries, _ := os.ReadDir(d.dir)
	for _, e := range entries {
		if filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(d.dir, e.Name()))
		var r deliveryRecord
		if err != nil || json.Unmarshal(b, &r) != nil {
			continue
		}
		if r.Ack {
			if time.Now().Unix()-r.Updated > 7*86400 {
				_ = os.Remove(filepath.Join(d.dir, e.Name()))
			}
			continue
		}
		// 이전 프로세스의 running 기록은 결과 불명으로 남긴다.
		// 이전 헬퍼가 아직 실행 중일 수도 있으므로 실패 결과를 먼저 확정하지 않는다.

		if r.State == "completed" {
			if _, ok := d.pending[r.Job.ID]; !ok {
				d.pending[r.Job.ID] = r
			}
		}
	}
	batch := make([]deliveryRecord, 0, len(d.pending))
	for _, r := range d.pending {
		if d.save(r) == nil {
			batch = append(batch, r)
		}
	}
	d.mu.Unlock()
	for _, r := range batch {
		if send(r.Job.ID, r.Result) != nil {
			continue
		}
		d.mu.Lock()
		r.Ack = true
		r.Updated = time.Now().Unix()
		if d.save(r) == nil {
			delete(d.pending, r.Job.ID)
		}
		d.mu.Unlock()
	}
}

// pid 표기는 깨우기 assertion의 프로세스 수명을 제한하는 데 사용한다.
var deliveryPID = strconv.Itoa(os.Getpid())
