"""Standalone Python file execution with a separate JSON result channel.

Raw evidence is private, finite-lived data. No parser, IBL values or IBL faults
enter this module. CLI and the IBL adapter call exactly the same functions.
"""
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import shutil
import sys
import time
import uuid

from script_process import run_process

PROTOCOL = 'file-script/1'
RESULT_ENV = 'INDIEBIZ_SCRIPT_RESULT'
RETENTION_SECONDS = 7 * 86400
MAX_CODE_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 32 * 1024 * 1024


class ScriptError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def digest(data):
    return sha256(data).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8') as stream:
            os.chmod(tmp, 0o600)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def strict_json(data):
    def invalid(value):
        raise ValueError('비유한 JSON 숫자: ' + value)
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('중복 JSON 키: ' + key)
            out[key] = value
        return out
    value = json.loads(data, parse_constant=invalid, object_pairs_hook=pairs)
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError('비유한 JSON 숫자')
        if isinstance(item, dict):
            for child in item.values():
                finite(child)
        elif isinstance(item, list):
            for child in item:
                finite(child)
    finite(value)
    return value


def read_result(directory):
    """Decode stored output without running anything; null is a real value."""
    path = Path(directory) / 'result.json'
    if not path.exists():
        raise ScriptError('RESULT_MISSING', '종료했지만 결과 파일을 쓰지 않았습니다. stdout은 진단이며 값으로 해석하지 않습니다.')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RESULT_BYTES:
        raise ScriptError('RESULT_INVALID', '결과는 32MiB 이하의 일반 JSON 파일이어야 합니다.')
    try:
        return strict_json(path.read_bytes())
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ScriptError('RESULT_INVALID', f'결과 JSON을 해석할 수 없습니다: {exc}') from exc


def snapshot(source, workspace, destination):
    """Copy Python code as a relative tree; imports and __file__ see that tree.

Data files and the outside world are not snapshotted. Their original working
directory is recorded explicitly, rather than claiming deterministic replay.
"""
    workspace, source = Path(workspace).resolve(), Path(source).resolve()
    if not source.is_relative_to(workspace) or source.suffix != '.py':
        raise ScriptError('SCRIPT_PATH', 'Python 진입 파일은 작업 폴더 안에 있어야 합니다.')
    files, total = {}, 0
    for path in sorted(workspace.rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(workspace) or path.stat().st_nlink != 1:
            raise ScriptError('SCRIPT_PATH', '코드 묶음의 링크는 지원하지 않습니다.')
        raw = path.read_bytes()
        total += len(raw)
        if total > MAX_CODE_BYTES:
            raise ScriptError('SCRIPT_SOURCE_LIMIT', '코드 묶음은 8MiB 이하여야 합니다.')
        relative = path.relative_to(workspace)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(raw)
        os.chmod(target, 0o600)
        files[relative.as_posix()] = digest(raw)
    entry = source.relative_to(workspace).as_posix()
    if entry not in files:
        raise ScriptError('SCRIPT_PATH', '진입 파일이 없습니다.')
    return entry, files


def execute(source, stdin, workspace, **kwargs):
    """An active workspace lease prevents retention cleanup during execution."""
    from filelock import FileLock, Timeout
    root = Path(workspace).resolve().parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = FileLock(str(root / '.execution.lock'))
    check = kwargs.get('check') or (lambda: None)
    until = time.monotonic() + float(kwargs.get('timeout', 300))
    while True:
        check()
        try:
            lock.acquire(timeout=.05)
            break
        except Timeout:
            if time.monotonic() >= until:
                raise ScriptError('SCRIPT_TIMEOUT', '작업 폴더의 실행 잠금 대기 시간이 끝났습니다. 실행하지 않았습니다.')
    try:
        atomic_json(root / 'scope.json', {'protocol': 'file-workspace/1', 'updated': time.time()})
        from python_environment_lock import environment_lease
        with environment_lease(check=check):
            return _execute(source, stdin, workspace, **kwargs)
    finally:
        lock.release()


def _execute(source, stdin, workspace, *, interpreter=None, timeout=300,
            check=None, env=None, parent_execution=None, cwd=None, expected_hashes=None,
            expected_environment=None):
    """One explicit invocation, never retry. Check exceptions are re-raised."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ScriptError('SCRIPT_TIMEOUT_ARGUMENT', 'timeout은 0초 초과 3600초 이하입니다.')
    if not isinstance(strict_json(stdin), dict):
        raise ScriptError('SCRIPT_INPUT', 'stdin은 JSON 객체 하나여야 합니다.')
    workspace = Path(workspace).resolve()
    executions = workspace.parent / 'executions'
    executions.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = executions / uuid.uuid4().hex
    directory.mkdir(mode=0o700)
    entry, hashes = snapshot(source, workspace, directory / 'source')
    if expected_hashes is not None and hashes != expected_hashes:
        raise ScriptError('SCRIPT_SOURCE_CHANGED', '영수증 준비 이후 코드가 바뀌었습니다. 실행하지 않았습니다.')
    (directory / 'stdin.json').write_bytes(stdin)
    os.chmod(directory / 'stdin.json', 0o600)
    interpreter = interpreter or sys.executable
    from python_environment_lock import fingerprint
    environment = fingerprint(workspace)
    if expected_environment is not None and environment != expected_environment:
        raise ScriptError('SCRIPT_ENVIRONMENT_CHANGED', '영수증 준비 이후 Python 환경이 바뀌었습니다. 실행하지 않았습니다.')
    created = time.time()
    meta = {'protocol': PROTOCOL, 'execution_id': directory.name, 'created': created,
            'expires_at': created + RETENTION_SECONDS, 'state': 'prepared',
            'entry': entry, 'source_hashes': hashes, 'stdin_hash': digest(stdin),
            'original_path': str(Path(source).resolve()), 'workspace': str(workspace),
            'cwd': str(Path(cwd or Path(source).resolve().parent).resolve()), 'interpreter': interpreter,
            'python_version': sys.version, 'timeout': timeout, 'parent_execution': parent_execution,
            'environment_fingerprint': environment,
            'external_state_frozen': False}
    atomic_json(directory / 'meta.json', meta)
    child_env = dict(os.environ if env is None else env)
    child_env[RESULT_ENV] = str(directory / 'result.json')
    child_env['PYTHONDONTWRITEBYTECODE'] = '1'
    def started(pid):
        meta.update(state='running', pid=pid)
        atomic_json(directory / 'meta.json', meta)
    try:
        process = run_process([interpreter, str(directory / 'source' / entry)], stdin,
                              cwd=meta['cwd'], env=child_env, timeout=timeout, check=check,
                              stdout_file=directory / 'stdout.log', stderr_file=directory / 'stderr.log',
                              started=started, terminate_descendants=True)
        meta.update(process)
    except BaseException as exc:
        meta.update(state='interrupted', error_type=type(exc).__name__, ended=time.time())
        atomic_json(directory / 'meta.json', meta)
        # The boundary may attach a path, but never puts the raw input in chat.
        if hasattr(exc, 'details'):
            exc.details.update(execution_id=directory.name, record=str(directory))
        raise
    error, value, has_value = None, None, False
    try:
        value = read_result(directory)
        has_value = True
    except ScriptError as exc:
        error = {'code': exc.code, 'message': str(exc)}
    if meta['timed_out']:
        error = {'code': 'SCRIPT_TIMEOUT', 'message': '시간 한도로 프로세스를 중단했습니다. 외부 효과는 되돌리지 않았습니다.'}
    elif meta['exit_code'] != 0:
        error = {'code': 'SCRIPT_EXIT', 'message': f"Script 종료 코드 {meta['exit_code']}. stderr 원문을 확인하세요."}
    meta.update(state='failed' if error else 'completed', ended=time.time(),
                has_value=has_value, error=error)
    for name in ('stdout.log', 'stderr.log', 'result.json'):
        path = directory / name
        if path.is_file() and not path.is_symlink():
            os.chmod(path, 0o600)
    atomic_json(directory / 'meta.json', meta)
    return {'ok': not error, 'value': value, 'has_value': has_value,
            'error': error, 'record': str(directory), 'meta': meta}


def inspect_record(directory):
    """Original input is never reconstructed from a masked display."""
    directory = Path(directory).resolve()
    try:
        meta = strict_json((directory / 'meta.json').read_bytes())
        if meta['protocol'] != PROTOCOL:
            raise ValueError('protocol')
        if time.time() >= meta['expires_at']:
            raise ScriptError('SCRIPT_RECORD_EXPIRED', '원문 보존 기간이 끝났습니다. 마스킹본으로 재현하지 않습니다.')
        for relative, expected in meta['source_hashes'].items():
            path = directory / 'source' / relative
            if not path.resolve().is_relative_to(directory / 'source') or path.is_symlink() or digest(path.read_bytes()) != expected:
                raise ValueError('source fingerprint')
        if digest((directory / 'stdin.json').read_bytes()) != meta['stdin_hash']:
            raise ValueError('stdin fingerprint')
        return meta
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScriptError('SCRIPT_RECORD_INVALID', '실행 기록이 없거나 지문과 일치하지 않습니다.') from exc


def reproduce(directory, *, check=None, env=None):
    """CLI replay is an explicit new attempt, not IBL resume."""
    directory = Path(directory).resolve()
    meta = inspect_record(directory)
    if meta['state'] in ('prepared', 'running'):
        raise ScriptError('SCRIPT_EFFECT_UNCERTAIN', '진행 중이거나 완료 불명인 실행은 재실행하지 않습니다.')
    if meta['state'] == 'interrupted':
        raise ScriptError('SCRIPT_EFFECT_UNCERTAIN', '중단된 실행의 외부 효과를 먼저 확인하세요.')
    # Copy the recorded code to a new private working tree. Never edit evidence.
    root = Path(meta['workspace']).parent / 'reproductions' / uuid.uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    shutil.copytree(directory / 'source', root / 'work')
    result = execute(root / 'work' / meta['entry'], (directory / 'stdin.json').read_bytes(),
                     root / 'work', interpreter=meta['interpreter'], timeout=meta['timeout'],
                     check=check, env=env, parent_execution=meta['execution_id'], cwd=meta['cwd'])
    return result


def _prune_scope(scope, now):
    from filelock import FileLock, Timeout
    deleted = 0
    try:
        with FileLock(str(scope / '.execution.lock'), timeout=0):
            active = False
            for manifest in (scope / 'executions').glob('*/meta.json'):
                directory = manifest.parent
                if manifest.is_symlink() or not directory.resolve().is_relative_to(scope.resolve()):
                    continue
                meta = strict_json(manifest.read_bytes())
                if meta.get('protocol') != PROTOCOL or meta.get('expires_at', now + 1) > now:
                    continue
                if meta.get('state') == 'running':
                    from common.platform_utils import pid_alive
                    if pid_alive(meta.get('pid')):
                        active = True
                        continue
                shutil.rmtree(directory)
                deleted += 1
            marker = scope / 'scope.json'
            if not active and marker.is_file():
                state = strict_json(marker.read_bytes())
                if state.get('protocol') == 'file-workspace/1' and state.get('updated', now) + RETENTION_SECONDS <= now:
                    path = scope / 'work'
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                        deleted += 1
            # Reproductions have independent leases and retention clocks.
            for child in (scope / 'reproductions').glob('*'):
                if child.is_dir() and not child.is_symlink():
                    deleted += _prune_scope(child, now)
    except (Timeout, OSError, ValueError, ScriptError):
        pass
    return deleted


def prune(root, now=None):
    """Periodic cleanup of expired private records; active leases are skipped."""
    import re
    root = Path(root)
    now = time.time() if now is None else now
    if not root.is_dir():
        return 0
    return sum(_prune_scope(scope, now) for scope in root.iterdir()
               if not scope.is_symlink() and scope.is_dir()
               and re.fullmatch('[0-9a-f]{64}', scope.name))
