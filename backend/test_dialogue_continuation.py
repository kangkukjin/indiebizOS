"""조향의 종료 경합·CLI/API 후속·취소·예산·실패 인계 계약."""
import boot_paths  # noqa: F401
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import steer_inbox as inbox
from dialogue_continuation import stream


@pytest.fixture(autouse=True)
def isolated_steering(monkeypatch):
    import steer_inbox
    for name in ('_inbox', '_active', '_journals', '_delivered', '_held'):
        monkeypatch.setattr(steer_inbox, name, {})
    monkeypatch.setattr(steer_inbox, '_sealed', set())


class Journal:
    def __init__(self):
        self.events = []

    def record(self, kind, data):
        self.events.append((kind, data))

    def recovery(self):
        return ""

    def observe(self, event):
        pass

    def finish(self, success, response):
        self.record("finished", {"success": success})


@pytest.mark.parametrize('native', [False, True])
def test_final_text_and_native_tools_continue_before_single_final(native):
    journal, requests = Journal(), []

    def execute(message, history):
        requests.append((message, history))
        if len(requests) == 1:
            if native:
                yield {"type": "tool_start", "id": "bash", "name": "Bash", "input": {"command": "read"}}
                yield {"type": "tool_result", "id": "bash", "name": "Bash", "result": "existing result"}
            yield {"type": "text", "content": "old answer"}
            inbox.post("agent", "A사를 빼줘", "task", require_active=True)
            yield {"type": "final", "content": "old answer"}
        else:
            assert 'A사를 빼줘' in message
            assert history[-1]['content'] == 'old answer'
            if native:
                assert 'existing result' in history[-2]['content']
            yield {"type": "final", "content": "updated answer"}
        yield {"type": "_turn_meta", "tool_calls": [{"segment": len(requests)}], "turn_tokens": 10*len(requests)}

    with inbox.task_scope(["agent"], "task", journal.record):
        events = list(stream(execute, '원래 목표', [], 'agent', 'task', journal))
        with pytest.raises(ValueError, match='확정'):
            inbox.post('agent', 'too late', 'task', require_active=True)
    assert [e['content'] for e in events if e['type'] == 'final'] == ['updated answer']
    assert len(requests) == 2
    assert events[-1]['turn_tokens'] == 20
    assert len(events[-1]['tool_calls']) == 2
    assert any(k == 'steer.completed' for k, _ in journal.events)


@pytest.mark.parametrize('mode', ['cancel', 'error', 'exception', 'budget'])
def test_pending_survives_unsuccessful_exit_without_relaunch(mode, monkeypatch):
    journal, calls = Journal(), []
    cancelled = threading.Event()
    if mode == 'budget':
        monkeypatch.setattr('providers.base.turn_limit_reason', lambda: {'kind': 'task_budget', 'reason': '예산'})

    def execute(message, history):
        calls.append(message)
        inbox.post('stop', '미처리 지시', mode, require_active=True)
        if mode == 'cancel':
            cancelled.set()
        if mode == 'exception':
            raise RuntimeError('worker died')
        if mode == 'error':
            yield {'type': 'error', 'content': 'failed'}
        else:
            yield {'type': 'final', 'content': 'draft'}

    with inbox.task_scope(['stop'], mode, journal.record):
        if mode == 'exception':
            with pytest.raises(RuntimeError):
                list(stream(execute, 'start', [], 'stop', mode, journal, cancelled.is_set))
        else:
            list(stream(execute, 'start', [], 'stop', mode, journal, cancelled.is_set))
    assert len(calls) == 1
    assert any(k == 'steer.held' for k, _ in journal.events)
    assert not any(k == 'steer.completed' for k, _ in journal.events)
    assert any(k == 'steer.accepted' and row['instruction'] == '미처리 지시'
               for k, row in journal.events)
    assert inbox.drain('stop', mode) == []  # 영속 인계와 메모리 재배달이 중복되지 않는다.


def test_post_and_seal_race_never_accepts_and_loses():
    for i in range(30):
        task, barrier = f'race-{i}', threading.Barrier(2)
        with inbox.task_scope(['race'], task):
            def post():
                barrier.wait()
                try:
                    inbox.post('race', 'change', task, require_active=True)
                    return True
                except ValueError:
                    return False

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(post)
                barrier.wait()
                taken = inbox.take_or_seal('race', task)
                accepted = future.result()
            assert (accepted, taken) in [(True, ['change']), (False, [])]


def test_journal_failure_does_not_acknowledge_or_drop_existing_input():
    def broken(kind, data):
        raise OSError('disk full')

    with inbox.task_scope(['disk'], 'failure', broken):
        with pytest.raises(ValueError, match="접수하지 않았습니다"):
            inbox.post('disk', 'not accepted', 'failure', require_active=True)
        assert inbox.drain('disk', 'failure') == []


def test_generator_close_preserves_input():
    journal = Journal()

    def execute(message, history):
        inbox.post('close', 'later', 'closed', require_active=True)
        yield {'type': 'text', 'content': 'streaming'}
        yield {'type': 'final', 'content': 'unused'}

    with inbox.task_scope(['close'], 'closed', journal.record):
        gen = stream(execute, 'start', [], 'close', 'closed', journal)
        next(gen)
        gen.close()
    assert any(k == 'steer.held' for k, _ in journal.events)
    assert any(k == 'steer.accepted' and row['instruction'] == 'later' for k, row in journal.events)
    assert inbox.drain('close', 'closed') == []


def test_real_cli_subprocess_followup_uses_captured_session(monkeypatch):
    """IBL을 한 번도 부르지 않은 CLI 자식의 최종 출력 중 접수→저장 세션 재개."""
    from types import SimpleNamespace
    from test_cli_stream_deadline import _FakeCli, _make

    invocations, mapping = [], {}

    class ImmediateCli(_FakeCli):
        CHILD_CODE = ("import json,sys; text=sys.stdin.read(); "
                      "print(json.dumps({'session_id':'captured-session','type':'text','content':text}))")

        def _build_command(self, **kwargs):
            invocations.append(kwargs)
            return super()._build_command(**kwargs)

    provider = _make(ImmediateCli, disable_session_persistence=False)
    provider.SESSION_STORE = SimpleNamespace(
        load_map=lambda: dict(mapping), load_sizes=lambda: {},
        clear_agent=lambda key: mapping.pop(key, None), clear_size=lambda key: None,
        record_size=lambda *args: None, save_map=lambda value: mapping.update(value))
    monkeypatch.setattr(provider, '_get_session_key', lambda: 'cli-worker')
    journal = Journal()

    def execute(message, history):
        for event in provider.process_message_stream(message, history=history):
            if event['type'] == 'text' and len(invocations) == 1:
                inbox.post('cli', 'A사를 제외해', 'native', require_active=True)
            yield event

    with inbox.task_scope(['cli'], 'native', journal.record):
        events = list(stream(execute, '회사 비교', [], 'cli', 'native', journal))
    assert [i['resume_session_id'] for i in invocations] == [None, 'captured-session']
    finals = [e['content'] for e in events if e['type'] == 'final']
    assert len(finals) == 1 and 'A사를 제외해' in finals[0]
    assert any(k == 'steer.completed' for k, _ in journal.events)


from test_episode3388_repairs import isolated  # noqa: E402,F401


def test_pipeline_handles_steering_after_model_final_and_preserves_history(tmp_path, monkeypatch, isolated):
    """실제 인지 본문/최종 판정/뒷정리를 통과해 단일 확정 응답으로 닫힌다."""
    from types import SimpleNamespace
    from test_episode3388_repairs import Runner
    import thread_context as tc
    import conversation_sessions as sessions
    import sqlite3

    path = tmp_path / 'conversation.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    store = sessions.SessionStore(path, 'conversations', 'system_ai')
    binding = store.begin(store.create()['id'])
    requests = []

    def execute(**kwargs):
        requests.append(kwargs)
        yield {'type': 'final', 'content': '수정된 답' if len(requests) > 1 else '처음 답'}

    monkeypatch.setattr('consciousness_agent.get_consciousness_agent',
                        lambda: SimpleNamespace(is_ready=True, process=lambda **kw:
                            {'task_framing': kw['user_message'], 'achievement_criteria': ''}))
    monkeypatch.setattr('consciousness_agent.get_world_pulse_text', lambda: '')
    runner = Runner(tmp_path, execute)
    body = runner._cognitive_stream_body

    def late_steering(*args, **kwargs):
        for event in body(*args, **kwargs):
            yield event
            if event['type'] == 'final' and len(requests) == 1:
                inbox.post(tc.get_current_agent_id(), '이전 결과는 보존하고 제목만 변경',
                           tc.get_current_task_id(), require_active=True)

    runner._cognitive_stream_body = late_steering
    with sessions.scope(binding):
        events = list(runner.cognitive_stream('보고서 작성', []))
    assert len(requests) == 2
    assert '제목만 변경' in requests[1]['message_content']
    assert '처음 답' in requests[1]['message_content']
    assert [e['content'] for e in events if e['type'] == 'final'] == ['수정된 답']
    assert not [e for e in events if e['type'] == 'error']
    with sessions.connection(path) as db:
        payloads = [row[0] for row in db.execute('SELECT payload FROM conversation_events')]
    assert any('handoff.steer.completed' in row for row in payloads)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
