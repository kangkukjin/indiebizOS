"""Parent-owned nested checks: every child receives a fresh, narrower OS sandbox.

The short-lived socket grants only the enclosing command's workspace/runtime.
It never executes requests in the host without repair_process's sandbox.
"""
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import select
import socket
import socketserver
import subprocess
import threading
import uuid

ADDRESS = 'INDIEBIZ_REPAIR_BRIDGE'
TOKEN = 'INDIEBIZ_REPAIR_BRIDGE_TOKEN'


def request(command, workspace, *, timeout, env, readonly, live_read, check, cwd):
    address = os.environ[ADDRESS]
    payload = {'token': os.environ.get(TOKEN, ''), 'command': command,
               'workspace': str(workspace), 'timeout': timeout,
               'env': dict(os.environ if env is None else env), 'readonly': readonly,
               'live_read': live_read, 'cwd': str(cwd)}
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(address)
        client.sendall(json.dumps(payload).encode() + b'\n')
        client.settimeout(.1)
        chunks = []
        while True:
            if check:
                check()
            try:
                chunk = client.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            chunks.append(chunk)
    result = json.loads(b''.join(chunks))
    if result.get('timeout'):
        raise subprocess.TimeoutExpired(command, timeout, result.get('stdout'), result.get('stderr'))
    if result.get('error'):
        raise PermissionError(result['error'])
    return subprocess.CompletedProcess(command, result['exit_code'], result['stdout'], result['stderr'])


@contextmanager
def serve(workspace, runtime, *, readonly, live_read, check=None, write_scopes=()):
    allowed = Path(runtime if readonly else workspace).resolve()
    runtime = Path(runtime).resolve()
    token = uuid.uuid4().hex
    stopped = threading.Event()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            result = {}
            self.connection.settimeout(5)
            try:
                raw = self.rfile.readline(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError('중첩 검사 요청이 너무 큽니다')
                value = json.loads(raw)
                if not hmac.compare_digest(str(value.get('token', '')), token):
                    raise PermissionError('중첩 검사 소유자가 일치하지 않습니다')
                root = Path(value['workspace']).resolve(strict=True)
                child_readonly = value.get('readonly') is True
                if not child_readonly and not (root.is_relative_to(allowed) or root.is_relative_to(runtime)):
                    raise PermissionError('중첩 검사 작업 공간이 부모 쓰기 범위 밖입니다')
                if root.is_relative_to(allowed / '.git'):
                    raise PermissionError('중첩 검사에서 Git 관리 경로는 쓸 수 없습니다')
                if value.get('live_read') and (not live_read or not child_readonly):
                    raise PermissionError('부모가 운영 읽기 통로를 열지 않았습니다')
                command = value['command']
                if not isinstance(command, list) or not command or any(not isinstance(x, str) for x in command):
                    raise ValueError('중첩 검사 명령은 argv 목록이어야 합니다')
                cwd = Path(value['cwd']).resolve(strict=True)
                if not cwd.is_relative_to(root):
                    raise PermissionError('중첩 검사 cwd가 작업 공간 밖입니다')

                def alive():
                    if check:
                        check()
                    if stopped.is_set() or (select.select([self.connection], [], [], 0)[0]
                            and not self.connection.recv(1, socket.MSG_PEEK)):
                        raise PermissionError('중첩 검사의 부모 실행이 끝났습니다')
                from repair_process import _run_local
                response = _run_local(command, root, timeout=min(float(value['timeout']), 1800),
                                      env=value['env'], readonly=child_readonly,
                                      live_read=bool(value.get('live_read')), check=alive,
                                      cwd=str(cwd), parent=runtime,
                                      write_scopes=(*write_scopes, (str(allowed), str(runtime))))
                result = {'exit_code': response.returncode, 'stdout': response.stdout, 'stderr': response.stderr}
            except subprocess.TimeoutExpired as exc:
                result = {'timeout': True, 'stdout': exc.stdout, 'stderr': exc.stderr}
            except Exception as exc:
                result = {'error': str(exc)}
            try:
                self.wfile.write(json.dumps(result).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

    class Server(socketserver.ThreadingUnixStreamServer):
        block_on_close = True
        daemon_threads = False

    address = runtime / 'checks.sock'
    server = Server(str(address), Handler)
    os.chmod(address, 0o600)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        yield {ADDRESS: str(address), TOKEN: token}
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join()
        address.unlink(missing_ok=True)
