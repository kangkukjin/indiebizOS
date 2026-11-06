"""Private JSON IPC: Unix socket / Windows named pipe. No pickle or host HTTP."""
import json
import os
import secrets
import shutil
import tempfile
import threading
from multiprocessing.connection import Client, Listener
from pathlib import Path

LIMIT = 16 * 1024 * 1024


class Channel:
    def __init__(self, runtime, dispatch):
        self.dispatch, self.stopped = dispatch, threading.Event()
        self.key = secrets.token_bytes(32)
        self.directory = Path(tempfile.mkdtemp(prefix='iblsp-')).resolve()
        self.family = 'AF_PIPE' if os.name == 'nt' else 'AF_UNIX'
        self.address = r'\\.\pipe\iblsp-' + secrets.token_hex(16) if os.name == 'nt' else str(self.directory / 'rpc')
        self.listener = Listener(self.address, family=self.family, authkey=self.key)
        self.config = Path(runtime) / ('analysis-channel-' + secrets.token_hex(8) + '.json')
        self.config.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'address': self.address, 'family': self.family, 'key': self.key.hex()}, stream)
        from concurrent.futures import ThreadPoolExecutor
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='analysis-ipc')
        self.thread = threading.Thread(target=self.run, daemon=True, name='analysis-channel')  # cc-ok: authenticated wakeup and close own thread
        from runtime_work import service_scope
        with service_scope(own_processes=True):
            self.thread.start()

    def serve(self, conn):
        with conn:
            try:
                if not conn.poll(5):
                    return
                body = json.loads(conn.recv_bytes(LIMIT))
                from runtime_work import scope
                with scope('code-analysis-channel'):
                    result = {'ok': True, 'result': self.dispatch(body)}
            except Exception as exc:
                result = {'ok': False, 'code': str(getattr(exc, 'code', 'REQUEST_FAILED')), 'error': str(exc)}
            try:
                conn.send_bytes(json.dumps(result, ensure_ascii=False).encode())
            except (OSError, EOFError):
                pass

    def run(self):
        while not self.stopped.is_set():
            try:
                conn = self.listener.accept()
                if self.stopped.is_set():
                    conn.close()
                    break
                self.pool.submit(self.serve, conn)  # cc-ok: close owns executor, bounded requests own connections
            except (EOFError, OSError, ValueError, __import__('multiprocessing').AuthenticationError):
                if self.stopped.is_set():
                    break

    def close(self):
        if self.stopped.is_set():
            return
        self.stopped.set()
        try:
            with Client(self.address, family=self.family, authkey=self.key):
                pass
        except (OSError, EOFError):
            pass
        self.listener.close()
        self.thread.join(timeout=5)
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.config.unlink(missing_ok=True)
        shutil.rmtree(self.directory, ignore_errors=True)


def request(config, body, timeout=120):
    value = json.loads(Path(config).read_text())
    with Client(value['address'], family=value['family'], authkey=bytes.fromhex(value['key'])) as conn:
        conn.send_bytes(json.dumps(body, ensure_ascii=False).encode())
        if not conn.poll(timeout):
            raise TimeoutError('코드 작업 공간 응답 시간 초과')
        result = json.loads(conn.recv_bytes(LIMIT))
    if not result.get('ok'):
        raise RuntimeError(result.get('code', '') + ': ' + result.get('error', '요청 실패'))
    return result['result']
