"""Bounded post-edit LSP feedback. Producers supply paths; delivery owns no writes."""
import contextvars
import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from pathlib import Path

from code_analysis_scope import check, current_scope
from execution_situation import current, fingerprint as json_signature, optional_observation

MAX_FILES = 8
MAX_BYTES = 2 * 1024 * 1024
WAIT_SECONDS = 4


def revision(path):
    path = Path(path)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('automatic diagnostics file size limit')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supported(path):
    from code_analysis_drivers import registry
    return any(Path(path).suffix in spec['extensions'] for spec in registry()['servers'].values())


def root_for(path):
    """Prefer issued copies; never walk above their authority boundary."""
    path = Path(path).resolve()
    scope = check(path)
    if scope:
        return Path(scope['root'])
    from thread_context import get_repair_workspace
    candidate = get_repair_workspace(create=False)
    if candidate and path.is_relative_to(Path(candidate).resolve()):
        return Path(candidate).resolve()
    from code_analysis_drivers import select
    _, spec = select(path)
    for parent in path.parents:
        if (parent / '.git').exists() or any((parent / marker).is_file() for marker in spec.get('markers', [])):
            return parent
    return path.parent


class Feedback:
    def __init__(self, situation=None, store=None):
        self.situation, self.store = situation, store
        self.lock = threading.RLock()
        self.pending, self.seen, self.jobs, self.rows = {}, {}, {}, {}
        self.native = {}
        self.pool = None
        self.closed = threading.Event()
        self.overflow = 0
        self.retries = {}
        self.published = {}

    def mark(self, path, expected=None):
        path = Path(path).resolve()
        if not supported(path):
            return
        root = root_for(path)
        version = revision(path)
        if expected is not None and expected != version:
            return  # The committed bytes have already been superseded.
        from thread_context import snapshot
        with self.lock:
            if self.closed.is_set() or self.seen.get(str(path), object()) == version:
                return
            if str(path) not in self.pending and len(self.pending) >= 64:
                self.overflow += 1
                return
            self.seen[str(path)] = version
            self.retries[str(path)] = 0
            self.pending[str(path)] = (root, version, contextvars.copy_context(), snapshot())

    def query(self, path, entry):
        root, version, context, snapshot = entry

        def run():
            from thread_context import restore, snapshot as take_snapshot
            prior = take_snapshot()
            restore(snapshot)
            try:
                if self.closed.is_set():
                    return None
                check(path)
                if revision(path) != version:
                    return {'path': path, 'status': 'stale', 'document_hash': version}
                if version is None:
                    return {'path': path, 'status': 'deleted', 'document_hash': None, 'items': []}
                from coding_store import CodingStore, fingerprint
                from code_analysis import manager
                from file_changes import identity
                if self.store is None:
                    self.store = CodingStore()
                app = manager(self.store)
                key = fingerprint([str(root), self.situation.task if self.situation else id(self), current_scope()])[:32]
                row = {'id': 'autodiag_' + key, 'path': str(root), 'mode': 'inspect', 'root_identity': identity(root)}
                with self.lock:
                    self.rows[row['id']] = (app, row)
                result = app.query(row, {'analysis': 'diagnostics', 'path': str(Path(path).relative_to(root)),
                                         'wait': 2, 'limit': 100}, cancelled=self.closed.is_set)
                state = result['diagnostics']['files'][0]
                status = state['status']
                if revision(path) != version or result['analysis']['status'] == 'stale':
                    status = 'stale'
                # Preserve original diagnostics in evidence; the model gets a bounded excerpt.
                return {'path': path, 'document_hash': version, 'status': status,
                        'server': result['analysis']['server'], 'generation': result['analysis']['generation'],
                        'document_version': state['document_version'], 'diagnostic_version': state['diagnostic_version'],
                        'total': result['total'], 'items': result['items'],
                        **({'full_result': result['full_result']} if result.get('full_result') else {}),
                        'project_graph_confirmed': False}
            except Exception as exc:
                return {'path': path, 'document_hash': version, 'status': 'unavailable',
                        'error': str(exc)[:400], 'error_code': str(getattr(exc, 'code', type(exc).__name__))}
            finally:
                restore(prior)
                if self.closed.is_set():
                    self.close_views()
        return context.run(run)

    @optional_observation
    def flush(self, wait=WAIT_SECONDS):
        """One total wait budget, including cold start; late results wait for a later boundary."""
        with self.lock:
            if self.closed.is_set():
                return []
            for path, entry in list(self.pending.items())[:MAX_FILES]:
                if path in self.jobs:
                    continue
                self.pending.pop(path)
                if self.pool is None:
                    self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='code-diagnostics')
                from runtime_work import service_scope
                with service_scope(own_processes=True):
                    future = self.pool.submit(self.query, path, entry)  # cc-ok: close cancels queued work; LSP requests are bounded
                self.jobs[path] = (future, entry)
            jobs = list(self.jobs.items())
        deadline = time.monotonic() + wait
        delivered = []
        for path, (future, entry) in jobs:
            version = entry[1]
            try:
                value = future.result(timeout=max(0, deadline - time.monotonic()))
            except TimeoutError:
                value = {'path': path, 'status': 'pending', 'document_hash': version}
            if future.done():
                with self.lock:
                    if self.jobs.get(path, (None,))[0] is not future:
                        continue
                    self.jobs.pop(path, None)
                    if (value and value['status'] in ('pending', 'stale', 'version_unconfirmed') and self.seen.get(path) == version
                            and self.retries.get(path, 0) < 2):
                        self.pending.setdefault(path, entry)
                        self.retries[path] = self.retries.get(path, 0) + 1
            if value is None or self.closed.is_set():
                continue
            if self.seen.get(path) != version:
                continue
            if value['status'] not in ('pending', 'unavailable', 'deleted') and revision(path) != version:
                value = {**value, 'status': 'stale'}
            delivered.append(self.publish(value))
        return delivered

    def publish(self, value):
        full = dict(value)
        items = value.get('items', [])
        summary = {**value, 'items': [{k: item[k] for k in ('message', 'severity', 'code', 'range', 'source') if k in item}
                                      for item in items[:8]],
                   'automatic': True, 'scope': 'changed_file',
                   'note': '진단은 관측한 파일 판본에 한정. pending/stale/version_unconfirmed/unavailable은 오류 0건이 아님.'}
        for item in summary['items']:
            if isinstance(item.get('message'), str):
                item['message'] = item['message'][:400]
        summary['omitted'] = max(0, value.get('total', len(items)) - len(summary['items']))
        summary['queued_files'] = len(self.pending)
        summary['unobserved_files'] = self.overflow
        if self.situation:
            signature = json_signature(value)
            if self.published.get(value['path']) == signature:
                return summary
            self.published[value['path']] = signature
            evidence = self.situation.evidence(full)
            inline = {k: summary[k] for k in ('status', 'server', 'total', 'automatic', 'scope', 'error_code') if k in summary}
            inline['items'] = []
            for item in summary['items']:
                small = dict(item)
                if 'message' in small:
                    small['message'] = small['message'].encode()[:160].decode(errors='ignore')
                inline['items'].append(small)
                if len(json.dumps(inline, ensure_ascii=False).encode()) > 550:
                    inline['items'].pop()
                    break
            inline['omitted'] = max(0, value.get('total', len(items)) - len(inline['items']))
            self.situation.observe({'kind': 'code_file', 'path': value['path']}, 'diagnostics', inline,
                source='lsp_after_edit', source_ref=evidence, subject_revision=value['document_hash'],
                observed_at=time.time())
        return summary

    def close_views(self):
        with self.lock:
            rows = list(self.rows.values())
        for app, row in rows:
            app.close_view(row['id'])

    @optional_observation
    def close(self):
        self.closed.set()
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)
        self.close_views()


def feedback(situation):
    with situation.lock:
        if not hasattr(situation, 'code_feedback'):
            situation.code_feedback = Feedback(situation)
        return situation.code_feedback


def native_path(situation, path):
    if not isinstance(path, str) or not path:
        return None
    target = Path(path)
    if not target.is_absolute():
        from execution_turn import current as turn, resolve_session
        from thread_context import get_current_agent_id
        binding = turn() or resolve_session(get_current_agent_id(), situation.task)
        root = getattr(binding.runner, 'project_path', None)
        if not root or not Path(root).is_absolute():
            return None
        target = Path(root) / target
    return str(target.resolve())


def observe(situation, event, **data):
    if event == 'command_started':
        return snapshot_sources(data['root'])
    if event == 'command_finished':
        from code_analysis_scope import bind
        with bind(data['root']):
            after = snapshot_sources(data['root'])
            before = data['observation']
            for path in before.keys() | after.keys():
                if before.get(path) != after.get(path):
                    feedback(situation).mark(path)
    elif event == 'file_committed':
        if supported(data['path']):
            feedback(situation).mark(data['path'], data.get('revision'))
    elif event == 'tool_started':
        # Exact native file destinations only. Do not parse shell text into claimed writes.
        name, payload = data['name'].split('__')[-1], data['payload']
        if name in ('Edit', 'Write', 'MultiEdit') and isinstance(payload, dict):
            path = native_path(situation, payload.get('file_path'))
            if path and supported(path):
                check(path)
                feedback(situation).native.setdefault(data['key'], (path, revision(path)))
    elif event == 'tool_finished' and data['name'] == 'apply_patch' and not data.get('unknown'):
        # Codex supplies structured file-change receipts; no patch/shell text heuristics.
        payload = data.get('payload') or {}
        for change in payload.get('changes', []) if isinstance(payload, dict) else []:
            path = native_path(situation, change.get('path')) if isinstance(change, dict) else None
            if path and supported(path):
                feedback(situation).mark(path)
    elif hasattr(situation, 'code_feedback'):
        state = situation.code_feedback
        if event == 'tool_finished':
            previous = state.native.pop(data['key'], None)
            if previous and revision(previous[0]) != previous[1]:
                state.mark(previous[0])
        elif event == 'prepare':
            state.flush()
        elif event == 'close':
            state.close()


def snapshot_sources(root):
    """Bounded command observation, only inside an explicitly issued workspace."""
    check(root)
    root = Path(root).resolve()
    from code_analysis_drivers import registry
    extensions = {ext for spec in registry()['servers'].values() for ext in spec['extensions']}
    # Git identifies changed and untracked sources without hashing every tracked source.
    dirty = subprocess.run(['git', '-C', str(root), 'diff', '--relative', '--name-only', '-z', 'HEAD', '--', '.'],
                           capture_output=True, timeout=2)
    if dirty.returncode == 0:
        untracked = subprocess.run(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard', '-z'],
                                  capture_output=True, timeout=2, check=True)
        paths = {root / os.fsdecode(p) for p in (dirty.stdout + untracked.stdout).split(b'\0') if p}
        paths = {p for p in paths if p.suffix in extensions and p.resolve().is_relative_to(root) and not p.is_symlink()}
        if len(paths) > 128:
            raise ValueError('automatic diagnostics changed-file limit')
        return {str(p): revision(p) for p in paths}
    found = {}
    count = 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('.git', '.venv', 'node_modules', '__pycache__', '_backups')
                   and not (Path(folder) / d).is_symlink()]
        for name in files:
            count += 1
            if count > 10000:
                raise ValueError('automatic diagnostics workspace scan limit')
            path = Path(folder) / name
            if path.suffix in extensions and not path.is_symlink():
                stat = path.stat()
                found[str(path)] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    return found


@contextmanager
def command_changes(root, state=None):
    """Observe actual file changes, including writes before a failing command exits."""
    situation = current()
    state = state or (feedback(situation) if situation else None)
    before = None
    if state:
        try:
            before = snapshot_sources(root)
        except Exception:
            pass
    try:
        yield state
    finally:
        if state and before is not None:
            try:
                after = snapshot_sources(root)
                for path in before.keys() | after.keys():
                    if before.get(path) != after.get(path):
                        from code_analysis_scope import bind
                        with bind(root):
                            state.mark(path)
            except Exception:
                pass  # The executed command's result is never replaced by observation failure.
