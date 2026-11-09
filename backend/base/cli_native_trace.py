"""Claude JSONL의 알림 대기와 실제 요청 포함을 기존 trajectory에 연결한다.

원문·추론·프롬프트는 복제하지 않는다. API 요청의 base/keep/tail은 알림이 있는
메시지 위치만 복원한다. 관측 실패는 실행을 바꾸지 않으며 coverage에 남긴다.
"""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path


def _notifications(content):
    if isinstance(content, list):
        content = '\n'.join(p.get('text', '') for p in content
                            if isinstance(p, dict) and p.get('type') == 'text')
    if not isinstance(content, str):
        return []
    result = []
    for block in re.findall(r'<task-notification>(.*?)</task-notification>', content, re.S):
        fields = {}
        for tag, key in (('task-id', 'native_task_id'), ('tool-use-id', 'native_tool_use_id'), ('status', 'status')):
            match = re.search(r'<' + tag + r'>([\w.:-]+)</' + tag + r'>', block)
            if match:
                fields[key] = match.group(1)
        if fields.get('native_task_id') and fields.get('status'):
            result.append(fields)
    return result


class ClaudeNativeTrace:
    """한 CLI attempt의 관측. 세션 과거는 조인용이며 현 호출 사건으로 재기록하지 않는다."""

    def __init__(self, config_dir, session_id=None, *, enabled=True):
        self.root = Path(config_dir) / 'projects'
        self.enabled = enabled
        self.started_at = datetime.now(timezone.utc)
        self.session_id = None
        self.path = None
        self.offset = self.line = 0
        self.identity = None
        self.lock = threading.RLock()
        self.notifications = {}
        self.blobs = {}
        self.requests = {}
        self.delivered = set()
        self.counts = {'queued': 0, 'delivered': 0, 'api_requests': 0}
        self.issues = set()
        self.closed = False
        self.partial_row = False
        self.set_session(session_id)

    def set_session(self, session_id):
        # Native IDs, not arbitrary paths from a subprocess.
        if not session_id or not re.fullmatch(r'[a-zA-Z0-9-]+', str(session_id)):
            return
        with self.lock:
            if self.session_id and session_id != self.session_id:
                self.issues.add('session_changed')
                return
            self.session_id = session_id

    def _emit(self, kind, data):
        from episode_logger import record_trajectory_event
        from model_call_context import fields
        record_trajectory_event(kind, {**fields(), 'native_session_id': self.session_id, **data})

    def _key(self, notification):
        return ':'.join((self.session_id or '', notification['native_task_id'],
                         notification.get('native_tool_use_id', ''), notification['status']))

    def _current(self, row):
        try:
            return datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')) >= self.started_at
        except (KeyError, TypeError, ValueError):
            self.issues.add('timestamp_unavailable')
            return False

    def poll(self):
        if not self.enabled or self.closed or not self.session_id:
            return
        with self.lock:
            try:
                if self.path is None:
                    paths = list(self.root.glob(f'*/{self.session_id}.jsonl'))
                    if len(paths) != 1:
                        if paths:
                            self.issues.add('ambiguous_transcript')
                        return
                    self.path = paths[0]
                stat = self.path.stat()
                identity = (stat.st_dev, stat.st_ino)
                if self.identity and (identity != self.identity or stat.st_size < self.offset):
                    self.issues.add('transcript_replaced')
                    self.offset = self.line = 0
                    self.requests.clear()
                    self.blobs.clear()
                self.identity = identity
                with self.path.open('rb') as stream:
                    stream.seek(self.offset)
                    # Snapshot EOF: ongoing writes cannot keep a poll running indefinitely.
                    while stream.tell() < stat.st_size:
                        offset = stream.tell()
                        raw = stream.readline()
                        self.partial_row = not raw.endswith(b'\n')
                        if self.partial_row:
                            break  # Writer has not finished this row; retry next poll.
                        self.offset = stream.tell()
                        self.line += 1
                        try:
                            row = json.loads(raw)
                            if not isinstance(row, dict):
                                raise ValueError('non-object')
                            ref = {'path': str(self.path), 'line': self.line, 'offset': offset,
                                   'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                            self._consume(row, ref)
                        except (ValueError, TypeError, KeyError, AttributeError):
                            self.issues.add('invalid_record')
            except Exception as exc:
                # No raw exception strings: they can contain native prompt fragments.
                self.issues.add('read_error:' + type(exc).__name__)

    def _consume(self, row, ref):
        if row.get('sessionId', self.session_id) != self.session_id:
            self.issues.add('session_mismatch')
            return
        kind = row.get('type')
        if kind == 'queue-operation' and row.get('operation') == 'enqueue':
            for notification in _notifications(row.get('content')):
                key = self._key(notification)
                if key in self.notifications:
                    continue
                data = {**notification, 'notification_id': key,
                        'queued_at': row.get('timestamp'), 'native_ref': ref}
                self.notifications[key] = data
                if self._current(row):
                    self.counts['queued'] += 1
                    self._emit('model.native_notification', data)
        elif kind == 'api-request-blob':
            message = row.get('message') or {}
            # Assistant reasoning/text and tool output are not input-delivery evidence.
            if message.get('role') in ('system', 'user'):
                notices = _notifications(message.get('content'))
                if notices:
                    self.blobs[row['hash']] = (notices, ref)
        elif kind == 'api-request':
            self._request(row, ref)

    def _request(self, row, ref):
        base = row.get('base')
        keep = row.get('keep', 0)
        tail = row.get('tail', [])
        if not isinstance(keep, int) or keep < 0 or not isinstance(tail, list):
            raise ValueError('request shape')
        prior = self.requests.get(base, {})
        if base and base not in self.requests:
            self.issues.add('request_base_unavailable')
        messages = {i: h for i, h in prior.items() if i < keep}
        for i, blob_hash in enumerate(tail, keep):
            if blob_hash in self.blobs:
                messages[i] = blob_hash
        self.requests[row['id']] = messages
        current = self._current(row)
        if current:
            self.counts['api_requests'] += 1
        for blob_hash in messages.values():
            notices, blob_ref = self.blobs[blob_hash]
            for notice in notices:
                key = self._key(notice)
                if key in self.delivered or key not in self.notifications:
                    continue
                self.delivered.add(key)
                if not current:
                    continue
                queued = self.notifications[key]
                self.counts['delivered'] += 1
                self._emit('model.notification_delivery', {
                    **notice, 'notification_id': key,
                    'queued_at': queued['queued_at'], 'included_at': row.get('timestamp'),
                    'request_id': row['id'], 'request_digest': row.get('requestDigest'),
                    'evidence': 'native_api_request', 'native_ref': ref,
                    'notification_ref': queued['native_ref'], 'input_blob_ref': blob_ref,
                })

    def close(self):
        self.poll()
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if not self.enabled:
                self.issues.add('session_persistence_disabled')
            elif not self.path:
                self.issues.add('transcript_unavailable')
            elif not self.counts['api_requests']:
                self.issues.add('api_requests_unavailable')
            if self.partial_row:
                self.issues.add('incomplete_record')
            try:
                self._emit('model.native_observation', {
                    'coverage': 'partial' if self.issues else 'observed',
                    'issues': sorted(self.issues), **self.counts,
                    'native_path': str(self.path) if self.path else None,
                    'read_bytes': self.offset,
                })
            except Exception:
                pass  # Instrumentation must not replace the original CLI outcome.
