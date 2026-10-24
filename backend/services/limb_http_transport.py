"""Per-thread HTTP connection pools for the phone's sync, event and transfer lanes."""
import threading


class LimbHttpTransport:
    def __init__(self, hub):
        self.hub = hub.rstrip('/')
        self.local = threading.local()

    def __call__(self, path, payload, timeout):
        import requests
        from limb_client import LimbError
        session = getattr(self.local, 'session', None)
        if session is None:
            session = self.local.session = requests.Session()
        # requests defaults to no automatic POST retries. Lost replies are reconciled
        # by event IDs / job IDs, never by silently replaying a device operation.
        response = session.post(f'{self.hub}/limb/resident/{path}', json=payload,
                                timeout=(10, timeout))
        try:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code != 200:
                detail = body.get('detail') if isinstance(body, dict) else None
                raise LimbError(str(detail or f'http_{response.status_code}'), response.status_code)
            return body if isinstance(body, dict) else {}
        finally:
            response.close()

    def close(self):
        session = getattr(self.local, 'session', None)
        if session is not None:
            session.close()
            del self.local.session
