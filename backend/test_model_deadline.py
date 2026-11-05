"""Total decision deadline cancels IO and joins its transport worker."""
import boot_paths  # noqa: F401
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from model_deadline import DecisionDeadline, openai_stream


@pytest.mark.parametrize('mode', ['connect', 'read', 'trickle'])
def test_decision_deadline_closes_transport_and_rejects_late_answer(monkeypatch, mode):
    closed = []
    class Stream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append('stream')
        def __aiter__(self):
            return self
        async def __anext__(self):
            await asyncio.sleep(0.03 if mode == 'trickle' else 60)
            return 'partial'
    class Client:
        def __init__(self, **kw):
            assert kw['max_retries'] == 0
            self.chat = SimpleNamespace(completions=self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append('client')
        async def create(self, **kw):
            if mode == 'connect':
                await asyncio.sleep(60)
            return Stream()
    monkeypatch.setattr('openai.AsyncOpenAI', Client)
    provider = SimpleNamespace(_request_deadline=time.monotonic() + .15,
        _client=SimpleNamespace(api_key='fixture', base_url='http://localhost', organization=None, project=None))
    started = time.monotonic()
    with pytest.raises(DecisionDeadline):
        list(openai_stream(provider, {'stream': True}))
    assert time.monotonic() - started < 1
    assert 'client' in closed and (mode == 'connect' or 'stream' in closed)
    assert not any(t.name == 'decision-transport' for t in threading.enumerate())


def test_slot_wait_obeys_same_deadline_and_does_not_enter():
    from consciousness_agent import _PriorityLock
    lock = _PriorityLock()
    lock.acquire()
    try:
        with pytest.raises(DecisionDeadline):
            with lock.held(deadline=time.monotonic() + .03):
                pytest.fail('entered occupied slot')
        assert lock._held == 1 and lock._fg_waiting == 0
    finally:
        lock.release()


@pytest.mark.parametrize('transport', ['openai', 'anthropic', 'gemini'])
@pytest.mark.parametrize('cancel', [False, True])
def test_sdk_transport_closes_on_cancel_or_deadline(monkeypatch, transport, cancel):
    from model_deadline import AnthropicStream, DecisionCancelled, gemini_stream
    closed = []
    cancelled = threading.Event()
    class Stream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append('stream')
        def __aiter__(self):
            return self
        async def __anext__(self):
            await asyncio.sleep(60)
        async def aclose(self):
            closed.append('stream')
    class Client:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=self)
            self.messages = self.models = self.aio = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append('client')
        async def create(self, **kw):
            return Stream()
        def stream(self, **kw):
            return Stream()
        async def generate_content_stream(self, **kw):
            return Stream()
        def close(self):
            closed.append('sync-client')
    monkeypatch.setattr('openai.AsyncOpenAI', Client)
    monkeypatch.setattr('anthropic.AsyncAnthropic', Client)
    monkeypatch.setattr('google.genai.Client', Client)
    provider = SimpleNamespace(api_key='fixture', model='fixture',
        _request_deadline=time.monotonic() + (.8 if cancel else .12),
        _decision_cancel_check=cancelled.is_set,
        _client=SimpleNamespace(api_key='fixture', base_url='http://localhost', organization=None, project=None))
    timer = threading.Timer(.08, cancelled.set) if cancel else None
    if timer:
        timer.start()
    try:
        with pytest.raises(DecisionCancelled if cancel else DecisionDeadline):
            if transport == 'anthropic':
                with AnthropicStream(provider, {}) as stream:
                    list(stream)
            else:
                list(openai_stream(provider, {}) if transport == 'openai'
                     else gemini_stream(provider, [], {}))
    finally:
        if timer:
            timer.join()
    assert 'stream' in closed and 'client' in closed
    assert not any(t.name == 'decision-transport' for t in threading.enumerate())


def test_cli_retry_backoff_shares_role_deadline():
    from model_deadline import retry_wait
    started = time.monotonic()
    with pytest.raises(DecisionDeadline):
        retry_wait(SimpleNamespace(_request_deadline=started + .1), 30)
    assert time.monotonic() - started < .5


def test_slot_wait_is_cancelled_before_its_deadline():
    from model_deadline import DecisionCancelled
    from consciousness_agent import _PriorityLock
    lock = _PriorityLock()
    lock.acquire()
    try:
        with pytest.raises(DecisionCancelled):
            with lock.held(deadline=time.monotonic() + 15, cancel_check=lambda: True):
                pytest.fail('cancelled caller entered slot')
        assert lock._held == 1 and lock._fg_waiting == 0
    finally:
        lock.release()
