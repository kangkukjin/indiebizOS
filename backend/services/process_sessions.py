"""Durable process session client shared by tools, task receipts and HTTP."""
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import tempfile
from pathlib import Path

from coding_store import CodingStore, fingerprint, identifier
from code_analysis_scope import check, current_scope
from process_session_worker import write_json, snapshot


def store():
    return CodingStore()


def directory(task_id, db=None):
    if not isinstance(task_id, str) or not task_id.startswith('process_') or not task_id[8:].isalnum():
        raise ValueError('잘못된 process task_id')
    return (db or store()).root / 'processes' / task_id


def start(command, cwd, *, io='pipe', request_id=None, yield_ms=1000, lifetime='task', db=None, sandbox=True, shell=None,
          stdin='open', environment=None, path=None):
    """stdin='closed'는 입력 통로를 닫고 시작한다(pipe 전용). environment='inherit'는 이 프로세스의 환경을
    걸러 내지 않고 물려준다. path는 그 환경의 PATH를 바꾼다. 셋 다 몸의 셸 문(`hold`)이 쓰는 값이고,
    기본값은 지금까지의 세션과 같다."""
    from runtime_utils import expand_body_path
    cwd = str(Path(expand_body_path(cwd)).resolve(strict=True))
    check(cwd, write=True)
    execution = (current_scope() or {}).get('execution')
    if execution:
        if lifetime != 'task' or not sandbox:
            raise PermissionError('수리 프로세스는 작업 수명과 기존 격리를 사용합니다')
        if not Path(cwd).is_relative_to(execution['root']):
            raise PermissionError('실행 문맥 밖 cwd')
    if io not in ('pipe', 'pty') or lifetime not in ('task', 'session'):
        raise ValueError('io=pipe/pty, lifetime=task/session')
    if stdin not in ('open', 'closed') or environment not in (None, 'inherit'):
        raise ValueError('stdin=open/closed, environment=inherit')
    closed = stdin == 'closed' and io == 'pipe'
    if not isinstance(command, str) or not command.strip(): raise ValueError('command 필수')
    if io == 'pty' and os.name == 'nt': raise ValueError('로컬 PTY 미지원: resident terminal을 사용하세요')
    from file_changes import attribution, validate_attribution
    owner = attribution()
    validate_attribution({'attribution': owner})
    db = db or store()
    signature = fingerprint({'command': command, 'cwd': cwd, 'io': io, 'lifetime': lifetime, 'owner': owner,
                             **({'shell': shell} if shell is not None else {}),
                             **({'stdin': 'closed'} if closed else {}),
                             **({'environment': environment} if environment else {}),
                             **({'execution': execution} if execution else {})})
    with db.lock('process-start'):
        if request_id:
            for row in db.list('process_session'):
                if row.get('request_id') == request_id and row.get('attribution') == owner:
                    if row['signature'] != signature: raise ValueError('request_id 충돌')
                    return receipt(row, db, yield_ms)
        from command_preflight import check as precheck, default_argv, blocked, rejection
        argv = default_argv(command, shell)
        with tempfile.TemporaryDirectory(prefix='indiebiz-preflight-') as scratch:
            def inspect(parser, **kwargs):
                from command_preflight import run_parser
                from coding_process import sandbox_command
                return run_parser(sandbox_command(parser, cwd, scratch), **kwargs)
            preflight = precheck(argv, cwd=cwd, runner=inspect if sandbox else None)
        if blocked(preflight):
            return rejection(preflight)
        task_id = identifier('process'); folder = directory(task_id, db)
        folder.mkdir(parents=True, mode=0o700)
        if sandbox and not execution:
            from coding_process import sandbox_command
            argv = sandbox_command(argv, cwd, folder)
        row = {'id': task_id, 'command': command, 'cwd': cwd, 'io': io, 'argv': argv, 'preflight': preflight,
               'lifetime': lifetime, 'attribution': owner, 'request_id': request_id, 'signature': signature,
               'generation': secrets.token_hex(16), 'token': secrets.token_hex(32), 'created_at': time.time(),
               'state': 'queued', 'capabilities': {'input': not closed, 'eof': not closed, 'interrupt': True, 'cancel': True,
                                                'resize': io == 'pty', 'io': io, 'sandbox': sandbox,
                                                'restart_reconnect': True, 'output_retention_bytes': 1048576}}
        if closed:
            row['stdin'] = 'closed'
        if environment:
            row['environment'] = environment
            row['held'] = True     # hold가 시작한 세션 — 끝나면 기록을 거둔다(_forget·_sweep)
            if path:
                row['path'] = str(path)
        if execution:
            row['execution'] = execution
        write_json(folder / 'session.json', row)
        db.save('process_session', {k: v for k, v in row.items() if k != 'token'})
        backend = Path(__file__).resolve().parents[1]
        code = 'import sys; sys.path.insert(0, sys.argv[1]); import boot_paths; from process_session_worker import main; main(sys.argv[2])'
        from runtime_work import service_scope
        with service_scope(), open(folder / 'worker.log', 'ab') as log:
            subprocess.Popen([sys.executable, '-c', code, str(backend), str(folder), '--indiebiz-owned-session'],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                             close_fds=True)
    return receipt(row, db, yield_ms)


def receipt(row, db, yield_ms):
    import task_receipts as T
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = json.loads((directory(row['id'], db) / 'session.json').read_text())
        if current['state'] != 'queued': break
        time.sleep(.02)
    observed = query(row['id'], db=db, wait_ms=min(max(int(yield_ms), 0), 30000))
    return {**T.receipt('process', row['id']), **observed, 'preflight': row.get('preflight'),
            'task_ref': T.ref('process', row['id']), 'accepted': True}


HOLD_OUTPUT_BYTES = 1048576   # 세션이 보존하는 출력과 같은 크기


_USER_SHELL = {}


def user_shell():
    """(셸 이름, PATH) — 사용자가 터미널에서 쓰는 셸과 그 셸이 평소 갖는 PATH. POSIX 전용, 없으면 (None, None).

    CLI 실행자의 자기 셸은 사용자의 셸 환경에서 돌았다(Claude Code는 대화형 셸의 스냅숏, Codex는 로그인 셸).
    백엔드는 앱이 준 좁은 PATH로 뜨므로, 같은 명령이 몸의 셸에서도 같은 도구를 찾게 PATH만 가져온다.
    값은 비밀이 아니라 세션 기록에 남겨도 된다. 프로세스당 한 번 잰다.
    """
    if os.name == 'nt':
        return None, None
    if 'value' not in _USER_SHELL:
        name, found = None, None
        try:
            import pwd
            import re
            executable = pwd.getpwuid(os.getuid()).pw_shell
            if Path(executable).name in ('sh', 'bash', 'zsh'):
                name = Path(executable).name
                # 프로필이 화면에 쓰는 글과 섞이지 않게 표식 사이의 값만 읽는다.
                done = subprocess.run([executable, '-l', '-i', '-c', 'printf "\\n__INDIEBIZ_PATH__%s__END__\\n" "$PATH"'],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      timeout=20, text=True, start_new_session=True)
                match = re.search(r'__INDIEBIZ_PATH__(.*?)__END__', done.stdout, re.S)
                found = match.group(1).strip() if match and match.group(1).strip() else None
        except Exception:
            pass
        _USER_SHELL['value'] = (name, found)
    return _USER_SHELL['value']


def hold(command, cwd, *, timeout=60, shell=None, lifetime='task', request_id=None, user=False, db=None):
    """명령을 몸이 쥐고, 끝나거나 timeout(초)이 지나면 돌아온다. 시간이 지나도 명령은 죽이지 않는다.

    길지 짧을지를 미리 고르지 않게 하는 문이다(docs/BODY_HELD_COMMANDS_DESIGN_2026_11_17.md 4.2).
    돌려주는 것: state, exit_code(끝났으면), stdout·stderr(처음부터 지금까지), task_ref·generation·cursor
    (이어서 `[self:task]`로 볼 손잡이), signs(아직 돌고 있으면 살아 있다는 신호), preflight·diagnostics.
    구문 검사에서 막힌 명령은 start의 거절 봉투를 그대로 돌려준다(accepted 없음).
    입력 통로는 닫고 시작하고, 환경은 걸러 내지 않으며, 샌드박스를 씌우지 않는다 — 지금까지의 동기 실행과
    같은 범위다. 입력을 주고받을 세션은 start를 쓴다. user=True면 셸을 지정하지 않았을 때 사용자의 셸과
    그 PATH로 돈다(CLI 실행자의 자기 셸이 돌던 조건).
    """
    db = db or store()
    path = None
    if user:
        name, path = user_shell()
        shell = shell or name
    value = start(command, cwd, io='pipe', request_id=request_id, yield_ms=0, lifetime=lifetime, db=db,
                  sandbox=False, shell=shell, stdin='closed', environment='inherit', path=path)
    if not value.get('accepted'):
        return value
    task_id, receipt_fields = value['task_ref']['task_id'], {k: value[k] for k in ('task_ref', 'preflight') if k in value}
    deadline = time.monotonic() + max(0.0, float(timeout))
    streams, size, cursor = {'stdout': [], 'stderr': [], 'combined': []}, 0, 0
    while True:
        for row in value.get('output') or []:
            if size < HOLD_OUTPUT_BYTES:
                streams.setdefault(row.get('stream') or 'stdout', []).append(row.get('text', ''))
                size += len(row.get('text', ''))
        cursor = value.get('cursor', cursor)
        active = value['state'] in ('queued', 'running')
        if not active and not value.get('has_more'):
            break
        left = deadline - time.monotonic()
        if active and left <= 0:
            break
        value = query(task_id, db=db, cursor=cursor, limit_bytes=262144,
                      wait_ms=int(min(max(left, 0.0), 30.0) * 1000) if active else 0)
    if not active:
        _forget(task_id, db)   # 결과를 다 돌려준다 — 손잡이를 넘기지 않은 세션은 남길 것이 없다
    _sweep(db)
    return {**receipt_fields, 'state': value['state'], 'exit_code': value.get('exit_code'),
            'generation': value.get('generation'), 'cursor': cursor, 'gap': value.get('gap'),
            'stdout': ''.join(streams['stdout'] + streams['combined']), 'stderr': ''.join(streams['stderr']),
            'truncated': size >= HOLD_OUTPUT_BYTES,
            **({k: value[k] for k in ('signs', 'diagnostics', 'cleanup', 'error') if k in value}),
            'accepted': True}


def _forget(task_id, db):
    """끝난 세션의 기록과 폴더를 지운다. 워커에게 먼저 물러나라고 알린다."""
    folder = directory(task_id, db)
    try:
        meta = json.loads((folder / 'session.json').read_text())
        with socket.create_connection(('127.0.0.1', meta['port']), timeout=1) as conn:
            conn.settimeout(3)
            conn.sendall(json.dumps({'op': 'release', 'generation': meta['generation'], 'token': meta['token']}).encode() + b'\n')
            conn.makefile('rb').readline(65536)
    except (OSError, KeyError, ValueError):
        pass   # 워커가 이미 없으면 지울 것만 남았다
    db.delete('process_session', task_id)
    import shutil
    shutil.rmtree(folder, ignore_errors=True)   # 워커가 아직 파일을 쥔 몸(Windows)에서는 _sweep이 마저 지운다


_SWEEP = {'at': 0.0}
SWEEP_EVERY_S = 600


def _sweep(db, now=None):
    """쥔 명령의 묵은 기록을 거둔다. 손잡이를 넘긴 채(제한 시간에 돌아옴) 끝난 세션은 세션 수명(ttl)만큼
    남겼다가 지우고, 기록 없이 남은 폴더도 지운다. 명령마다 세션이 생기므로 거두지 않으면 끝없이 쌓인다
    (2026-11-17: 재기동마다 쌓인 바이트코드 캐시 111GB가 같은 꼴이었다)."""
    now = time.time() if now is None else now
    if now - _SWEEP['at'] < SWEEP_EVERY_S:
        return 0
    _SWEEP['at'] = now
    removed, known = 0, set()
    for row in db.list('process_session'):
        known.add(row['id'])
        if not row.get('held'):
            continue
        try:
            meta = json.loads((directory(row['id'], db) / 'session.json').read_text())
        except (OSError, ValueError):
            meta = {'ended_at': row.get('created_at', 0)}   # 폴더가 없는 기록 — 볼 것이 남지 않았다
        ended = meta.get('ended_at')
        if ended and now - ended > meta.get('ttl', 86400):
            _forget(row['id'], db)
            known.discard(row['id'])
            removed += 1
    root = db.root / 'processes'
    if root.is_dir():
        import shutil
        for folder in root.iterdir():
            try:
                if folder.is_dir() and folder.name not in known and now - folder.stat().st_mtime > 120:
                    shutil.rmtree(folder, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed


def query(task_id, *, db=None, op='status', **params):
    if str(task_id).startswith('remoteprocess_'):
        import remote_process_sessions as remote
        ref = {'kind': 'remote_process', 'task_id': task_id}
        return remote.status({**ref, '_history_cursor': params.get('cursor'), '_limit_bytes': params.get('limit_bytes')}) if op == 'status' else remote.control(ref, params)
    import principal
    if not principal.is_owner(): raise PermissionError('프로세스 제어는 소유자 전용입니다')
    folder = directory(task_id, db)
    meta = json.loads((folder / 'session.json').read_text())
    check(meta['cwd'], write=op != 'status')
    generation = params.pop('generation', meta['generation'])
    if generation != meta['generation']: raise ValueError('프로세스 generation 불일치')
    try:
        with socket.create_connection(('127.0.0.1', meta['port']), timeout=2) as conn:
            conn.settimeout(35)
            conn.sendall(json.dumps({**params, 'op': op, 'generation': generation, 'token': meta['token']}).encode() + b'\n')
            result = json.loads(conn.makefile('rb').readline(2 * 1024 * 1024))
            if not result.get('success'): raise ValueError(result.get('error'))
            return _execution_feedback(meta, result)
    except (OSError, KeyError):
        if op != 'status':
            raise RuntimeError('delivery_unknown: 실행 소유자 연결 실패. 입력을 새 request_id로 자동 재전송하지 마세요')
        if meta['state'] in ('queued', 'running'):
            meta = {**meta, 'state': 'interrupted'}
        path = folder / 'output.json'
        output = json.loads(path.read_text()) if path.exists() else {'events': [], 'end': 0}
        return _execution_feedback(meta, snapshot(meta, output['events'], output['end'], int(params.get('cursor') or 0),
                        min(int(params.get('limit_bytes') or 65536), 262144)))


def _execution_feedback(meta, result):
    if meta.get('preflight') and result.get('exit_code') is not None:
        from preflight_feedback import execution_result
        result['diagnostics'] = execution_result(meta['preflight'], result['exit_code'],
            ''.join(row.get('text', '') for row in result.get('output', [])))
    return result


def quiesce_workspace(workspace, *, db=None):
    """Publication/discard holds its existing application lock across this call."""
    root = str(Path(workspace).resolve())
    db = db or store()
    for row in db.list('process_session'):
        if (row.get('execution') or {}).get('root') != root:
            continue
        value = query(row['id'], db=db)
        if value['state'] in ('queued', 'running'):
            query(row['id'], db=db, op='control', action='cancel', request_id='publication-stop')
            deadline = time.monotonic() + 8
            while value['state'] in ('queued', 'running') and time.monotonic() < deadline:
                time.sleep(.05)
                value = query(row['id'], db=db, wait_ms=100)
        if (value['state'] in ('queued', 'running')
                or value['state'] == 'interrupted' and value.get('cleanup', {}).get('confirmed') is not True
                or value.get('cleanup', {}).get('confirmed') is False):
            raise RuntimeError('소유 프로세스 종료 미확인: ' + row['id'])


def task_status(ref):
    import task_receipts as T
    value = query(ref['task_id'], cursor=ref.get('_history_cursor'),
                  limit_bytes=ref.get('_limit_bytes'), wait_ms=ref.get('_wait_ms'))
    return T.view(ref, value['state'], progress=value, result=value,
                  error=('exit code: ' + str(value['exit_code'])) if value['state'] == 'failed' else None,
                  accepted_at=value['accepted_at'], ended_at=value.get('ended_at'),
                  history_cursor=value['cursor'], output=value['output'], generation=value['generation'],
                  capabilities=value['capabilities'], gap=value['gap'])


def task_control(ref, params):
    if not params.get('generation'): raise ValueError('control에는 status의 generation이 필요합니다')
    return query(ref['task_id'], op='control', **params)


def task_cancel(ref):
    if ref['task_id'].startswith('remoteprocess_'):
        from remote_process_sessions import cancel
        return cancel(ref)
    if query(ref['task_id'])['state'] in ('queued', 'running'):
        query(ref['task_id'], op='control', action='cancel', request_id='cancel')
    return task_status(ref)
