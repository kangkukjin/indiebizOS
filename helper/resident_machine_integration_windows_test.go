package main

// Run on an elevated Windows CI runner with IB_MACHINE_INTEGRATION_BINARY set
// to a freshly built helper. No real central credentials or registered PC used.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

func TestMachineServiceRealInstallExecuteAndRemove(t *testing.T) {
	binary := os.Getenv("IB_MACHINE_INTEGRATION_BINARY")
	if binary == "" {
		t.Skip("set IB_MACHINE_INTEGRATION_BINARY to the built helper for SCM integration")
	}
	if !windows.GetCurrentProcessToken().IsElevated() {
		t.Fatal("SCM integration requires an elevated Windows runner")
	}
	invitation, generation := residentID()+residentID(), residentID()
	var mu sync.Mutex
	var installation string
	sent, removing, elevated := false, false, false
	result := make(chan map[string]interface{}, 1)
	removed := make(chan struct{}, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/limb/resident/ws" {
			http.NotFound(w, r)
			return
		}
		var body map[string]interface{}
		if json.NewDecoder(r.Body).Decode(&body) != nil {
			http.Error(w, "body", 400)
			return
		}
		mu.Lock()
		defer mu.Unlock()
		response := map[string]interface{}{"success": true}
		switch r.URL.Path {
		case "/limb/resident/enroll":
			installation, _ = body["installation_id"].(string)
			proof, _ := body["enrollment_proof"].(string)
			h := sha256.Sum256([]byte(proof))
			response = map[string]interface{}{"key": "scm-test-key", "alias": "SCM integration", "registration": map[string]interface{}{
				"generation": generation, "enrollment_proof_hash": hex.EncodeToString(h[:])}}
		case "/limb/resident/sync":
			if body["key"] != "scm-test-key" || body["installation_id"] != installation {
				http.Error(w, "auth", 403)
				return
			}
			if caps, ok := body["capabilities"].(map[string]interface{}); ok {
				elevated = caps["elevation_unattended"] == true && caps["service_scope"] == "machine"
			}
			ack := []string{}
			if events, ok := body["events"].([]interface{}); ok {
				for _, item := range events {
					ev, _ := item.(map[string]interface{})
					id, _ := ev["event_id"].(string)
					ack = append(ack, id)
					if ev["kind"] == "result" {
						payload, _ := ev["payload"].(map[string]interface{})
						select {
						case result <- payload:
						default:
						}
						removing = true
					}
				}
			}
			jobs := []Job{}
			if !sent {
				code, _ := json.Marshal(map[string]interface{}{"op": "shell", "cmd": "whoami /user /fo csv /nh", "resident": true,
					"generation": generation, "elevate": true, "timeout": 30})
				jobs = append(jobs, Job{ID: residentID(), Code: string(code)})
				sent = true
			}
			state := "active"
			if removing {
				state = "removal_pending"
			}
			response = map[string]interface{}{"success": true, "jobs": jobs, "ack": ack, "generation": generation, "state": state}
		case "/limb/resident/local-state":
			removing = true
		case "/limb/resident/removed":
			response["registration"] = map[string]string{"state": "removed"}
			select {
			case removed <- struct{}{}:
			default:
			}
		default:
			http.NotFound(w, r)
			return
		}
		json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()
	cfg := Config{Mode: "enroll", Key: invitation, Base: server.URL, Alias: "SCM integration"}
	configPath := filepath.Join(t.TempDir(), "invite.json")
	if err := residentSave(configPath, cfg); err != nil {
		t.Fatal(err)
	}
	programFiles, err := windows.KnownFolderPath(windows.FOLDERID_ProgramFiles, 0)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256([]byte(invitation))
	root := filepath.Join(programFiles, "IndieBizManaged", hex.EncodeToString(sum[:8]))
	defer func() {
		mu.Lock()
		id := installation
		mu.Unlock()
		manager, err := mgr.Connect()
		if err == nil {
			defer manager.Disconnect()
			if service, e := manager.OpenService(residentServiceName(&Config{InstallationID: id})); e == nil {
				service.Control(svc.Stop)
				for deadline := time.Now().Add(15 * time.Second); time.Now().Before(deadline); {
					status, e := service.Query()
					if e != nil || status.State == svc.Stopped {
						break
					}
					time.Sleep(100 * time.Millisecond)
				}
				service.Delete()
				service.Close()
			}
		}
		os.RemoveAll(root)
	}()
	if out, err := exec.Command(binary, "--resident-machine-install", configPath).CombinedOutput(); err != nil {
		t.Fatalf("install: %s: %v", out, err)
	}
	select {
	case got := <-result:
		output, _ := got["output"].(string)
		mu.Lock()
		active := elevated
		mu.Unlock()
		if !active || got["exit"] != float64(0) || !strings.Contains(output, "S-1-5-18") {
			t.Fatalf("unattended System job: %v active=%v", got, active)
		}
	case <-time.After(60 * time.Second):
		t.Fatal("machine service did not execute the authenticated job")
	}
	select {
	case <-removed:
	case <-time.After(30 * time.Second):
		t.Fatal("central removal was not acknowledged")
	}
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(filepath.Join(root, "service.exe")); os.IsNotExist(err) {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatal("service host was not removed after acknowledging removal")
}
