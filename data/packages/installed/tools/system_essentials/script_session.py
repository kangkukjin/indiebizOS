"""Registered script sessions: one child per IBL execution, typed IPC and cleanup."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
from common.expression_ir import Fault, pack, unpack


def record(handler_file, sid, ok, error=None):
    from common.pkg_utils import load_singleton
    from logging_utils import mask_secrets
    ops = load_singleton(handler_file, 'script_ops')
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    ops._update_state(sid, last_run={'at': now, 'ok': ok, 'protocol': 'ibl-script-session/1'},
                      last_error={'at': now, 'stderr_tail': mask_secrets(error)} if error else None)


class Session:
    def __init__(self, project_path, agent_id, sid, script_path):
        self.project = str(Path(project_path).resolve())
        self.agent_id = agent_id
        self.sid, self.script_path = sid, Path(script_path)
        self.lock = threading.RLock()
        self.closed = False
        self.owner = uuid.uuid4().hex
        self.generation = uuid.uuid4().hex
        self.lease = None
        self.proc = None
        self.responses = queue.Queue()

    def start(self, runtime):
        from python_environment_lock import environment_lease
        from runtime_utils import get_python_cmd, get_base_path
        import boot_paths
        self.lease = environment_lease(check=runtime.check)
        self.lease.__enter__()
        worker = self.script_path
        try:
            self.proc = subprocess.Popen([get_python_cmd(), '-I', str(worker), str(Path(boot_paths.__file__).parent), str(get_base_path() / "pylibs")], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                         cwd=self.project, start_new_session=True, bufsize=1)
        except OSError as exc:
            raise Fault('PY_RUNTIME_UNAVAILABLE', str(exc), kind='protocol') from exc
        def reader():
            try:
                for line in self.proc.stdout:
                    self.responses.put(json.loads(line))
            except Exception as exc:
                self.responses.put({'transport_error': type(exc).__name__})
            finally:
                self.responses.put(None)
        threading.Thread(target=reader, daemon=True).start()  # cc-ok: 실행 소유 워커의 pipe만 읽고 close가 프로세스 종료·EOF를 보장
        self.proc.stdin.write(json.dumps({'protocol': 'ibl-script-session/1', 'owner': self.owner,
                                         'generation': self.generation}) + '\n')
        self.proc.stdin.flush()
        ready = self.wait(runtime, 60)
        if not ready.get('ready') or ready.get('protocol') != 'ibl-script-session/1':
            raise Fault('SCRIPT_PROTOCOL', '등록 스크립트의 세션 프로토콜 응답이 없습니다.', kind='protocol')
        self.environment = ready['environment']

    def wait(self, runtime, timeout):
        deadline = time.monotonic() + float(timeout)
        import psutil
        while True:
            try:
                runtime.check()
                if time.monotonic() > deadline:
                    raise Fault('PY_TIMEOUT', 'Python 호출 시간 한도 초과. 외부 효과는 불명입니다.', kind='budget',
                                details={'stage': 'invoke', 'invoked': True, 'effect_status': 'unknown'})
                if self.proc.poll() is None and psutil.Process(self.proc.pid).memory_info().rss > 1024**3:
                    raise Fault('PY_MEMORY_BUDGET', 'Python 워커 메모리 1GiB 한도 초과.', kind='budget')
                response = self.responses.get(timeout=.05)
                if response is None or 'transport_error' in response:
                    raise Fault('PY_WORKER_LOST', 'Python 워커 연결이 끊겼습니다. 재호출하지 않았으며 효과는 불명입니다.',
                                kind='protocol', details={'invoked': True, 'effect_status': 'unknown'})
                return response
            except queue.Empty:
                continue
            except psutil.NoSuchProcess:
                continue
            except BaseException:
                self.close()
                raise

    def invoke(self, params, runtime, timeout=60):
        from logging_utils import mask_secrets
        with self.lock:
            if self.closed:
                raise Fault('PY_STATE_EXPIRED', '종료한 Python 실행입니다.', kind='protocol')
            if self.proc is None:
                self.start(runtime)
            timeout = params.get('timeout', timeout)
            request = {'id': runtime.local.invocation_id, 'params': pack(params)}
            try:
                self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + '\n')
                self.proc.stdin.flush()
            except (OSError, ValueError) as exc:
                self.close()
                raise Fault('PY_WORKER_LOST', '전송 실패: 효과 불명, 자동 재시도하지 않습니다.', kind='protocol') from exc
            result = self.wait(runtime, timeout)
            # Scrub only diagnostics, never alter the business value.
            if not result['ok']:
                error = result['error']
                details = json.loads(mask_secrets(json.dumps(error['details'], ensure_ascii=False)))
                raise Fault(error['code'], mask_secrets(error['message']), kind=error['kind'],
                            partial=unpack(result['partial']), details=details)
            value = unpack(result['value'])
            evidence = {**result.get('evidence', {}), 'script': {
                'id': self.sid, 'path': str(self.script_path), 'protocol': 'ibl-script-session/1',
                'environment': result['environment'],
                'elapsed_ms': result['elapsed_ms'],
                'diagnostics': mask_secrets(result['diagnostics'])}}
            if result.get('artifact'):
                artifact = result['artifact']
                value = self.write_bytes(artifact, {'path': artifact.get('path')})
            return value, evidence

    def write_bytes(self, payload, options):
        import base64
        from tool_loader import load_tool_handler
        from tool_context import ToolContext
        handler = load_tool_handler('write_file')
        context = ToolContext(self.project, 'write_file', agent_id=self.agent_id)
        path = options.get('path')
        if not isinstance(path, str) or not path:
            raise Fault('PY_EXPORT_PATH', 'bytes export에는 options.path가 필요합니다.')
        resolved = context.resolve_output_path(path, guard=handler._validate_path_in_scope)
        if resolved.get('error'):
            raise Fault('PY_EXPORT_PERMISSION', str(resolved['error']), kind='permission')
        target = handler._red_stage(resolved['path'], for_write=True)
        refusal = handler._red_write_prepare(target)
        if refusal:
            raise Fault('PY_EXPORT_PERMISSION', str(refusal), kind='permission')
        data = base64.b64decode(payload['base64'], validate=True)
        from supervision_bus import current
        from supervision_delivery import _atomic, stage_artifact
        controller = current(self.agent_id)
        if controller and Path(target).resolve().is_relative_to(controller.delivery.public_root):
            with controller.delivery.lock:
                record = stage_artifact(target, data, controller.delivery.public_root,
                                        directory=controller.delivery.directory)
            return {'path': record['staged'], 'target': target, 'bytes': len(data), 'staged': True}
        _atomic(Path(target), data)
        handler._red_write_finalize(target)
        handler._vocab_enforce(target)
        from write_ledger import log_write
        log_write(target, event='write', gate='script_export', size=len(data))
        return {'path': target, 'bytes': len(data), 'saved': True}

    def close(self):
        self.closed = True
        try:
            if self.proc is not None:
                if self.proc.poll() is None:
                    import psutil
                    try:
                        parent = psutil.Process(self.proc.pid)
                        owned = parent.children(recursive=True) + [parent]
                        for process in owned:
                            try:
                                process.terminate()
                            except psutil.NoSuchProcess:
                                pass
                        _, alive = psutil.wait_procs(owned, timeout=1)
                        for process in alive:
                            try:
                                process.kill()
                            except psutil.NoSuchProcess:
                                pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                        # Enumeration may be forbidden even though this Popen
                        # child is ours. Always reap the owned worker itself.
                        if self.proc.poll() is None:
                            self.proc.terminate()
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=2)
                for stream in (self.proc.stdin, self.proc.stdout):
                    if stream:
                        stream.close()
        finally:
            if self.lease is not None:
                self.lease.__exit__(None, None, None)
                self.lease = None
