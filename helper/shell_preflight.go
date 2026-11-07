package main

// The target owns parsing and execution. A hub never certifies another OS dialect.
import (
	"bytes"
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
)

type preflightBuffer struct{ bytes.Buffer }

func (b *preflightBuffer) Write(p []byte) (int, error) {
	n := len(p)
	if left := 8192 - b.Len(); left > 0 {
		if len(p) > left {
			p = p[:left]
		}
		_, _ = b.Buffer.Write(p)
	}
	return n, nil
}

func shellPreflight(parent context.Context, candidate *exec.Cmd) map[string]interface{} {
	name := strings.TrimSuffix(strings.ToLower(filepath.Base(candidate.Path)), ".exe")
	source := candidate.Args[len(candidate.Args)-1]
	sum := sha256.Sum256([]byte(source))
	report := map[string]interface{}{"phase": "preflight", "status": "unsupported", "executed": false,
		"language": name, "source_hash": hex.EncodeToString(sum[:]), "total": 0, "items": []interface{}{},
		"runtime":  map[string]interface{}{"executable": candidate.Path, "cwd": candidate.Dir},
		"coverage": map[string]interface{}{"syntax": "unsupported", "lint": "not_checked", "external_commands": "not_checked"}}
	if name != "sh" && name != "bash" && name != "zsh" && name != "dash" && name != "powershell" && name != "pwsh" {
		return report
	}
	fail := func(code, message string) map[string]interface{} {
		report["status"] = "failed"
		report["items"] = []interface{}{map[string]interface{}{"code": code, "severity": "error", "message": message}}
		report["total"] = 1
		return report
	}
	if len(source) > 65536 {
		return fail("PREFLIGHT_LIMIT", "source exceeds 64 KiB")
	}
	ctx, cancel := context.WithTimeout(parent, 5*time.Second)
	defer cancel()
	var parser *exec.Cmd
	ps := name == "powershell" || name == "pwsh"
	if ps {
		const script = `$OutputEncoding = [Console]::OutputEncoding = [Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
$src = [Console]::In.ReadToEnd(); $tokens=$null; $errors=$null
$null=[System.Management.Automation.Language.Parser]::ParseInput($src,[ref]$tokens,[ref]$errors)
@{version=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition; items=@($errors | ForEach-Object {
@{code=$_.ErrorId; severity='error'; message=$_.Message; location=@{line=$_.Extent.StartLineNumber; column=$_.Extent.StartColumnNumber; encoding='utf16_1based'; source='execution_script'}}
})} | ConvertTo-Json -Compress -Depth 6`
		parser = exec.CommandContext(ctx, candidate.Path, "-NoProfile", "-NonInteractive", "-Command", script)
		parser.Stdin = strings.NewReader(source)
	} else {
		args := append([]string{}, candidate.Args[1:len(candidate.Args)-2]...)
		if name == "zsh" {
			args = append(args, "-f")
		}
		args = append(args, "-n", "-c", source)
		parser = exec.CommandContext(ctx, candidate.Path, args...)
	}
	parser.Dir = candidate.Dir
	env := candidate.Env
	if env == nil {
		env = os.Environ()
	}
	for _, pair := range env {
		key := strings.SplitN(pair, "=", 2)[0]
		if key != "BASH_ENV" && key != "ENV" && key != "ZDOTDIR" && key != "SHELLOPTS" && key != "BASHOPTS" {
			parser.Env = append(parser.Env, pair)
		}
	}
	configureShellCommand(parser)
	var output preflightBuffer
	parser.Stdout = &output
	parser.Stderr = &output
	err := parser.Run()
	if ctx.Err() != nil {
		return fail("PREFLIGHT_TIMEOUT", ctx.Err().Error())
	}
	var items []interface{}
	if ps {
		if err != nil {
			return fail("PREFLIGHT_UNAVAILABLE", output.String())
		}
		var parsed struct {
			Items   []interface{} `json:"items"`
			Version string        `json:"version"`
			Edition string        `json:"edition"`
		}
		if e := json.Unmarshal(bytes.TrimPrefix(output.Bytes(), []byte{239, 187, 191}), &parsed); e != nil {
			return fail("PREFLIGHT_PROTOCOL", e.Error())
		}
		items = parsed.Items
		report["runtime"].(map[string]interface{})["version"] = parsed.Version
		report["runtime"].(map[string]interface{})["edition"] = parsed.Edition
	} else if err != nil {
		if _, ok := err.(*exec.ExitError); !ok {
			return fail("PREFLIGHT_UNAVAILABLE", err.Error())
		}
		items = []interface{}{map[string]interface{}{"code": "SHELL_SYNTAX", "severity": "error", "message": output.String(), "location": nil}}
	}
	if items == nil {
		items = []interface{}{}
	}
	report["items"] = items
	report["total"] = len(items)
	report["status"] = "valid"
	if len(items) > 0 {
		report["status"] = "invalid"
	}
	report["coverage"].(map[string]interface{})["syntax"] = "checked"
	fingerprint := sha256.Sum256([]byte(fmt.Sprint(candidate.Path, candidate.Args[:len(candidate.Args)-1], candidate.Dir, env)))
	report["runtime_fingerprint"] = hex.EncodeToString(fingerprint[:])
	return report
}

func preflightRejected(report map[string]interface{}) map[string]interface{} {
	if report["status"] != "invalid" && report["status"] != "failed" {
		return nil
	}
	return map[string]interface{}{"success": false, "executed": false, "error": "shell_preflight", "preflight": report}
}
