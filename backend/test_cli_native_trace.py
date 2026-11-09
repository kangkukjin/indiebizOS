"""Native queue ≠ model input; preserve that distinction across resume and retries."""
import json
from datetime import datetime, timezone

import boot_paths  # noqa: F401
import pytest

from cli_native_trace import ClaudeNativeTrace

SESSION = 'a1b2-c3d4'
QUEUED = '2026-11-08T23:40:02.506Z'
INCLUDED = '2026-11-08T23:41:33.790Z'
NOTICE = ('<task-notification><task-id>task-1</task-id><tool-use-id>tool-1</tool-use-id>'
          '<status>killed</status><summary>private text must stay in source</summary>'
          '</task-notification>')


def enqueue(notice=NOTICE, timestamp=QUEUED):
    return dict(type='queue-operation', operation='enqueue', content=notice,
                timestamp=timestamp, sessionId=SESSION)


def blob(content=NOTICE, role='system', hash='blob-1'):
    return dict(type='api-request-blob', hash=hash,
                message=dict(role=role, content=[dict(type='text', text=content)]))


def request(id='request-1', base=None, keep=0, tail=None, timestamp=INCLUDED):
    return dict(type='api-request', id=id, base=base, keep=keep,
                tail=['blob-1'] if tail is None else tail, timestamp=timestamp,
                sessionId=SESSION, requestDigest='digest')


@pytest.fixture
def trace(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda k, d: events.append((k, d)))
    directory = tmp_path / 'projects' / 'project'
    directory.mkdir(parents=True)
    path = directory / f'{SESSION}.jsonl'
    path.touch()
    observer = ClaudeNativeTrace(tmp_path, SESSION)
    observer.started_at = datetime(2026, 11, 8, tzinfo=timezone.utc)
    return observer, path, events


def append(path, *rows):
    with path.open('a') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')


def test_queue_and_attachment_are_not_delivery(trace):
    observer, path, events = trace
    append(path, enqueue(), dict(type='attachment', timestamp=QUEUED,
                                attachment=dict(type='queued_command', prompt=NOTICE)),
           dict(type='queue-operation', operation='remove', reason='absorbed_mid_turn'), blob())
    observer.poll()
    assert [k for k, d in events] == ['model.native_notification']
    append(path, request())
    observer.poll()
    queued, delivered = [d for k, d in events]
    assert delivered['notification_id'] == queued['notification_id']
    assert delivered['queued_at'] == QUEUED and delivered['included_at'] == INCLUDED
    assert delivered['request_id'] == 'request-1'
    # Follow the byte reference back to exactly the request, without copying its body.
    ref = delivered['native_ref']
    with path.open('rb') as stream:
        stream.seek(ref['offset'])
        assert json.loads(stream.read(ref['bytes']))['id'] == 'request-1'
    assert 'private text' not in json.dumps(events)
    observer.close()
    assert events[-1][1]['coverage'] == 'observed'


def test_retry_and_resume_do_not_replay_historical_events(trace):
    observer, path, events = trace
    append(path, enqueue(), blob(), request(),
           request('retry', base='request-1', keep=1, tail=[]))
    observer.poll()
    observer.poll()
    assert [k for k, d in events].count('model.notification_delivery') == 1
    events.clear()
    resumed = ClaudeNativeTrace(path.parents[2], SESSION)
    resumed.started_at = datetime(2026, 11, 9, tzinfo=timezone.utc)
    append(path, request('resume', base='retry', keep=1, tail=[], timestamp='2026-11-09T01:00:00Z'))
    resumed.poll()
    assert not events


def test_retained_input_and_compacted_input_follow_keep(trace):
    observer, path, events = trace
    # Input blob alone is not delivery. A retained blob must still join the native queue.
    append(path, blob(), request(), enqueue(),
           request('kept', base='request-1', keep=1, tail=[]))
    observer.poll()
    assert events[-1][1]['request_id'] == 'kept'
    assert len(events) == 2
    # Removing the message prevents a false delivery for a later queue.
    observer.notifications.clear()
    observer.delivered.clear()
    events.clear()
    append(path, enqueue(), request('compacted', base='kept', keep=0, tail=[]))
    observer.poll()
    assert [k for k, d in events] == ['model.native_notification']


def test_partial_write_malformed_record_and_foreign_session(trace):
    observer, path, events = trace
    raw = json.dumps(enqueue())
    path.write_text('not json\n' + raw[:40])
    observer.poll()
    assert not events
    with path.open('a') as stream:
        stream.write(raw[40:] + '\n')
    append(path, {**enqueue(), 'sessionId': 'other'}, blob(), request())
    observer.close()
    assert [k for k, d in events][:2] == ['model.native_notification', 'model.notification_delivery']
    assert events[-1][1]['issues'] == ['invalid_record', 'session_mismatch']


def test_no_delivery_from_assistant_or_tool_output(trace):
    observer, path, events = trace
    append(path, enqueue(), blob(role='assistant'),
           dict(type='api-request-blob', hash='tool-output', message=dict(role='user', content=[
               dict(type='tool_result', content=NOTICE)])), request(tail=['blob-1', 'tool-output']))
    observer.poll()
    assert [k for k, d in events] == ['model.native_notification']


@pytest.mark.parametrize('enabled', [True, False])
def test_missing_observation_is_explicit(tmp_path, monkeypatch, enabled):
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda k, d: events.append(d))
    observer = ClaudeNativeTrace(tmp_path, SESSION, enabled=enabled)
    observer.close()
    observer.close()
    assert len(events) == 1 and events[0]['coverage'] == 'partial'
    expected = 'transcript_unavailable' if enabled else 'session_persistence_disabled'
    assert expected in events[0]['issues']


def test_replaced_transcript_preserves_dedup_and_reports_gap(trace):
    observer, path, events = trace
    append(path, enqueue(), blob(), request())
    observer.poll()
    path.unlink()
    append(path, enqueue())
    observer.close()
    assert len([k for k, d in events if k == 'model.native_notification']) == 1
    assert 'transcript_replaced' in events[-1][1]['issues']


def test_watch_observes_silent_cli_in_the_invoking_context(trace):
    import contextvars
    import threading
    from types import SimpleNamespace
    from cli_lifecycle import CliWatch

    observer, path, events = trace
    seen = threading.Event()
    identity = contextvars.ContextVar('test_identity', default=None)
    identity.set('owned-call')
    original = observer._emit

    def emit(kind, data):
        assert identity.get() == 'owned-call'
        original(kind, data)
        seen.set()

    observer._emit = emit
    provider = SimpleNamespace(STATE_PREFIX='test', STREAM_IDLE_POLL_SEC=.01,
                               STREAM_IDLE_TIMEOUT_SEC=60, _completion_channel='native-trace-test')
    watch = CliWatch(provider, SimpleNamespace(poll=lambda: None), None, observation=observer)
    try:
        append(path, enqueue())
        assert seen.wait(2), 'No stdout was emitted; the existing watch must still collect the queue.'
    finally:
        watch.close()


def test_stream_attempt_binds_session_and_flushes_native_evidence(trace, monkeypatch):
    from test_cli_stream_deadline import _FakeCli, _make

    observer, path, events = trace
    observer.session_id = None
    append(path, enqueue(), blob(), request())

    class NativeCli(_FakeCli):
        CHILD_CODE = ('import json; print(json.dumps(' + repr(dict(
            type='text', content='done', session_id=SESSION)) + '))')

        def _start_native_observation(self, env, resume_session_id):
            return observer

    output = list(_make(NativeCli).process_message_stream('test', history=[]))
    assert any(e.get('content') == 'done' for e in output)
    assert observer.closed and observer.session_id == SESSION
    delivered = [d for k, d in events if k == 'model.notification_delivery']
    assert len(delivered) == 1 and delivered[0]['native_task_id'] == 'task-1'
    assert delivered[0]['call_id']  # Same provider call identity as the normal trajectory.


def test_incomplete_final_record_does_not_claim_full_coverage(trace):
    observer, path, events = trace
    append(path, request(tail=[]))
    with path.open('a') as stream:
        stream.write('{"type":')
    observer.close()
    assert events[-1][1]['issues'] == ['incomplete_record']
