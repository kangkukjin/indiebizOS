"""Detached, authenticated process owner. Backend restarts never adopt a bare PID."""
import base64
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

MAX_OUTPUT = 1024 * 1024
MAX_INPUT = 65536


def write_json(path, value):
    temp = path.with_suffix('.pending')
    with open(temp, 'w', encoding='utf-8') as out:
        os.chmod(temp, 0o600)
        json.dump(value, out, ensure_ascii=False)
        out.flush(); os.fsync(out.fileno())
    os.replace(temp, path)


class Worker:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.meta_path = self.directory / 'session.json'
        self.meta = json.loads(self.meta_path.read_text())
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.events = []
        self.end = 0
        self.requests = {}
        self.stdin_closed = False
        self.cancelled = False
        self.master = None
        self.proc = None
        self.lease = None
        self.stopping = False
        self.execution_stack = None
        self.reaper = None
        self.released = False
        self.input_fd = None
        self.input_bytes = 0
        self.last_output_at = None
        self.cpu_total = None      # 프로세스 무리가 쓴 CPU 초(누적)
        self.cpu_moved_at = None   # 그 값이 마지막으로 늘어난 시각
        self.cpu_sampled_at = 0.0

    def save(self):
        with self.lock:
            write_json(self.meta_path, self.meta)

    def output(self, stream, handle):
        try:
            while True:
                try:
                    data = os.read(handle, 16384)
                except BlockingIOError:
                    import select
                    select.select([handle], [], [], .2)
                    continue
                if not data: break
                with self.condition:
                    self.last_output_at = time.time()
                    self.events.append({'start': self.end, 'stream': stream, 'data': base64.b64encode(data).decode()})
                    self.end += len(data)
                    while self.events and self.end - self.events[0]['start'] > MAX_OUTPUT:
                        self.events.pop(0)
                    write_json(self.directory / 'output.json', {'end': self.end, 'events': self.events})
                    self.condition.notify_all()
        except OSError:
            pass

    def terminate(self, interrupt=False):
        if self.proc is None: return
        if not interrupt:
            from script_process import stop_tree
            with self.lock:
                previous = self.meta.get('cleanup', {})
                result = stop_tree(self.proc, grace=1)
                result['confirmed'] = result['confirmed'] and previous.get('confirmed', True)
                result['diagnostics'] = previous.get('diagnostics', []) + result['diagnostics']
                self.meta['cleanup'] = result
                self.save()
            return
        if os.name == 'nt':
            self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            return
        try:
            pgid = os.tcgetpgrp(self.master) if interrupt and self.master is not None else self.proc.pid
            os.killpg(pgid, signal.SIGINT if interrupt else signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return

    def launch(self):
        command = self.meta['argv']
        if self.meta.get('environment') == 'inherit':
            env = dict(os.environ)
            if self.meta.get('path'):
                env['PATH'] = self.meta['path']
        else:
            env = {k: v for k, v in os.environ.items()
                   if not any(s in k.upper() for s in ('TOKEN', 'API_KEY', 'SECRET', 'PASSWORD'))
                   and not k.startswith(('INDIEBIZ', 'GIT_'))}
            env.update(TMPDIR=str(self.directory), PYTHONDONTWRITEBYTECODE='1', TERM='xterm-256color')
        execution = self.meta.get('execution')
        if execution:
            from contextlib import ExitStack
            import tempfile
            from repair_process import prepare
            self.execution_stack = ExitStack()
            # Unix socket paths have a platform length limit. The worker owns
            # this short runtime for the entire session, including its bridge.
            runtime = Path(tempfile.mkdtemp(prefix='process-run-', dir='/tmp'))
            def cleanup_runtime():
                if self.meta.get('cleanup', {}).get('confirmed') is False:
                    self.meta['runtime_retained'] = str(runtime)
                    self.save()
                else:
                    import shutil
                    shutil.rmtree(runtime)
            self.execution_stack.callback(cleanup_runtime)
            source = dict(os.environ, INDIEBIZ_MODEL_CONFIG_ROOT=execution['repo'])
            command, env = prepare(command, execution['root'], runtime=runtime, env=source,
                                   body=execution['body'], cwd=self.meta['cwd'])
            if execution['body']:
                from repair_process_bridge import serve
                env.update(self.execution_stack.enter_context(serve(
                    execution['root'], runtime, readonly=False, live_read=False)))
        kwargs = {'cwd': self.meta['cwd'], 'env': env, 'bufsize': 0}
        if self.meta['io'] == 'pty':
            if os.name == 'nt': raise ValueError('이 로컬 실행자는 PTY 미지원입니다. Windows resident terminal을 사용하세요')
            import pty
            import fcntl
            import termios
            self.master, slave = pty.openpty()
            def setup():
                os.setsid(); fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            self.proc = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, preexec_fn=setup, **kwargs)
            os.close(slave)
            readers = [('combined', self.master)]
            self.input_fd = self.master
        else:
            kwargs.update({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True})
            # 입력을 주고받지 않는 명령은 입력 통로를 닫고 시작한다 — 입력을 기다리는 프로그램이 곧바로
            # '입력 끝'을 받는다(2026-11-17, 에피소드 6178: 명령에 잘못 든 `cat`이 열린 통로를 19분 기다렸다).
            closed = self.meta.get('stdin') == 'closed'
            self.proc = subprocess.Popen(command, stdin=subprocess.DEVNULL if closed else subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
            readers = [('stdout', self.proc.stdout.fileno()), ('stderr', self.proc.stderr.fileno())]
            if closed:
                self.stdin_closed = True
            else:
                self.input_fd = self.proc.stdin.fileno()
        if self.input_fd is not None:
            os.set_blocking(self.input_fd, False)
        threads = []
        for stream, fd in readers:
            thread = threading.Thread(target=self.output, args=(stream, fd), daemon=True)
            thread.start(); threads.append(thread)
        self.meta.update(state='running', pid=self.proc.pid, started_at=time.time())
        self.save()
        def reap():
            code = self.proc.wait()
            # Close escaped/background descendants before releasing ownership.
            self.terminate()
            for thread in threads: thread.join(timeout=2)
            if self.execution_stack is not None:
                self.execution_stack.close()
            with self.condition:
                self.meta.update(state='cancelled' if self.cancelled else 'succeeded' if code == 0 else 'failed',
                                 exit_code=code, ended_at=time.time())
                self.save(); self.condition.notify_all()
        self.reaper = threading.Thread(target=reap, daemon=True)
        self.reaper.start()

    def snapshot(self, request):
        cursor = int(request.get('cursor') or 0)
        limit = max(1, min(int(request.get('limit_bytes') or 65536), 262144))
        deadline = time.monotonic() + min(max(float(request.get('wait_ms') or 0), 0), 30000) / 1000
        with self.condition:
            while self.end <= cursor and self.meta['state'] == 'running' and time.monotonic() < deadline:
                self.condition.wait(deadline - time.monotonic())
            value = snapshot(self.meta, self.events, self.end, cursor, limit)
            running = self.meta['state'] == 'running'
        if running:
            value['signs'] = self.signs()
        return value

    def sample(self):
        """프로세스 무리가 쓴 CPU 초와 살아 있는 프로세스 이름. 재는 것뿐이고 판정하지 않는다."""
        try:
            import psutil
            root = psutil.Process(self.proc.pid)
            members = [root] + root.children(recursive=True)
        except Exception:
            return None
        total, names = 0.0, []
        for member in members:
            try:
                times = member.cpu_times()
                # 살아 있는 프로세스 자신의 몫 + 이미 끝나 거둔 자식의 몫(OS가 주는 만큼).
                total += times.user + times.system + getattr(times, 'children_user', 0.0) + getattr(times, 'children_system', 0.0)
                names.append(member.name())
            except Exception:
                continue
        now = time.time()
        with self.lock:
            if self.cpu_total is None or total > self.cpu_total + 0.005:
                self.cpu_moved_at = now
            self.cpu_total = total if self.cpu_total is None else max(self.cpu_total, total)
            self.cpu_sampled_at = now
        return list(reversed(names))[:8]

    def signs(self):
        """살아 있다는 신호 — 명령이 일하는 중인지 서 있는지를 가를 사실. 임계값도 판정도 없다."""
        names = self.sample()
        now = time.time()
        started = self.meta.get('started_at') or now
        with self.lock:
            value = {'running_s': round(now - started, 1),
                     'quiet_s': round(now - (self.last_output_at or started), 1),
                     'output_seen': self.last_output_at is not None,
                     'stdin': 'closed' if self.stdin_closed else 'open',
                     'stdin_bytes': self.input_bytes}
            if names is not None:
                value.update(cpu_s=round(self.cpu_total or 0.0, 2),
                             cpu_quiet_s=round(now - (self.cpu_moved_at or started), 1),
                             processes=names)
        return value

    def control(self, request):
        rid = request.get('request_id')
        if not isinstance(rid, str) or not rid or len(rid) > 128:
            raise ValueError('control에는 request_id가 필요합니다')
        action = request.get('action')
        import hashlib
        signature = hashlib.sha256(json.dumps({k: v for k, v in request.items() if k != 'token'}, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if rid in self.requests:
                old = self.requests[rid]
                if old['signature'] != signature: raise ValueError('request_id 충돌')
                return {**old['result'], 'cached': True}
            if len(self.requests) >= 10000: raise ValueError('입력 접수 한도에 도달했습니다')
            if self.meta['state'] != 'running': raise ValueError('종료된 프로세스입니다')
            actor = str(request.get('actor') or 'ai')
            if action != 'cancel' and self.lease and self.lease[0] != actor and self.lease[1] > time.monotonic():
                raise ValueError('다른 작성자가 입력을 제어 중입니다')
            self.lease = (actor, time.monotonic() + 30)
            result = {'accepted': True, 'delivery': 'delivery_unknown', 'request_id': rid}
            self.requests[rid] = {'signature': signature, 'result': result}
            write_json(self.directory / 'requests.json', self.requests)
            if action == 'input':
                if self.stdin_closed: raise ValueError('stdin이 닫혔습니다')
                if ('text' in request) == ('base64' in request): raise ValueError('text 또는 base64 하나가 필요합니다')
                data = base64.b64decode(request['base64'], validate=True) if 'base64' in request else request['text'].encode()
                if request.get('newline'): data += b'\n'
                if len(data) > MAX_INPUT: raise ValueError('입력은 64KiB 이하입니다')
                try:
                    count = os.write(self.input_fd, data)
                    self.input_bytes += count
                    result.update(delivery='delivered' if count == len(data) else 'partial', bytes_written=count)
                except BlockingIOError:
                    result.update(accepted=False, delivery='backpressure', bytes_written=0)
            elif action == 'eof':
                if self.master is not None:
                    os.write(self.master, b'\x04')
                    result.update(delivery='delivered', note='PTY VEOF 전달; 파이프 close와 다릅니다')
                elif self.stdin_closed:
                    result.update(delivery='delivered', note='입력 통로는 이미 닫혀 있습니다')
                else:
                    self.proc.stdin.close(); self.stdin_closed = True
                    result['delivery'] = 'delivered'
            elif action == 'interrupt':
                self.terminate(interrupt=True); result['delivery'] = 'delivered'
            elif action == 'resize':
                if self.master is None: raise ValueError('resize는 PTY 전용입니다')
                import fcntl
                import struct
                import termios
                cols, rows = int(request['cols']), int(request['rows'])
                if not 1 <= cols <= 1000 or not 1 <= rows <= 1000: raise ValueError('터미널 크기 범위: 1~1000')
                fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
                result['delivery'] = 'delivered'
            elif action == 'cancel':
                self.cancelled = True; self.terminate(); result['delivery'] = 'delivered'
            else:
                raise ValueError('control: input/eof/interrupt/resize')
            write_json(self.directory / 'requests.json', self.requests)
            return result

    def handle(self, conn):
        with conn:
            try:
                conn.settimeout(35)
                f = conn.makefile('rb')
                line = f.readline(200000)
                req = json.loads(line)
                import hmac
                if not hmac.compare_digest(str(req.get('token', '')), self.meta['token']):
                    raise PermissionError('프로세스 연결 인증 실패')
                if req.get('generation') != self.meta['generation']: raise ValueError('프로세스 generation 불일치')
                if req['op'] == 'release':
                    # 끝난 명령의 결과를 맡긴 쪽이 다 받았다. 30초를 더 머물지 않는다.
                    if self.meta['state'] == 'running': raise ValueError('실행 중인 프로세스는 놓을 수 없습니다')
                    self.released = True
                    out = {'released': True}
                else:
                    out = self.snapshot(req) if req['op'] == 'status' else self.control(req)
                conn.sendall(json.dumps({'success': True, **out}).encode() + b'\n')
            except Exception as exc:
                conn.sendall(json.dumps({'success': False, 'error': str(exc)}).encode() + b'\n')

    def run(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen(16); listener.settimeout(1)
            self.meta['port'] = listener.getsockname()[1]
            self.launch()
            while True:
                execution = self.meta.get('execution')
                if execution and self.meta['state'] == 'running':
                    cancellation = Path(execution['cancel_path'])
                    stop = cancellation.is_file() and bool(json.loads(cancellation.read_text()))
                    if execution.get('session_path'):
                        path = Path(execution['session_path'])
                        session = json.loads(path.read_text()) if path.exists() else {}
                        stop = stop or session.get('created_at') != execution.get('created_at') or session.get('status') != 'staging'
                    if stop:
                        self.cancelled = True
                        self.terminate()
                binding = self.meta.get('attribution') or {}
                if self.meta.get('lifetime') == 'task' and binding.get('turn_id') and self.meta['state'] == 'running':
                    import sqlite3
                    with sqlite3.connect(binding['db_path'], timeout=1) as conn:
                        turn = conn.execute('SELECT state FROM conversation_turns WHERE id=?', (binding['turn_id'],)).fetchone()
                    if not turn or turn[0] != 'running':
                        self.cancelled = True; self.terminate()
                if time.time() - self.meta['created_at'] > self.meta.get('ttl', 86400) and self.meta['state'] == 'running':
                    self.cancelled = True; self.terminate()
                if self.meta.get('ended_at') and (self.released or time.time() - self.meta['ended_at'] > 30): break
                if self.meta['state'] == 'running' and time.time() - self.cpu_sampled_at >= 2:
                    self.sample()
                try: conn, _ = listener.accept()
                except socket.timeout: continue
                threading.Thread(target=self.handle, args=(conn,), daemon=True).start()
        if self.master is not None: os.close(self.master)


def snapshot(meta, events, end, cursor=0, limit=65536):
    start = events[0]['start'] if events else end
    position = max(cursor, start)
    output = []
    for event in events:
        data = base64.b64decode(event['data'])
        skip = max(0, position - event['start'])
        chunk = data[skip:skip + limit]
        if chunk:
            output.append({'stream': event['stream'], 'base64': base64.b64encode(chunk).decode(),
                           'text': chunk.decode('utf-8', errors='replace'), 'offset': event['start'] + skip})
            position = event['start'] + skip + len(chunk); limit -= len(chunk)
        if limit <= 0: break
    return {'state': meta['state'], 'generation': meta['generation'], 'output': output,
            'cursor': position, 'history_cursor': position, 'has_more': position < end,
            'gap': {'from': cursor, 'to': start} if cursor < start else None,
            'exit_code': meta.get('exit_code'), 'accepted_at': meta['created_at'],
            'ended_at': meta.get('ended_at'), 'capabilities': meta['capabilities'],
            **({k: meta[k] for k in ('cleanup', 'execution', 'error', 'runtime_retained') if k in meta})}


def main(directory):
    worker = Worker(directory)
    try: worker.run()
    except BaseException as exc:
        if worker.proc: worker.terminate()
        if worker.reaper: worker.reaper.join(timeout=5)
        if worker.proc is None:
            worker.meta['cleanup'] = {'confirmed': True, 'diagnostics': []}
        worker.meta.update(state='interrupted' if worker.proc else 'failed', error=str(exc), ended_at=time.time())
        worker.save()
    finally:
        if worker.execution_stack is not None:
            worker.execution_stack.close()
