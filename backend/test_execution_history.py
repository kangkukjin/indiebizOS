"""Ordinary execution retains context; historical separate results stay owner-scoped."""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import conversation_sessions as sessions
from conversation_db import ConversationDB
from execution_history import PendingExecutionHistory, pending_receipts


class AI:
    def __init__(self, scripts):
        self.agent_id = 'system_ai'
        self._provider = NS(model='same-model', system_prompt='System structure + IBL + rules',
                            tools=['all tools'], _last_tool_calls=[],
                            disable_session_persistence=False)
        self.scripts = iter(scripts)
        self.calls = []

    def process_message_stream(self, **kwargs):
        self.calls.append((self._provider, kwargs))
        yield from next(self.scripts)


@pytest.fixture
def binding(tmp_path, monkeypatch):
    monkeypatch.setattr('conversation_db._ckpt_schedule', None)
    monkeypatch.setattr('conversation_db._ckpt_apply', None)
    db = ConversationDB(str(tmp_path / 'conversation.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('assistant')
    store = sessions.SessionStore(db.db_path, 'messages', sessions.pair_owner(user, agent))
    binding = store.begin(store.create()['id'])
    with sessions.scope(binding):
        yield binding
    store.finish(binding)


def legacy_result(actor='system_ai', response='삼성1 음량 12 확인'):
    sessions.record_event({'type': 'reflex.result', 'actor': actor,
                           'request': '소리 키워', 'response': response,
                           'results': [{'result_ref': 'stored-result'}]})


@pytest.mark.parametrize('termination', ['complete', 'error', 'cancel', 'no_final', 'not_sent'])
def test_historical_delivery_ack_requires_successful_response(binding, termination):
    legacy_result()
    runner = NS(ai=AI([]), config={})
    receipt = PendingExecutionHistory(runner)
    if termination != 'not_sent':
        message = receipt.message('현재 상태를 알려줘')
        assert '삼성1 음량 12 확인' in message and 'stored-result' in message
    if termination != 'no_final':
        receipt.observe({'type': 'final', 'content': '완료'})
    if termination == 'error':
        receipt.observe({'type': 'error', 'content': 'connection failed'})
    receipt.finish(termination != 'cancel')
    assert bool(pending_receipts('system_ai')) == (termination != 'complete')
    next_receipt = PendingExecutionHistory(runner)
    assert ('stored-result' in next_receipt.message('후속')) == (termination != 'complete')


def test_historical_results_and_ack_remain_conversation_and_actor_scoped(binding):
    legacy_result('other', 'private')
    assert pending_receipts('system_ai') == []
    runner = NS(ai=AI([]), config={})
    legacy_result()
    receipt = PendingExecutionHistory(runner)
    receipt.message('후속')
    receipt.observe({'type': 'final', 'content': '완료'})
    other = sessions.Binding(binding.db_path, 'different-session', binding.owner, binding.turn_id)
    with sessions.scope(other):
        assert pending_receipts('other') == []
        receipt.finish(True)
    assert pending_receipts('system_ai')
    receipt.finish(True)
    assert pending_receipts('system_ai') == []
    assert pending_receipts('other')


def test_ack_does_not_consume_results_recorded_after_input(binding):
    legacy_result(response='first')
    receipt = PendingExecutionHistory(NS(ai=AI([]), config={}))
    receipt.message('후속')
    legacy_result(response='later')
    receipt.observe({'type': 'final', 'content': '완료'})
    receipt.finish(True)
    assert [row['response'] for _, row in pending_receipts('system_ai')] == ['later']


@pytest.mark.parametrize('message', ['음악 꺼', '#execute 보고서를 수정해'])
def test_pipeline_preserves_provider_full_history_and_recall(binding, monkeypatch, message):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin):
        pass

    class Recall:
        reflex = NS(score=.99, code='old recipe')
        def attach(self, *args): pass
        def route(self, kind, **kwargs): self.routed = kind
        def text(self): return '<recall>current memory and device state</recall>'
        def finish(self, **kwargs): pass
        def usage_payload(self): return {}

    runner = Runner()
    runner.config = {'name': 'system_ai', '_is_system_ai': True}
    runner.ai = AI([[{'type': 'final', 'content': '완료'}]])
    provider = runner.ai._provider
    provider.SESSION_STORE = NS(mapping={'system_ai': 'existing-cli-session'})
    recall = Recall()
    runner._associate = lambda *a, **kw: recall
    runner._classify_request = lambda *a, **kw: 'EXECUTE'
    runner._run_consciousness_or_reuse = lambda *a, **kw: pytest.fail('ordinary execution')
    runner._load_role = lambda: 'role'
    runner._build_system_ai_prompt_split = lambda role, c, mem, **kw: ('rules', mem)
    runner._after_response_async = lambda *a, **kw: None
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)

    def adopt(guard, runner, message, response, *args, **kwargs):
        yield from ()
        return response
    monkeypatch.setattr('capability_guard.adopt_response', adopt)
    history = [{'role': 'user', 'content': 'old research ' * 1000},
               {'role': 'tool', 'content': 'window-id=42'},
               *[{'role': 'assistant', 'content': str(i)} for i in range(5)]]
    legacy_result()
    with runner.turn_ai_scope():
        events = list(runner._cognitive_stream_body(message, history))
    assert not [event for event in events if event['type'] == 'error']
    assert recall.routed == 'EXECUTE'
    assert runner.ai._provider is provider
    assert len(runner.ai.calls) == 1
    used_provider, inputs = runner.ai.calls[0]
    assert inputs['history'] == history
    assert used_provider.model == provider.model
    assert used_provider.SESSION_STORE is provider.SESSION_STORE
    assert used_provider.SESSION_STORE.mapping == {'system_ai': 'existing-cli-session'}
    assert 'current memory and device state' in inputs['message_content']
    assert 'stored-result' in inputs['message_content']
    assert pending_receipts('system_ai') == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
