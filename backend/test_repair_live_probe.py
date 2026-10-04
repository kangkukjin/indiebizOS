"""운영 검증의 읽기 제한·환경 장애 분류·모델 재호출 금지."""
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


def test_environment_failures_never_start_an_executor(consumer, tmp_path, monkeypatch):
    module, deliveries, settled = consumer
    row = record(tmp_path, active_verify={"state": "failed", "receipt": {
        "exit_code": 1, "failure_kind": "environment", "output_path": "full-receipt.json"}})
    receipt(tmp_path)
    monkeypatch.setattr(module, "_commit_ready", lambda *a: None)
    module.process_pending(tmp_path, "new", lambda *a: pytest.fail("환경 오류 뒤 모델 실행"))
    assert settled == ["blocked"]
    import repair_continuation
    assert repair_continuation.read(row["task_id"], tmp_path)["phase"] == "verify_environment"
    assert "full-receipt.json" in deliveries[0]["reason"]


def test_failure_classification_does_not_hide_assertions():
    assert failure_kind("AssertionError: wrong translation", 1) == "check"
    assert failure_kind("<urlopen error [Errno 1] Operation not permitted>", 1) == "environment"
    assert failure_kind("sandbox_apply: Operation not permitted", 0) is None


def test_environment_retry_preserves_receipt_and_is_bounded(tmp_path, monkeypatch):
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
    with pytest.raises(ValueError, match="한 번"):
        worker.retry_environment(row["task_id"], tmp_path)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
