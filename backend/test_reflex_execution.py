"""REFLEX: 분류 호출 재사용, 주 세션 보존, 행동 전 승격, 별도 실행 결말 인계."""
import json
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import conversation_sessions as sessions
from conversation_db import ConversationDB
from cognitive_consciousness import CognitiveConsciousnessMixin
from reflex_execution import ReflexTurn, NEEDS_CONTEXT, recent_history, pending_receipts, _TurnSessions


@pytest.fixture
def binding(tmp_path, monkeypatch):
    monkeypatch.setattr('conversation_db._ckpt_schedule', None)
    monkeypatch.setattr('conversation_db._ckpt_apply', None)
    db = ConversationDB(str(tmp_path / 'conversation.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('assistant')
    store = sessions.SessionStore(db.db_path, 'messages', sessions.pair_owner(user, agent))
    sid = store.create()['id']
    b = store.begin(sid)
    with sessions.scope(b):
        yield b
    store.finish(b)


class AI:
    def __init__(self, scripts):
        self.agent_id = 'system_ai'
        self._provider = NS(model='same-model', system_prompt='System structure + IBL + rules',
                            tools=['all tools'], SESSION_STORE=_TurnSessions(),
                            _last_tool_calls=[], disable_session_persistence=False)
        self.scripts = iter(scripts)
        self.calls = []

    def process_message_stream(self, **kw):
        self.calls.append((self._provider, kw))
        yield from next(self.scripts)


def runner(scripts):
    return NS(ai=AI(scripts), config={'name': 'system_ai'})


def history():
    return [{'role': 'user', 'content': 'old research ' * 10000},
            {'role': 'assistant', 'content': 'old research answer'},
            {'role': 'tool', 'content': 'old raw evidence'},
            {'role': 'user', 'content': '삼성1에서 음악 틀어'},
            {'role': 'assistant', 'content': '삼성1에서 재생했습니다.'},
            {'role': 'user', 'content': '소리 키워'},
            {'role': 'assistant', 'content': '삼성1 음량 9에서 12로 변경 확인'}]


def test_classifier_accepts_reflex_once_with_existing_short_context(monkeypatch):
    calls = []
    monkeypatch.setattr('model_resolver.consciousness_enabled', lambda: True)
    monkeypatch.setattr('consciousness_agent.oneshot_ai_call',
                        lambda message, **kw: calls.append(message) or 'REFLEX')
    r = CognitiveConsciousnessMixin()
    r._log = lambda *a: None
    assert r._decide_request_type('음악 꺼', .99, 'old recipe', history()) == ('REFLEX', None)
    assert len(calls) == 1
    assert '삼성1' in calls[0] and 'old research' not in calls[0]


def test_history_preserves_whole_recent_dialogue_without_old_tools():
    h = history()
    assert recent_history(h) == h[-4:]
    assert len(h) == 7
    assert recent_history([{'role': 'user', 'content': 'x' * 6001}]) is None
    assert recent_history([{'role': 'assistant', 'content': [{'type': 'tool_use'}]}]) is None
    assert recent_history([{'role': 'user', 'content': 'summary', '_history_replacement': True}]) is None


def test_short_turn_keeps_prompt_model_tools_and_primary_session(binding):
    r = runner([[{'type': 'tool_start', 'name': 'execute_ibl'},
                 {'type': 'tool_result', 'result': 'stopped'},
                 {'type': 'final', 'content': '삼성1 중지 확인'}]])
    primary = r.ai._provider
    primary.SESSION_STORE.mapping = {'system_ai': 'long-main-session'}
    t = ReflexTurn(r, '음악 꺼', history())
    assert t.eligible
    t.prepare(True, history())
    assert t.active and r.ai._provider is not primary
    isolated = r.ai._provider
    assert isolated.model == primary.model and isolated.system_prompt == primary.system_prompt
    assert isolated.tools == primary.tools
    assert isolated.SESSION_STORE.load_map() == {}
    events = list(t.stream('<recall>기기와 기억 유지</recall>음악 꺼', t.history, None, None))
    assert events[-1]['content'] == '삼성1 중지 확인'
    assert r.ai.calls[0][1]['history'] == history()[-4:]
    assert '<recall>기기와 기억 유지</recall>' in r.ai.calls[0][1]['message_content']
    isolated.SESSION_STORE.save_map({'system_ai': 'short-session'})
    t.finish(events[-1]['content'], [], True)
    t.restore()
    assert r.ai._provider is primary
    assert primary.SESSION_STORE.load_map() == {'system_ai': 'long-main-session'}
    assert pending_receipts('system_ai')[0][1]['response'] == '삼성1 중지 확인'


def test_context_signal_is_buffered_and_falls_back_before_any_tool(binding):
    r = runner([[{'type': 'text', 'content': NEEDS_CONTEXT[:8]},
                 {'type': 'text', 'content': NEEDS_CONTEXT[8:]},
                 {'type': 'final', 'content': NEEDS_CONTEXT}],
                [{'type': 'tool_start', 'name': 'execute_ibl'},
                 {'type': 'final', 'content': '전체 문맥으로 완료'}]])
    primary = r.ai._provider
    t = ReflexTurn(r, '그것 꺼', history()); t.prepare(True, history())
    events = list(t.stream('그것 꺼', t.history, None, None))
    assert len(r.ai.calls) == 2 and not t.active
    assert r.ai.calls[1][0] is primary
    assert r.ai.calls[1][1]['history'] == history()
    assert sum(e['type'] == 'tool_start' for e in events) == 1
    assert not any('reflex_needs' in e.get('content', '') for e in events)


def test_signal_after_tool_never_repeats_action(binding):
    r = runner([[{'type': 'tool_start', 'name': 'execute_ibl'},
                 {'type': 'final', 'content': NEEDS_CONTEXT}]])
    t = ReflexTurn(r, '꺼', history()); t.prepare(True, history())
    events = list(t.stream('꺼', t.history, None, None))
    assert len(r.ai.calls) == 1 and t.active
    assert '중복 실행하지 않았습니다' in events[-1]['content']
    t.finish(events[-1]['content'], [{'name': 'execute_ibl'}], True)
    t.restore()
    assert pending_receipts('system_ai')[0][1]['completed'] is False


def test_receipts_survive_new_controller_and_ack_only_after_delivery(binding):
    sessions.record_event({'type': 'reflex.result', 'actor': 'system_ai',
                           'request': '소리 키워', 'response': '삼성1 음량 12 확인'})
    r = runner([[{'type': 'error', 'content': 'connection failed'}],
                [{'type': 'final', 'content': '후속 완료'}],
                [{'type': 'final', 'content': '다음 완료'}]])
    for expected in [True, True, False]:
        t = ReflexTurn(r, '최근 조작 설명해', history()); t.prepare(False, history())
        events = list(t.stream('최근 조작 설명해', history(), None, None))
        assert ('<separate_execution_history>' in r.ai.calls[-1][1]['message_content']) is expected
        t.finish(events[-1].get('content'), [], events[-1]['type'] == 'final')
    assert pending_receipts('system_ai') == []
    # 같은 대화에 다른 실행 주체의 결말을 섞지 않는다.
    sessions.record_event({'type': 'reflex.result', 'actor': 'other', 'response': 'private'})
    assert pending_receipts('system_ai') == []
    b = sessions.Binding(binding.db_path, 'different-session', binding.owner, binding.turn_id)
    with sessions.scope(b):
        assert pending_receipts('other') == []


def test_cancel_does_not_trigger_fallback_or_ack(binding):
    r = runner([[{'type': 'final', 'content': NEEDS_CONTEXT}]])
    t = ReflexTurn(r, '꺼', history()); t.prepare(True, history())
    assert list(t.stream('꺼', t.history, None, lambda: True)) == []
    assert len(r.ai.calls) == 1
    t.restore()


def test_unbound_and_attachment_stay_on_existing_path(binding):
    r = runner([])
    assert not ReflexTurn(r, '사진 속 기기 꺼', history(), [{}]).eligible
    with sessions.scope(None):
        assert not ReflexTurn(r, '음악 꺼', history()).eligible


def test_real_cli_spawn_uses_only_turn_store(binding):
    from test_cli_stream_deadline import _FakeCli, _make

    class Echo(_FakeCli):
        CHILD_CODE = ("import json,sys; print(json.dumps({'type':'text',"
                      "'session_id':'short-cli','content':sys.stdin.read()}))")

        def _capture_session_id(self, event):
            return event.get('session_id')

        def _build_command(self, **kw):
            self.invocation = kw
            return super()._build_command(**kw)

    primary = _make(Echo, disable_session_persistence=False)
    primary.SESSION_STORE = _TurnSessions()
    key = primary._get_session_key()
    primary.SESSION_STORE.save_map({key: 'long-main-session'})
    r = runner([]); r.ai._provider = primary
    t = ReflexTurn(r, '음악 꺼', history()); t.prepare(True, history())
    short = r.ai._provider
    events = list(short.process_message_stream('음악 꺼', history=t.history))
    assert not [e for e in events if e['type'] == 'error'], events
    assert short.invocation['resume_session_id'] is None
    sent = ''.join(e.get('content', '') for e in events if e['type'] == 'text')
    assert '삼성1' in sent and 'old research' not in sent and 'old raw evidence' not in sent
    assert short.SESSION_STORE.load_map()[key] == 'short-cli'
    list(short.process_message_stream('결과 확인', history=t.history))
    assert short.invocation['resume_session_id'] == 'short-cli'
    t.restore()
    assert primary.SESSION_STORE.load_map()[key] == 'long-main-session'
    list(primary.process_message_stream('일반 요청', history=history()))
    assert primary.invocation['resume_session_id'] == 'long-main-session'


def test_pipeline_routes_reflex_without_changing_recall_or_model(binding, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin):
        pass

    class Recall:
        reflex = NS(score=.99, code='old recipe')
        routed = None
        def attach(self, *a): pass
        def route(self, kind, **kw): self.routed = kind
        def text(self): return '<recall>all current memory and device state</recall>'
        def finish(self, **kw): pass
        def usage_payload(self): return {}

    r = Runner(); r.config = {'name': 'system_ai', '_is_system_ai': True}
    r.ai = AI([[{'type': 'final', 'content': '현재 시각은 오전 3시입니다.'}]])
    original = r.ai._provider
    recall = Recall()
    r._associate = lambda *a, **kw: recall
    r._decide_request_type = lambda *a: ('REFLEX', None)
    r._load_role = lambda: 'role'
    r._build_system_ai_prompt_split = lambda role, c, mem, **kw: ('System structure + IBL + rules', mem)
    r._after_response_async = lambda *a, **kw: None
    monkeypatch.setattr('pursuit_bind.prepare', lambda: '')
    monkeypatch.setattr('pursuit_bind.refresh_memory', lambda x: x)
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda r: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)

    def adopt(guard, runner, message, response, *a, **kw):
        yield from ()
        return response
    monkeypatch.setattr('capability_guard.adopt_response', adopt)
    with r.turn_ai_scope():
        events = list(r._cognitive_stream_body('지금 몇 시야', history()))
        assert not [e for e in events if e['type'] == 'error'], events
    assert [e['content'] for e in events if e['type'] == 'final'] == ['현재 시각은 오전 3시입니다.']
    assert recall.routed == 'REFLEX'
    assert r.ai._provider is original
    assert r.ai.calls[0][1]['history'] == history()[-4:]
    assert 'all current memory and device state' in r.ai.calls[0][1]['message_content']
    assert pending_receipts('system_ai')[0][1]['completed'] is True


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
