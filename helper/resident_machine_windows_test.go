package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"
)

func TestMachineInstallRequiresInitialAdministrator(t *testing.T) {
	if windows.GetCurrentProcessToken().IsElevated() {
		t.Skip("requires a normal user token")
	}
	err := residentMachineInstall(filepath.Join(t.TempDir(), "missing-invitation.json"))
	if err == nil || !strings.Contains(err.Error(), "관리자") {
		t.Fatalf("expected initial authorization requirement: %v", err)
	}
	if residentMachineActive(&Config{MachineService: true}) {
		t.Fatal("a configuration flag granted system identity")
	}
}

func TestMachineHostChild(t *testing.T) {
	path := os.Getenv("INDIEBIZ_MACHINE_HOST_TEST")
	if path == "" {
		return
	}
	file, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		os.Exit(17)
	}
	file.WriteString("started\n")
	file.Close()
	if os.Getenv("INDIEBIZ_MACHINE_HOST_EXIT") == "1" {
		os.Exit(0)
	}
	time.Sleep(time.Minute)
	os.Exit(18)
}

func TestMachineHostStopsOwnedWorkerAndRestartsAfterCleanExit(t *testing.T) {
	for _, restart := range []bool{false, true} {
		root := t.TempDir()
		marker := filepath.Join(root, "starts.txt")
		host := &residentMachineHost{cfg: &Config{DataDir: root}, command: func(ctx context.Context) *exec.Cmd {
			cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestMachineHostChild$")
			cmd.Env = append(os.Environ(), "INDIEBIZ_MACHINE_HOST_TEST="+marker)
			if restart {
				cmd.Env = append(cmd.Env, "INDIEBIZ_MACHINE_HOST_EXIT=1")
			}
			return cmd
		}}
		requests, status := make(chan svc.ChangeRequest, 2), make(chan svc.Status, 20)
		done := make(chan uint32, 1)
		go func() { _, code := host.Execute(nil, requests, status); done <- code }()
		want := 1
		if restart {
			want = 2
		}
		deadline := time.Now().Add(10 * time.Second)
		started := false
		for time.Now().Before(deadline) {
			raw, _ := os.ReadFile(marker)
			if strings.Count(string(raw), "started") >= want {
				started = true
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		requests <- svc.ChangeRequest{Cmd: svc.Stop}
		select {
		case code := <-done:
			if code != 0 || !started {
				t.Fatalf("worker lifecycle: exit=%d started=%v restart=%v", code, started, restart)
			}
		case <-time.After(10 * time.Second):
			t.Fatal("SCM stop failed to reap worker")
		}
	}
}

func TestMachineHostCleanupEndsAfterAcknowledgedRemoval(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "removing.json"), []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	host := &residentMachineHost{cfg: &Config{DataDir: root}, command: func(ctx context.Context) *exec.Cmd {
		cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestMachineHostChild$")
		cmd.Env = append(os.Environ(), "INDIEBIZ_MACHINE_HOST_TEST="+filepath.Join(root, "starts.txt"), "INDIEBIZ_MACHINE_HOST_EXIT=1")
		return cmd
	}}
	requests, status := make(chan svc.ChangeRequest, 1), make(chan svc.Status, 10)
	done := make(chan uint32, 1)
	go func() { _, code := host.Execute(nil, requests, status); done <- code }()
	select {
	case code := <-done:
		if code != 0 {
			t.Fatalf("cleanup service exit=%d", code)
		}
	case <-time.After(10 * time.Second):
		requests <- svc.ChangeRequest{Cmd: svc.Stop}
		t.Fatal("host restarted completed cleanup")
	}
}

func TestMachineProtectionReplacesExistingAccessList(t *testing.T) {
	// Inspect the descriptor without applying administrator-only permissions
	// to the test process's own directory (which would lock out cleanup).
	sd, err := windows.SecurityDescriptorFromString("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)")
	if err != nil {
		t.Fatal(err)
	}
	acl, _, err := sd.DACL()
	if err != nil || acl == nil {
		t.Fatalf("protected DACL missing: %v", err)
	}
	text := sd.String()
	if !strings.Contains(text, "D:P") || strings.Contains(text, ";;;BU") || strings.Contains(text, ";;;WD") {
		t.Fatalf("ordinary users can access the service store: %s", text)
	}
}

func TestMachineWorkerRefusesOrdinaryProcess(t *testing.T) {
	cfg := Config{MachineService: true}
	if residentMachineActive(&cfg) {
		t.Skip("test requires non-System identity")
	}
	path := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(path, []byte(`{"machine_service":true}`), 0600); err != nil {
		t.Fatal(err)
	}
	handled, code := residentMachineCLI([]string{"helper", "--resident-machine-worker", path})
	if !handled || code == 0 {
		t.Fatal("ordinary user launched a machine worker")
	}
}
