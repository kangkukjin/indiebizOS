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


def start(command, cwd, *, io='pipe', request_id=None, yield_ms=1000, lifetime='task', db=None, sandbox=True, shell=None):
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
    if not isinstance(command, str) or not command.strip(): raise ValueError('command 필수')
    if io == 'pty' and os.name == 'nt': raise ValueError('로컬 PTY 미지원: resident terminal을 사용하세요')
    from file_changes import attribution, validate_attribution
    owner = attribution()
    validate_attribution({'attribution': owner})
    db = db or store()
    signature = fingerprint({'command': command, 'cwd': cwd, 'io': io, 'lifetime': lifetime, 'owner': owner,
                             **({'shell': shell} if shell is not None else {}),
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
               'state': 'queued', 'capabilities': {'input': True, 'eof': True, 'interrupt': True, 'cancel': True,
                                                'resize': io == 'pty', 'io': io, 'sandbox': sandbox,
                                                'restart_reconnect': True, 'output_retention_bytes': 1048576}}
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
