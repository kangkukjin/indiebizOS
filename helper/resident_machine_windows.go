package main

// Machine installations have their own enrollment key in an administrator-only
// directory. They receive jobs directly from the authenticated hub; there is no
// user-writable command queue or local arbitrary-command elevation broker.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

func residentMachineActive(cfg *Config) bool {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	return cfg.MachineService && err == nil && user.User.Sid.String() == "S-1-5-18"
}

func residentMachineSetup(cfg *Config) error {
	file, err := os.CreateTemp("", "indiebiz-machine-invite-*.json")
	if err != nil {
		return err
	}
	path := file.Name()
	file.Close()
	defer os.Remove(path)
	if err = residentSave(path, cfg); err != nil {
		return err
	}
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	command := residentPowerShell("$p = Start-Process -FilePath " + residentPowerShellQuote(exe) +
		" -ArgumentList @('--resident-machine-install'," + residentPowerShellQuote("\""+path+"\"") +
		") -Verb RunAs -Wait -PassThru; exit $p.ExitCode")
	if err = command.Run(); err != nil {
		return fmt.Errorf("무인 관리 서비스 등록 실패: 관리자 승인과 중앙의 보호 등록 지원을 확인하세요: %w", err)
	}
	return nil
}

func residentMachineCLI(args []string) (bool, int) {
	if len(args) < 2 || !strings.HasPrefix(args[1], "--resident-machine-") {
		return false, 0
	}
	var err error
	if len(args) != 3 {
		err = fmt.Errorf("machine command requires a configuration path")
	} else {
		switch args[1] {
		case "--resident-machine-install":
			err = residentMachineInstall(args[2])
		case "--resident-machine-service", "--resident-machine-worker":
			var cfg Config
			var raw []byte
			raw, err = os.ReadFile(args[2])
			if err == nil {
				err = json.Unmarshal(raw, &cfg)
			}
			if err == nil && !residentMachineActive(&cfg) {
				err = fmt.Errorf("machine worker requires the installed LocalSystem service")
			}
			if err == nil && args[1] == "--resident-machine-service" {
				err = svc.Run(residentServiceName(&cfg), &residentMachineHost{cfg: &cfg, path: args[2]})
			} else if err == nil {
				hubCfg = &cfg
				cfg.Base = strings.TrimRight(cfg.Base, "/")
				err = startResident(&cfg)
			}
		default:
			err = fmt.Errorf("unknown machine command")
		}
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return true, 1
	}
	return true, 0
}

func residentMachineInstall(invitation string) error {
	if !windows.GetCurrentProcessToken().IsElevated() {
		return fmt.Errorf("최초 무인 관리 서비스 등록은 관리자 권한으로 실행하세요. 등록 이후 작업에는 UAC 승인이 필요하지 않습니다")
	}
	raw, err := os.ReadFile(invitation)
	if err != nil {
		return err
	}
	var invite Config
	if err = json.Unmarshal(raw, &invite); err != nil {
		return err
	}
	if invite.Mode != "enroll" || invite.Key == "" || invite.Base == "" {
		return fmt.Errorf("새 상주 PC 등록용 초대 설정이 필요합니다. 일반 헬퍼의 등록 키를 재사용하지 마세요")
	}
	programFiles, err := windows.KnownFolderPath(windows.FOLDERID_ProgramFiles, 0)
	if err != nil {
		return err
	}
	sum := sha256.Sum256([]byte(invite.Key))
	parent := filepath.Join(programFiles, "IndieBizManaged")
	root := filepath.Join(parent, hex.EncodeToString(sum[:8]))
	for _, path := range []string{parent, root} {
		if err = os.MkdirAll(path, 0700); err != nil {
			return err
		}
		p, e := windows.UTF16PtrFromString(path)
		if e != nil {
			return e
		}
		attrs, e := windows.GetFileAttributes(p)
		if e != nil {
			return e
		}
		if attrs&windows.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
			return fmt.Errorf("service path must not be a reparse point")
		}
		if err = residentMachineProtect(path); err != nil {
			return err
		}
	}
	configPath := filepath.Join(root, "indiebiz-helper.json")
	cfg := invite
	if raw, e := os.ReadFile(configPath); e == nil {
		if err = json.Unmarshal(raw, &cfg); err != nil {
			return err
		}
		if !cfg.MachineService || cfg.DataDir != root {
			return fmt.Errorf("existing service configuration mismatch")
		}
	} else if !os.IsNotExist(e) {
		return e
	} else {
		cfg.InstallationID, cfg.DataDir, cfg.MachineService = residentID(), root, true
		cfg.EnrollmentProof = residentID() + residentID()
		// Save enrollment identity before the network request, for retry.
		if err = residentSave(configPath, cfg); err != nil {
			return err
		}
	}
	if cfg.Mode == "enroll" {
		resp, e := residentPost(strings.TrimRight(cfg.Base, "/")+"/limb/resident/enroll", map[string]interface{}{
			"key": cfg.Key, "installation_id": cfg.InstallationID, "alias": cfg.Alias,
			"enrollment_proof": cfg.EnrollmentProof})
		if e != nil {
			return e
		}
		key, _ := resp["key"].(string)
		reg, _ := resp["registration"].(map[string]interface{})
		generation, _ := reg["generation"].(string)
		proofHash := sha256.Sum256([]byte(cfg.EnrollmentProof))
		if reg["enrollment_proof_hash"] != hex.EncodeToString(proofHash[:]) {
			return fmt.Errorf("중앙이 보호된 서비스 등록을 지원하지 않습니다. 중앙을 먼저 업데이트하세요")
		}
		if key == "" || generation == "" {
			return fmt.Errorf("invalid enrollment response")
		}
		cfg.Key, cfg.Generation, cfg.Mode = key, generation, "resident"
		cfg.Alias, _ = resp["alias"].(string)
		cfg.ExpiresAt, _ = resp["expires_at"].(float64)
		if err = residentSave(configPath, cfg); err != nil {
			return err
		}
	}
	manager, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer manager.Disconnect()
	name := residentServiceName(&cfg)
	if service, e := manager.OpenService(name); e == nil {
		defer service.Close()
		// An existing installation is never overwritten while its worker runs.
		return residentMachineStart(&cfg)
	} else if e != windows.ERROR_SERVICE_DOES_NOT_EXIST {
		return e
	}
	source, err := os.Executable()
	if err != nil {
		return err
	}
	host := filepath.Join(root, "service.exe")
	if err = residentCopy(source, host); err != nil {
		return err
	}
	if err = residentCopy(source, residentExecutable(root)); err != nil {
		return err
	}
	service, err := manager.CreateService(name, host, mgr.Config{
		DisplayName: "IndieBiz unattended management (" + cfg.Alias + ")",
		Description: "Authenticated central PC installation and configuration management",
		StartType:   mgr.StartAutomatic, ServiceStartName: "LocalSystem",
	}, "--resident-machine-service", configPath)
	if err != nil {
		return err
	}
	defer service.Close()
	if err = service.SetRecoveryActions([]mgr.RecoveryAction{
		{Type: mgr.ServiceRestart, Delay: 10 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 30 * time.Second},
		{Type: mgr.NoAction},
	}, 86400); err != nil {
		return err
	}
	if err = service.SetRecoveryActionsOnNonCrashFailures(true); err != nil {
		return err
	}
	return service.Start()
}

func residentMachineProtect(path string) error {
	sd, err := windows.SecurityDescriptorFromString("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)")
	if err != nil {
		return err
	}
	dacl, _, err := sd.DACL()
	if err != nil {
		return err
	}
	return windows.SetNamedSecurityInfo(path, windows.SE_FILE_OBJECT,
		windows.DACL_SECURITY_INFORMATION|windows.PROTECTED_DACL_SECURITY_INFORMATION,
		nil, nil, dacl, nil)
}

type residentMachineHost struct {
	cfg     *Config
	path    string
	command func(context.Context) *exec.Cmd
}

func (host *residentMachineHost) Execute(_ []string, requests <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	status <- svc.Status{State: svc.StartPending}
	current := svc.Status{State: svc.Running, Accepts: svc.AcceptStop | svc.AcceptShutdown}
	status <- current
	failures := 0
	for {
		_, removalErr := os.Stat(filepath.Join(host.cfg.DataDir, "removing.json"))
		cleaning := removalErr == nil
		ctx, cancel := context.WithCancel(context.Background())
		child := exec.CommandContext(ctx, residentExecutable(host.cfg.DataDir), "--resident-machine-worker", host.path)
		if cleaning {
			child = exec.CommandContext(ctx, filepath.Join(host.cfg.DataDir, "cleanup.exe"), "--resident-cleanup", host.cfg.DataDir)
		}
		if host.command != nil {
			child = host.command(ctx)
		}
		child.Dir = host.cfg.DataDir
		configureResidentProcess(child)
		log, err := os.OpenFile(filepath.Join(host.cfg.DataDir, "service.log"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
		if err != nil {
			cancel()
			return true, 1
		}
		child.Stdout, child.Stderr = log, log
		started := time.Now()
		if err = child.Start(); err != nil {
			log.Close()
			cancel()
			return true, 2
		}
		done := make(chan error, 1)
		go func() { done <- child.Wait() }()
		running := true
		var workerErr error
		for running {
			select {
			case request := <-requests:
				switch request.Cmd {
				case svc.Interrogate:
					status <- current
				case svc.Stop, svc.Shutdown:
					status <- svc.Status{State: svc.StopPending, WaitHint: 10000}
					cancel()
					<-done
					log.Close()
					return false, 0
				}
			case workerErr = <-done:
				running = false
			}
		}
		cancel()
		log.Close()
		if cleaning && workerErr == nil {
			return false, 0
		}
		if time.Since(started) >= time.Minute {
			failures = 0
		}
		failures++
		if failures >= 5 {
			return true, 3
		}
		// Both normal update exit and crash relaunch from the installed file.
		// SCM stop remains responsive during the retry delay.
		select {
		case request := <-requests:
			if request.Cmd == svc.Stop || request.Cmd == svc.Shutdown {
				return false, 0
			}
			status <- current
		case <-time.After(time.Second * time.Duration(failures)):
		}
	}
}

func residentMachineServiceExists(cfg *Config) bool {
	manager, err := mgr.Connect()
	if err != nil {
		return false
	}
	defer manager.Disconnect()
	service, err := manager.OpenService(residentServiceName(cfg))
	if err != nil {
		return false
	}
	service.Close()
	return true
}

func residentMachineStart(cfg *Config) error {
	manager, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer manager.Disconnect()
	service, err := manager.OpenService(residentServiceName(cfg))
	if err != nil {
		return err
	}
	defer service.Close()
	err = service.Start()
	if err == windows.ERROR_SERVICE_ALREADY_RUNNING {
		return nil
	}
	return err
}

func residentMachineAutostart(cfg *Config, remove bool) error {
	if !remove {
		return residentMachineStart(cfg)
	}
	manager, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer manager.Disconnect()
	service, err := manager.OpenService(residentServiceName(cfg))
	if err == windows.ERROR_SERVICE_DOES_NOT_EXIST {
		return nil
	}
	if err != nil {
		return err
	}
	defer service.Close()
	return service.Delete()
}
