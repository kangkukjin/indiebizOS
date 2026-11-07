"""OS shell syntax inspection. Never executes candidate commands or changes dialects.

Kept in base because repair, providers and services share this OS primitive.
No language-server, registry, model, permission or retry policy lives here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

from preflight_feedback import publish, blocked, rejection

MAX_SOURCE = 65536
PS_PARSE = r"""
$OutputEncoding = [Console]::OutputEncoding = [Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
$src = [Console]::In.ReadToEnd()
$tokens = $null; $errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput($src, [ref]$tokens, [ref]$errors)
@{version=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition;
items=@($errors | ForEach-Object { @{code=$_.ErrorId; severity='error'; message=$_.Message;
location=@{line=$_.Extent.StartLineNumber; column=$_.Extent.StartColumnNumber; encoding='utf16_1based'}} })
} | ConvertTo-Json -Compress -Depth 6
"""


def default_argv(source, shell=None):
    """New Windows commands use PS5.1; legacy batch callers explicitly select cmd."""
    kind = (shell or ('powershell' if os.name == 'nt' else 'sh')).lower()
    if kind in ('powershell', 'pwsh'):
        return [kind, '-NoProfile', '-NonInteractive', '-Command',
                "$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); " + source]
    if kind == 'cmd' and os.name == 'nt':
        return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', source]
    if kind in ('sh', 'bash', 'zsh') and os.name != 'nt':
        return ['/bin/sh' if kind == 'sh' else shutil.which(kind) or '/bin/' + kind, '-c', source]
    raise ValueError('이 OS에서 지원하지 않는 shell: ' + kind)


def repair_argv(source, shell=None):
    """Preserve POSIX repair pipefail semantics; select Windows through the OS seam."""
    if shell or os.name == 'nt':
        return default_argv(source, shell)
    bash = shutil.which('bash')
    return ([bash, '-e', '-o', 'pipefail', '-c', source] if bash
            else ['/bin/sh', '-e', '-c', source])


def run_parser(argv, *, cwd, env, input, timeout, cancelled=None):
    # A malformed source or startup file must not allocate unbounded output in RAM.
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=output, stderr=output, text=True, encoding='utf-8',
                                start_new_session=os.name != 'nt')
        started = time.monotonic()
        try:
            pending = input
            while True:
                if cancelled and cancelled():
                    raise OSError('preflight cancelled')
                left = timeout - (time.monotonic() - started)
                if left <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    proc.communicate(pending, timeout=min(.1, left))
                    break
                except subprocess.TimeoutExpired:
                    pending = None
            output.seek(0)
            text = output.read(8192).decode('utf-8', 'replace')
            return subprocess.CompletedProcess(argv, proc.returncode, text, '')
        finally:
            if proc.poll() is None:
                if os.name == 'nt':
                    proc.kill()
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                proc.wait()


def check(argv, *, cwd=None, env=None, runner=None, cancelled=None):
    """Inspect an exact shell -c/-Command invocation; other argv remains unsupported.

    runner allows an execution owner to use its existing sandbox/process lifetime.
    The returned validity covers syntax only, before execution of this candidate.
    """
    executable = str(argv[0])
    name = Path(executable).name.lower().removesuffix('.exe')
    dialect = name if name in ('sh', 'bash', 'dash', 'ksh', 'zsh', 'powershell', 'pwsh', 'cmd') else 'argv'
    switches = ('-Command', '-command') if dialect in ('powershell', 'pwsh') else ('-c',)
    index = next((i for i, x in enumerate(argv[1:], 1) if x in switches), None)
    source = argv[index + 1] if index is not None and index + 1 < len(argv) else (argv[-1] if dialect == 'cmd' else '')
    environment = dict(os.environ if env is None else env)
    resolved = shutil.which(executable, path=environment.get('PATH')) or executable
    runtime = {'executable': resolved, 'language': dialect, 'cwd': str(cwd or os.getcwd()),
               'options': argv[1:index] if index else argv[1:-1], 'os': os.name}
    try:
        stat = Path(resolved).stat()
        runtime['executable_revision'] = [str(stat.st_mtime_ns), stat.st_size]
    except OSError:
        pass
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    report = {'phase': 'preflight', 'status': 'unsupported', 'executed': False,
              'language': dialect, 'source_hash': hashlib.sha256(source.encode()).hexdigest(),
              'runtime': runtime, 'runtime_fingerprint': digest([runtime, digest(environment)]),
              'coverage': {'syntax': 'unsupported', 'lint': 'not_checked', 'external_commands': 'not_checked'},
              'items': [], 'total': 0}
    if dialect in ('cmd', 'argv') or index is None or index + 2 != len(argv):
        publish(report)
        return report
    try:
        if len(source.encode()) > MAX_SOURCE:
            raise OSError('preflight source exceeds 64 KiB')
        if '\x00' in source:
            raise ValueError('NUL in source')
        clean = {k: v for k, v in environment.items()
                 if k not in {'BASH_ENV', 'ENV', 'ZDOTDIR', 'SHELLOPTS', 'BASHOPTS'}}
        if dialect in ('powershell', 'pwsh'):
            parser = [resolved, '-NoProfile', '-NonInteractive', '-Command', PS_PARSE]
            timeout = 5
        else:
            # Preserve -e/pipefail/POSIX options, suppress optional interactive rc files.
            parser = [resolved, *argv[1:index], *(['-f'] if dialect == 'zsh' else []), '-n', '-c', source]
            timeout = 2
        kwargs = {'cwd': cwd, 'env': clean, 'input': source if dialect in ('powershell', 'pwsh') else '', 'timeout': timeout}
        result = runner(parser, **kwargs) if runner else run_parser(parser, cancelled=cancelled, **kwargs)
        output = (result.stdout or '') + (result.stderr or '')
        if result.returncode < 0:
            raise OSError('parser terminated: ' + str(result.returncode))
        if dialect in ('powershell', 'pwsh'):
            if result.returncode:
                raise OSError(output[:1000])
            parsed = json.loads(output.lstrip('\ufeff'))
            report['items'] = parsed['items']
            runtime.update(version=parsed['version'], edition=parsed['edition'])
        elif result.returncode:
            location = re.search(r'(?:line |:)(\d+):', output)
            report['items'] = [{'code': 'SHELL_SYNTAX', 'severity': 'error', 'message': output[:2000],
                                'location': {'line': int(location[1]), 'column': None} if location else None}]
        report['status'] = 'invalid' if report['items'] else 'valid'
        report['coverage']['syntax'] = 'checked'
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report.update(status='failed', items=[{'code': 'PREFLIGHT_UNAVAILABLE', 'severity': 'error',
                                              'message': str(exc)[:1000], 'location': None}])
        report['coverage']['syntax'] = 'unavailable'
    report['total'] = len(report['items'])
    report['runtime_fingerprint'] = digest([runtime, digest(environment)])
    publish(report)
    return report
