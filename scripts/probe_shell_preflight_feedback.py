#!/usr/bin/env python3
"""Opt-in design experiment, NOT the production shell executor.

Checks the complete candidate before executing it. Only synthetic cases supplied
by the caller belong here. Windows requests use an explicitly selected resident
PC and its real PowerShell parser; this script installs no tools or settings.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import urllib.request
import uuid


def api(body):
    body = dict(body)
    for key, variable in (('agent_id', 'INDIEBIZOS_AGENT_ID'), ('task_id', 'INDIEBIZOS_TASK_ID')):
        if os.environ.get(variable):
            body[key] = os.environ[variable]
    request = urllib.request.Request(
        'http://127.0.0.1:8765/ibl/execute', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def local(case, folder):
    executable = {'sh': '/bin/sh', 'zsh': '/bin/zsh'}[case['shell']]
    # No candidate evaluation during parsing. Do not inherit per-command hooks.
    # zsh still owns its installation-wide zshenv; this is not a security sandbox.
    env = {k: v for k, v in os.environ.items()
           if k not in {'BASH_ENV', 'ENV', 'ZDOTDIR', 'SHELLOPTS', 'BASHOPTS'}}
    flags = ['-f'] if case['shell'] == 'zsh' else []
    checked = subprocess.run([executable, *flags, '-n'], input=case['source'],
                             text=True, capture_output=True, env=env,
                             cwd=folder, timeout=5)
    result = {'status': 'invalid' if checked.returncode else 'valid',
              'executed': False, 'checker_exit_code': checked.returncode,
              'runtime': {'os': platform.system(), 'executable': executable,
                          'dialect': case['shell'],
                          'startup': '-f; global zshenv may run' if flags else 'noninteractive; ENV/BASH_ENV removed'},
              'diagnostics': ([{'severity': 'error', 'code': 'SHELL_SYNTAX',
                                'message': checked.stderr.strip(),
                                'location': None}] if checked.returncode else []),
              'coverage': {'syntax': True, 'lint': False, 'external_commands': False}}
    if checked.returncode:
        return result
    result['executed'] = True
    run = subprocess.run([executable, *flags], input=case['source'], text=True,
                         capture_output=True, env=env, cwd=folder, timeout=5)
    result.update(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)
    return result


def windows(case):
    encoded = base64.b64encode(case['source'].encode()).decode()
    # The candidate is data until ParseInput has returned zero parse errors.
    # This runs on the target Windows host, not a macOS PowerShell approximation.
    wrapper = r'''
$src = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__'))
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($src, [ref]$tokens, [ref]$errors)
$diagnostics = @($errors | ForEach-Object {
    [ordered]@{severity='error'; code=$_.ErrorId; message=$_.Message;
        location=[ordered]@{line=$_.Extent.StartLineNumber; column=$_.Extent.StartColumnNumber}}
})
$result = [ordered]@{status='invalid'; executed=$false; diagnostics=$diagnostics;
    runtime=[ordered]@{os=[Environment]::OSVersion.VersionString;
        executable=(Get-Process -Id $PID).Path; dialect='powershell';
        version=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition};
    coverage=[ordered]@{syntax=$true; lint=$false; external_commands=$false}}
if ($errors.Count -eq 0) {
    $result.status = 'valid'
    $result.executed = $true
    try {
        $result.stdout = @(& ([scriptblock]::Create($src)) | ForEach-Object { [string]$_ })
        $result.exit_code = 0
    } catch {
        $result.exit_code = 1
        $result.stderr = $_.Exception.Message
    }
}
$result | ConvertTo-Json -Compress -Depth 8
'''.replace('__SOURCE__', encoded)
    params = {'op': 'shell', 'limb': case['device_id'], 'shell': 'powershell',
              'cmd': wrapper, 'timeout': 10, 'wait': 20, 'mode': 'observe',
              'request_id': 'preflight-probe-' + uuid.uuid4().hex}
    try:
        response = api({'code': '[limbs:guestpc]' + json.dumps(params),
                        'edition': 2, 'origin': 'training'})
    except (OSError, ValueError) as exc:
        return {'status': 'unavailable', 'executed': None,
                'request_id': params['request_id'], 'reason': str(exc),
                'instruction': 'Transport result unknown; do not automatically resubmit'}
    value = response.get('value') or {}
    execution = value.get('result') or {}
    if not response.get('success') or execution.get('exit') != 0:
        # No automatic re-submission after ambiguous remote transport.
        return {'status': 'unavailable', 'executed': None,
                'reason': 'remote result unavailable; inspect the original receipt',
                'task_ref': value.get('task_ref'), 'transport': response}
    result = json.loads(execution['output'].strip())
    result['task_ref'] = value.get('task_ref')
    return result


def initialise(folder, windows_device):
    folder.mkdir(parents=True, exist_ok=False)
    cases = {
        'mac_sh': {'shell': 'sh', 'source': "printf 'MAC_SH_EXECUTED\\n' >> mac-sh-executions.txt\n"
                  "if true; then\n  printf '%s\\n' 'MAC_SH_OK'\n"},
        'mac_zsh': {'shell': 'zsh', 'source': "printf 'MAC_ZSH_EXECUTED\\n' >> mac-zsh-executions.txt\n"
                   "values=(alpha beta)\nif [[ ${#values} -eq 2 ]]; then\n  print -r -- 'MAC_ZSH_OK'\n"},
        'windows_ps': {'shell': 'powershell', 'device_id': windows_device,
                       'source': "Write-Output 'WINDOWS_FIRST_EFFECT'\nif ($true) {\n  Write-Output 'WINDOWS_PS_OK'\n"},
    }
    for name, case in cases.items():
        for suffix in ('.json', '.original.json'):
            (folder / (name + suffix)).write_text(json.dumps(case, ensure_ascii=False, indent=2))
    code = ('#!ibl edition=2\n[self:write]' + json.dumps({
        'path': str(folder / 'ibl-effect.txt'), 'content': 'IBL_EXECUTED_ONCE'},
        ensure_ascii=False) + '\nreturn $subtotal + 3\n')
    (folder / 'program.ibl').write_text(code)
    (folder / 'program.original.txt').write_text(code)
    return {'folder': str(folder), 'cases': list(cases), 'ibl': str(folder / 'program.ibl')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='op', required=True)
    init = commands.add_parser('init')
    init.add_argument('folder', type=Path)
    init.add_argument('--windows-device', required=True)
    run = commands.add_parser('run')
    run.add_argument('case', type=Path)
    args = parser.parse_args()
    if args.op == 'init':
        result = initialise(args.folder.resolve(), args.windows_device)
    else:
        path = args.case.resolve()
        case = json.loads(path.read_text())
        source = case['source']
        if not isinstance(source, str) or len(source.encode()) > 65536:
            raise ValueError('candidate must be a text script under 64 KiB')
        started = time.time()
        if case['shell'] in ('sh', 'zsh'):
            result = local(case, path.parent)
        elif case['shell'] == 'powershell':
            result = windows(case)
        else:
            result = {'status': 'unsupported', 'executed': False, 'diagnostics': [],
                      'reason': 'No parser adapter for the selected shell; not certified valid'}
        result = {'prototype': True, 'case': path.name, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                  'started_at': started, 'elapsed_seconds': round(time.time() - started, 3), **result}
        with (path.parent / 'attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
