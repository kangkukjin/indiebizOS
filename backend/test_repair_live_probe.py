"""운영 확인의 읽기 제한·실패 관측·명시적 재시도."""
import boot_paths  # noqa: F401
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from repair_live_probe import live_probe, failure_kind
from test_repair_continuation import consumer, record, receipt  # noqa: F401


@pytest.mark.parametrize("surface", ["/xray/app", "/launcher/app", "/health"])
def test_live_probe_only_forwards_explicit_reads(surface):
    requests = []

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"live page")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with live_probe(server.server_port) as url:
            with urlopen(url + surface) as response:
                assert response.read() == b"live page"
            for path, method in [("/xray/app", "POST"), ("/shutdown", "GET"),
                                 ("/xray/app?path=/secret", "GET"), ("//other/health", "GET")]:
                with pytest.raises(HTTPError) as exc:
                    urlopen(Request(url + path, method=method))
                assert exc.value.code in {403, 501}
        assert requests == [surface]
    finally:
        server.shutdown()
        server.server_close()


def test_environment_failure_returns_to_executor_for_judgment(consumer, tmp_path, monkeypatch):
    module, deliveries, settled = consumer
    row = record(tmp_path, active_verify={"state": "failed", "receipt": {
        "exit_code": 1, "failure_kind": "environment", "output_path": "full-receipt.json"}})
    receipt(tmp_path)
    monkeypatch.setattr(module, "_commit_ready", lambda *a: None)
    calls = []
    def execute(current):
        calls.append(current)
        return {'response': '환경 오류를 확인했습니다', 'evaluation': {'goal_status': 'UNKNOWN'}}
    module.process_pending(tmp_path, "new", execute)
    assert len(calls) == 1
    assert calls[0]['active_verify']['receipt']['output_path'] == 'full-receipt.json'
    assert settled == ["blocked"]


def test_failure_classification_does_not_hide_assertions():
    assert failure_kind("AssertionError: wrong translation", 1) == "unknown"
    assert failure_kind("mkdir: Operation not permitted", 1) == "unknown"
    assert failure_kind("<urlopen error [Errno 1] Operation not permitted>", 1) == "environment"
    assert failure_kind("sandbox_apply: Operation not permitted", 0) is None


def test_explicit_retry_preserves_receipt_without_lifetime_attempt_limit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import api_repair_continuation as worker
    from restart_protocol import atomic_json
    active = {"state": "failed", "receipt": {"exit_code": 1, "failure_kind": "environment"}}
    row = record(tmp_path, status="blocked", active_verify=active)
    candidate = SimpleNamespace(target=lambda base, rel: base / rel, fingerprint=lambda p: "verified")
    st = SimpleNamespace(_candidate=candidate, read_session=lambda *a: {"sealed": {"a": {"after": "verified"}}})
    monkeypatch.setattr("red_apply._load_handler", lambda *a: SimpleNamespace(_staging_mod=lambda: st))
    updated = worker.retry_environment(row["task_id"], tmp_path)
    assert updated["active_verify_history"] == [active]
    assert updated["status"] == "waiting_apply" and updated["active_verify"] is None
    atomic_json(tmp_path / "data/system_ai_state/repair_continuations/task-repair.json",
                {**updated, "status": "blocked", "active_verify": active})
    again = worker.retry_environment(row["task_id"], tmp_path)
    assert len(again['active_verify_history']) == 2
    assert again['active_verify'] is None


def test_continuation_commit_consumes_existing_active_probe(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    import api_repair_continuation as worker

    command = 'python live_check.py'
    checked = {'state': 'passed', 'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
               'receipt': {'exit_code': 0}}
    session = {'readiness': {'activation_commands': {'active_verify_cmd': command}}}
    persisted = []
    def commit(*args):
        assert persisted and session['activation_checks']['active_verify_cmd'] == checked
        return {'success': True}
    staging = SimpleNamespace(read_session=lambda *a: session,
                              _save_session=lambda *a: persisted.append(True), commit_applied=commit)
    monkeypatch.setattr('red_apply._load_handler', lambda *a: SimpleNamespace(_staging_mod=lambda: staging))
    row = {'task_id': 'task', 'active_verify': checked}
    worker._commit_ready(row, tmp_path)
    assert row['commit']['success']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
