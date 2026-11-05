"""CLI boundary observations and bounded cleanup owned by the invoking process."""
import threading
import time


def boundary(stage, **data):
    try:
        from model_call_context import fields, _call
        from episode_logger import record_trajectory_event
        started = (_call.get() or {}).get('_started_monotonic')
        record_trajectory_event('model.cli_boundary', {**fields(), 'stage': stage,
            'elapsed_ms': round((time.monotonic() - started) * 1000) if started else None, **data})
    except Exception:
        pass  # Instrumentation cannot change delivery.


class CliWatch:
    def __init__(self, provider, proc, cancel_check):
        self.provider, self.proc, self.cancel_check = provider, proc, cancel_check
        self.state = {'last': time.monotonic(), 'fired': 0.0, 'cancelled': False,
                      'terminal': None, 'reason': None}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.watch, daemon=True, name=f'{provider.STATE_PREFIX}-idle-watchdog')
        self.thread.start()

    def terminal(self):
        if self.state['terminal'] is None:
            self.state['terminal'] = time.monotonic()
            boundary('terminal_received')

    def watch(self):
        from completion_lease import cancel_channel, is_waiting, pending_tickets
        p, state = self.provider, self.state
        interval = min(p.STREAM_IDLE_POLL_SEC, 0.1) if getattr(p, '_request_deadline', None) else p.STREAM_IDLE_POLL_SEC
        while not self.stop.wait(interval):
            if self.proc.poll() is not None:
                return
            now = time.monotonic()
            decision_cancel = getattr(p, '_decision_cancel_check', None)
            if ((self.cancel_check and self.cancel_check()) or
                    (decision_cancel and decision_cancel())):
                state['cancelled'] = True
                cancel_channel(p._completion_channel)
            elif getattr(p, '_request_deadline', None) and now >= p._request_deadline:
                state.update(fired=now - state['last'], reason='role_deadline')
            elif (state['terminal'] is not None and not pending_tickets(p._completion_channel)
                  and now - state['terminal'] >= p.CLEANUP_TIMEOUT_SEC):
                state.update(fired=now - state['terminal'], reason='cleanup_deadline')
            elif is_waiting(p._completion_channel):
                state['last'] = now
                continue
            elif now - state['last'] > p.STREAM_IDLE_TIMEOUT_SEC:
                state.update(fired=now - state['last'], reason='idle_deadline')
            else:
                continue
            try:
                p._terminate_cli(self.proc)
            except ProcessLookupError:
                pass
            return

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)


class StderrDrain:
    """Drain stderr concurrently so a full pipe cannot deadlock stdout/exit."""
    def __init__(self, stream):
        self.text = ''
        self.stream = stream
        self.thread = threading.Thread(target=self.read, daemon=True, name='cli-stderr-drain')
        self.thread.start()

    def read(self):
        try:
            while self.stream:
                chunk = self.stream.read(4096)
                if not chunk:
                    break
                self.text = (self.text + chunk)[-64000:]
        except (OSError, ValueError):
            pass

    def close(self):
        self.thread.join(timeout=1)
