"""Hub-owned Samsung sessions behind the existing authorized script adapter.

Only pinned installed code runs in process. No HTTP entry point, caller-supplied
code, origin assertion or new IBL vocabulary. Unknown sends are never replayed.
"""
from collections import deque
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse

import hardware_registry

IDLE_TTL = 60
MAX_IDLE = 8
DRIVER_SHA256 = '6f4f46b825d1374721565a8e9961e4774611d615cc45d80de14b7e9a89d9858a'
ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "data/scripts/tv_control.py"


def fingerprint(rec):
    return hashlib.sha256(json.dumps([rec['driver'], rec['connection']],
                                    sort_keys=True).encode()).hexdigest()


class Session:
    def __init__(self):
        self.queue = deque()
        self.condition = threading.Condition()
        self.users = 0
        self.remote = None
        self.reader = None
        self.dead = threading.Event()
        self.write_lock = threading.Lock()
        self.fingerprint = None
        self.last_used = time.monotonic()
        self.http = {}
        self.http_lock = threading.Lock()

    @contextmanager
    def turn(self, check):
        ticket = object()
        with self.condition:
            self.queue.append(ticket)
        try:
            while True:
                check()
                with self.condition:
                    if self.queue[0] is ticket:
                        break
                    self.condition.wait(.05)
            yield
        finally:
            with self.condition:
                self.queue.remove(ticket)
                self.condition.notify_all()

    def close_remote(self):
        self.dead.set()
        remote, self.remote = self.remote, None
        if remote:
            # Interrupt the sole reader before joining; never hold manager lock.
            try:
                import socket
                remote.s.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
            remote.close()
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
        self.reader = None

    def close(self):
        self.close_remote()
        with self.http_lock:
            clients, self.http = list(self.http.values()), {}
        for client, lock in clients:
            with lock:
                client.close()

    def connect(self, driver, cfg, sink, check, deadline):
        if self.remote and not self.dead.is_set():
            return
        self.close_remote()
        check()
        remote = driver.Remote(cfg, sink, check=check, deadline=deadline)
        try:
            check()
        except BaseException:
            remote.close()
            raise
        self.remote = remote
        self.dead.clear()
        # Reader outlives the request: no captured request cancellation/deadline.
        remote.check = lambda: self._reader_check()
        send = remote._send
        def locked_send(*args):
            with self.write_lock:
                return send(*args)
        remote._send = locked_send
        def read():
            try:
                while not self.dead.is_set():
                    remote._message(time.monotonic() + 3600)
            except Exception:
                self.dead.set()
        from runtime_work import service_scope
        with service_scope():
            self.reader = threading.Thread(target=read, name='tv-reader', daemon=True)
            self.reader.start()

    def _reader_check(self):
        if self.dead.is_set():
            raise EOFError('TV connection closed')


class Request:
    def __init__(self, manager, session, rec, deadline, check):
        self.manager, self.session, self.rec = manager, session, rec
        self.deadline, self.host_check = deadline, check
        self.sent = []
        self.uncertain = False
        self.changed = False
        self.executing = False

    def check(self):
        self.host_check()
        if self.manager.stopped.is_set():
            raise RuntimeError('TV 서비스가 종료되었습니다')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('TV 전체 실행 시간 초과')
        current = self.manager.store.connection(self.rec['device_id'])
        if self.executing and fingerprint(current) != fingerprint(self.rec):
            raise PermissionError('TV 연결 설정이 변경되었습니다')

    def token_sink(self, token):
        self.manager.store.save_token(self.rec['device_id'], token,
                                      expected_connection=self.rec['connection'])
        expected = {**self.rec['connection'], 'token': str(token)}
        current = self.manager.store.connection(self.rec['device_id'])
        if current['connection'] != expected:
            raise PermissionError('TV 연결 설정이 변경되었습니다')
        self.rec = current
        self.session.fingerprint = fingerprint(current)

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while True:
            self.check()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            self.manager.stopped.wait(min(.05, remaining))

    def before_change(self):
        self.check()
        self.changed = True

    def pair(self, cfg, sink):
        self.session.close_remote()
        self.session.connect(self.manager.driver, {**cfg, 'token': ''}, self.token_sink,
                             self.check, self.deadline)

    def send_keys(self, cfg, keys, sink):
        parsed = self.manager.driver.parse_keys(keys)
        self.check()
        self.session.connect(self.manager.driver, self.rec['connection'], self.token_sink,
                             self.check, self.deadline)
        for key, delay in parsed:
            self.check()
            # Only a known dead connection BEFORE the first command may reconnect.
            if self.session.dead.is_set():
                if self.sent:
                    raise EOFError('TV connection lost during sequence')
                self.session.connect(self.manager.driver, self.rec['connection'], self.token_sink,
                                     self.check, self.deadline)
            self.check()
            self.uncertain = True
            self.session.remote.key(key)
            self.sent.append(key)
            self.uncertain = False
            self.sleep(delay)
        return {'sent': list(self.sent), 'verified': False,
                'message': '리모컨 명령 전달. 실제 화면·음량 변화는 확인되지 않았습니다.'}

    def request(self, url, *, method=None, data=None, headers=None, timeout=4):
        """Per-origin/authentication HTTP pool, no redirects/proxies/retries."""
        import requests
        self.check()
        headers = headers or {}
        parsed = urllib.parse.urlsplit(url)
        key = (parsed.scheme, parsed.netloc,
               hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).digest())
        with self.session.http_lock:
            if key not in self.session.http:
                client = requests.Session()
                client.trust_env = False
                self.session.http[key] = (client, threading.Lock())
            client, lock = self.session.http[key]
        while not lock.acquire(timeout=.05):
            self.check()
        try:
            self.check()
            method = method or ('POST' if data is not None else 'GET')
            if method != 'GET' and 'Get' not in headers.get('SOAPAction', headers.get('Soapaction', '')):
                self.changed = True
            limit = min(timeout, max(.01, self.deadline - time.monotonic()))
            with client.request(method, url, data=data, headers=headers, timeout=limit,
                                allow_redirects=False, stream=True) as response:
                raw = bytearray()
                for part in response.iter_content(16384):
                    self.check()
                    raw.extend(part)
                    if len(raw) > 512 * 1024:
                        raise ValueError('TV 응답 크기 초과')
                if response.status_code >= 300:
                    raise urllib.error.HTTPError('', response.status_code, 'TV HTTP response',
                                                 {}, io.BytesIO(raw))
                return bytes(raw)
        except requests.RequestException:
            raise OSError('TV HTTP connection failed') from None
        finally:
            lock.release()


class Manager:
    def __init__(self, driver, *, store=hardware_registry, ttl=IDLE_TTL, max_idle=MAX_IDLE):
        self.driver, self.store, self.ttl, self.max_idle = driver, store, ttl, max_idle
        self.lock = threading.Lock()
        self.sessions = {}
        self.stopped = threading.Event()
        self.reaper = None

    def start(self):
        from runtime_work import service_scope
        with service_scope():
            self.reaper = threading.Thread(target=self._reap, name='tv-session-reaper', daemon=True)
            self.reaper.start()

    def _reap(self):
        while not self.stopped.wait(1):
            self.sweep()

    def sweep(self):
        # Reserve idle entries before checking disk; no network or joins under lock.
        close = []
        with self.lock:
            idle = sorted(((key, s) for key, s in self.sessions.items() if s.users == 0),
                          key=lambda row: row[1].last_used)
            for index, (key, session) in enumerate(idle):
                stale = time.monotonic() - session.last_used >= self.ttl
                try:
                    stale |= fingerprint(self.store.connection(key)) != session.fingerprint
                except (PermissionError, ValueError, OSError):
                    stale = True
                if stale or index < len(idle) - self.max_idle:
                    close.append(self.sessions.pop(key))
        for session in close:
            session.close()

    def run(self, args, *, timeout, check=lambda: None):
        deadline = time.monotonic() + max(0, timeout)
        if any(k in args for k in ('config', 'ip', 'token', 'base')):
            raise ValueError('연결 설정 대신 등록된 target을 지정하세요')
        rec = self.store.connection(args.get('target'))
        if rec['driver'] != 'samsung-tizen':
            raise ValueError('지원하지 않는 TV 드라이버입니다')
        key = rec['device_id']
        with self.lock:
            if self.stopped.is_set():
                raise RuntimeError('TV 서비스가 종료되었습니다')
            session = self.sessions.setdefault(key, Session())
            session.users += 1
        req = Request(self, session, rec, deadline, check)
        try:
            with session.turn(req.check):
                try:
                    rec = self.store.connection(key)
                    req.rec = rec
                    req.executing = True
                    if session.fingerprint != fingerprint(rec):
                        session.close()
                        session.fingerprint = fingerprint(rec)
                    req.check()
                    token = self.driver._transport.set(req)
                    try:
                        result = self.driver.execute(args, rec['connection'], req.token_sink, ROOT, transport=req)
                    finally:
                        self.driver._transport.reset(token)
                    req.check()
                    if args.get('op') == 'off' or result.get('power') in ('off', 'standby'):
                        session.close_remote()
                    if 'reachable' in result:
                        self.store.observe(key, result['reachable'])
                    return {'success': True, 'target': key, 'op': args.get('op', 'status'), **result}
                except BaseException:
                    session.close()
                    raise
        except Exception as exc:
            # Preserve partial sends even when host cancellation raises its own Fault.
            result = {'success': False, 'verified': False, 'target': key,
                      'op': args.get('op', 'status'), 'sent': req.sent,
                      'unknown': req.uncertain or bool(req.sent) or req.changed,
                      'error': 'TV 실행이 중단되었습니다. 상태를 확인하고 변경 명령은 자동 반복하지 마세요.'}
            if isinstance(exc, (ValueError, PermissionError)):
                result['error'] = str(exc)
            result['timed_out'] = isinstance(exc, TimeoutError)
            return result
        finally:
            with self.lock:
                session.users -= 1
                session.last_used = time.monotonic()
            if self.stopped.is_set():
                session.close()
            self.sweep()

    def close(self):
        self.stopped.set()
        if self.reaper:
            self.reaper.join(timeout=2)
        with self.lock:
            sessions = [s for s in self.sessions.values() if not s.users]
            self.sessions.clear()
        # Active requests observe stop at each I/O/key/wait boundary and close in finally.
        for session in sessions:
            session.close()


_manager = None
_manager_lock = threading.Lock()


def shutdown():
    global _manager
    with _manager_lock:
        manager, _manager = _manager, None
    if manager:
        manager.close()


def registered_process(path, entry, args, *, timeout):
    """Return None only BEFORE invocation to retain the existing process boundary."""
    import os
    import principal
    from thread_context import get_repair_workspace, get_allowed_nodes
    if (os.environ.get('INDIEBIZ_TV_PERSISTENT', '1') != '1' or
            get_repair_workspace() or not principal.is_owner() or get_allowed_nodes() is not None or
            Path(path).resolve() != DRIVER or entry.get('interpreter') != 'python' or
            not isinstance(args, dict) or str(args.get('op', '')).startswith('epg_')):
        return None
    source = DRIVER.read_bytes()
    if hashlib.sha256(source).hexdigest() != DRIVER_SHA256:
        return None
    global _manager
    with _manager_lock:
        if _manager is None:
            spec = importlib.util.spec_from_loader('_installed_tv_driver', loader=None, origin=str(DRIVER))
            driver = importlib.util.module_from_spec(spec)
            driver.__file__ = str(DRIVER)
            # Execute precisely the bytes just verified, never re-open a mutable path.
            exec(compile(source, str(DRIVER), 'exec'), driver.__dict__)
            _manager = Manager(driver)
            _manager.start()
        manager = _manager
    from script_process import check_invocation
    from thread_context import execution_key
    from task_cancellation import requested
    owner, task = execution_key()
    def check():
        if not principal.is_owner() or get_allowed_nodes() is not None:
            raise PermissionError("현재 실행 문맥의 TV 제어 권한이 없습니다")
        check_invocation()
        if requested(owner, task):
            raise RuntimeError('작업 취소')
    try:
        result = manager.run(args, timeout=timeout, check=check)
    except (ValueError, PermissionError):
        result = {'success': False, 'verified': False, 'error': 'TV 등록·실행 권한을 확인하세요.'}
    return {'exit_code': 0, 'stdout': json.dumps(result, ensure_ascii=False),
            'stderr': '', 'timed_out': result.get('timed_out', False)}
