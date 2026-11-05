"""A total deadline for short, tool-free decisions, including streamed reads."""
import asyncio
import contextvars
import queue
import threading
import time


class DecisionDeadline(TimeoutError):
    kind = 'deadline'


class DecisionCancelled(RuntimeError):
    kind = 'cancelled'


def remaining(provider):
    cancel = getattr(provider, '_decision_cancel_check', None)
    if cancel and cancel():
        raise DecisionCancelled('사용자가 판단 호출을 취소했습니다')
    deadline = getattr(provider, '_request_deadline', None)
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        raise DecisionDeadline('짧은 판단의 전체 대기 한도에 도달했습니다')
    return left


def transport_stream(provider, consume):
    """Bridge an async SDK stream; cancellation closes IO before this iterator exits.

    The synchronous execution worker retains its provider loop and usage tracking.
    Only transport IO runs on the owned thread. No task survives the generator.
    """
    events = queue.Queue()
    state, ready = {}, threading.Event()

    async def run():
        state.update(loop=asyncio.get_running_loop(), task=asyncio.current_task())
        ready.set()
        async def check_cancel():
            while True:
                await asyncio.sleep(.05)
                cancel = getattr(provider, '_decision_cancel_check', None)
                if cancel and cancel():
                    state['cancelled'] = True
                    state['task'].cancel()
                    return
        monitor = asyncio.create_task(check_cancel())
        try:
            async with asyncio.timeout(remaining(provider)):
                await consume(lambda chunk: events.put(('chunk', chunk)))
        except (TimeoutError, asyncio.CancelledError):
            state['finishing'] = True
            error = DecisionCancelled('사용자가 판단 호출을 취소했습니다') if state.get('cancelled') else DecisionDeadline('짧은 판단의 전체 대기 한도에 도달했습니다')
            events.put(('error', error))
        except Exception as exc:
            state['finishing'] = True
            events.put(('error', exc))
        finally:
            state['finishing'] = True
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            events.put(('done', None))

    context = contextvars.copy_context()
    worker = threading.Thread(target=lambda: context.run(asyncio.run, run()), name='decision-transport')
    worker.start()
    try:
        while True:
            kind, value = events.get()
            if kind == 'done':
                break
            if kind == 'error':
                provider.last_failure_kind = getattr(value, 'kind', 'provider_error')
                raise value
            remaining(provider)  # Never accept a late buffered success.
            yield value
    finally:
        ready.wait()
        if worker.is_alive():
            try:
                def cancel_running():
                    if not state.get('finishing'):
                        state['task'].cancel()
                state['loop'].call_soon_threadsafe(cancel_running)
            except RuntimeError:
                pass
        worker.join()  # asyncio cancellation has closed the owned HTTP client.


def openai_stream(provider, params):
    import openai
    source = provider._client
    async def consume(emit):
        async with openai.AsyncOpenAI(
            api_key=source.api_key, base_url=str(source.base_url),
            organization=source.organization, project=source.project,
            max_retries=0, timeout=remaining(provider),
        ) as client:
            stream = await client.chat.completions.create(**params)
            async with stream:
                async for chunk in stream:
                    emit(chunk)
    return transport_stream(provider, consume)


class AnthropicStream:
    """Keep the existing synchronous event/final-message consumer contract."""
    def __init__(self, provider, params):
        import anthropic
        async def consume(emit):
            async with anthropic.AsyncAnthropic(
                api_key=provider._client.api_key, base_url=str(provider._client.base_url),
                max_retries=0, timeout=remaining(provider),
            ) as client:
                async with client.messages.stream(**params) as stream:
                    async for event in stream:
                        emit(event)
                    self.final_message = await stream.get_final_message()
        self.iterator = transport_stream(provider, consume)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.iterator.close()

    def __iter__(self):
        return self.iterator

    def get_final_message(self):
        return self.final_message


def gemini_stream(provider, contents, config):
    from google import genai
    async def consume(emit):
        client = genai.Client(api_key=provider.api_key, http_options={
            'timeout': max(1, int(remaining(provider) * 1000)),
            'retry_options': {'attempts': 1},
        })
        try:
            async with client.aio as async_client:
                stream = await async_client.models.generate_content_stream(
                    model=provider.model, contents=contents, config=config)
                try:
                    async for chunk in stream:
                        emit(chunk)
                finally:
                    await stream.aclose()
        finally:
            client.close()
    return transport_stream(provider, consume)


def retry_wait(provider, seconds):
    """Backoff consumes the same role budget and remains cancellable."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        left = remaining(provider)
        time.sleep(max(0, min(.05, end - time.monotonic(), left or seconds)))
    remaining(provider)
