"""Bidirectional stdio JSON-RPC with bounded requests and owned process cleanup."""
import json
import queue
import subprocess
import threading
import time
from collections import deque


class LspError(RuntimeError):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.data = code, data


class Client:
    def __init__(self, command, cwd, env=None, spawn=None, on_request=None, on_notice=None):
        from runtime_work import service_scope
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.pending = {}
        self.counter = 0
        self.closed = False
        self.failure = None
        self.logs = deque(maxlen=80)
        self.on_request = on_request or (lambda method, params: None)
        self.on_notice = on_notice or (lambda method, params: None)
        with service_scope(own_processes=True):
            self.process = (spawn or subprocess.Popen)(command, cwd=cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **({} if spawn else {'start_new_session': True}))
            self.reader = threading.Thread(target=self._read, daemon=True, name='lsp-receive')  # cc-ok: close owns process EOF and joins
            self.logger = threading.Thread(target=self._logs, daemon=True, name='lsp-stderr')  # cc-ok: close owns stderr EOF and joins
            self.reader.start()
            self.logger.start()

    def send(self, message):
        body = json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        with self.write_lock:
            if self.failure:
                raise self.failure
            if self.closed:
                raise LspError('LSP_CLOSED', '언어 서버가 종료됐습니다')
            try:
                self.process.stdin.write(f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise LspError('LSP_LOST', '언어 서버 전송 실패') from exc

    def notify(self, method, params=None):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params or {}})

    def request(self, method, params=None, timeout=30, cancelled=None):
        with self.lock:
            self.counter += 1
            rid = self.counter
            target = self.pending[rid] = queue.Queue(maxsize=1)
        try:
            self.send({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params or {}})
            deadline = time.monotonic() + timeout
            while True:
                if cancelled and cancelled() or time.monotonic() >= deadline:
                    self.notify('$/cancelRequest', {'id': rid})
                    raise LspError('LSP_CANCELLED' if cancelled and cancelled() else 'LSP_TIMEOUT',
                                   '언어 서버 요청이 취소됐거나 대기 시간을 초과했습니다')
                try:
                    result = target.get(timeout=min(.1, max(.001, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if isinstance(result, Exception):
                    raise result
                if 'error' in result:
                    error = result['error']
                    raise LspError(error.get('code'), error.get('message', 'LSP 오류'), error.get('data'))
                return result.get('result')
        finally:
            with self.lock:
                self.pending.pop(rid, None)

    def _read(self):
        try:
            stream = self.process.stdout
            while not self.closed:
                headers = {}
                size = 0
                while True:
                    line = stream.readline(8193)
                    if not line:
                        raise EOFError()
                    size += len(line)
                    if size > 16384:
                        raise ValueError('LSP header too large')
                    if line in (b'\r\n', b'\n'):
                        break
                    key, value = line.decode('ascii').split(':', 1)
                    headers[key.lower()] = value.strip()
                length = int(headers['content-length'])
                if not 0 <= length <= 64 * 1024 * 1024:
                    raise ValueError('LSP message exceeds 64MiB')
                chunks, remaining = [], length
                while remaining:
                    chunk = stream.read(remaining)
                    if not chunk:
                        raise EOFError()
                    chunks.append(chunk)
                    remaining -= len(chunk)
                message = json.loads(b''.join(chunks))
                if 'method' in message:
                    if 'id' in message:
                        response = {'jsonrpc': '2.0', 'id': message['id']}
                        try:
                            response['result'] = self.on_request(message['method'], message.get('params') or {})
                        except Exception as exc:
                            response['error'] = {'code': getattr(exc, 'code', -32601), 'message': str(exc)}
                        self.send(response)
                    else:
                        self.on_notice(message['method'], message.get('params') or {})
                else:
                    with self.lock:
                        target = self.pending.get(message.get('id'))
                        if target and target.empty():
                            target.put_nowait(message)
        except Exception as exc:
            self._fail(LspError('LSP_LOST', '언어 서버 연결 종료: ' + str(exc)))

    def _logs(self):
        try:
            for line in iter(self.process.stderr.readline, b''):
                self.logs.append(line.decode('utf-8', errors='replace').rstrip()[:4000])
        except (OSError, ValueError):
            pass

    def _fail(self, error):
        self.failure = error
        with self.lock:
            for target in self.pending.values():
                if target.empty():
                    target.put_nowait(error)

    def close(self, graceful=True):
        if self.closed:
            return
        if graceful and self.process.poll() is None:
            try:
                self.request('shutdown', timeout=1)
                self.notify('exit')
                self.process.wait(timeout=1)
            except (LspError, OSError, subprocess.TimeoutExpired):
                pass
        self.closed = True
        self._fail(LspError('LSP_CLOSED', '언어 서버 종료'))
        import psutil
        try:
            parent = psutil.Process(self.process.pid)
            owned = parent.children(recursive=True) + [parent]
            for proc in owned:
                try:
                    proc.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(owned, timeout=1)
            for proc in alive:
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        self.process.wait(timeout=3)
        for thread in (self.reader, self.logger):
            if thread is not threading.current_thread():
                thread.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
