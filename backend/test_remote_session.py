"""원격 HTTP 세션 계약을 WS 접속·후속 요청에도 적용한다. 모델 호출 없음."""
import boot_paths  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def client(monkeypatch):
    import api_launcher_web as auth
    import api_websocket as ws
    from websocket_manager import WebSocketManager
    monkeypatch.setattr(auth, "sessions", {"valid-session": {"created": "test"}})
    monkeypatch.setattr(ws, "manager", WebSocketManager())
    monkeypatch.setattr(ws, "_stream_tasks", {})
    monkeypatch.setattr(ws, "_stream_agent_keys", {})
    app = FastAPI()
    app.include_router(ws.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/ws/chat/probe", "/ws/launcher"])
def test_remote_websocket_rejects_missing_session(client, path):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("wss://remote.invalid" + path):
            pytest.fail("미인증 접속이 수락됐다")
    assert exc.value.code == 1008


@pytest.mark.parametrize("headers", [
    {"cookie": "launcher_session=valid-session"},
    {"X-Launcher-Session": "valid-session"},
])
def test_remote_session_allows_ping_and_revocation_blocks_next_request(client, monkeypatch, headers):
    import api_launcher_web as auth
    import api_websocket as ws
    called = []

    async def chat(*args):
        called.append(args)

    monkeypatch.setattr(ws, "handle_chat_message", chat)
    with client.websocket_connect("wss://remote.invalid/ws/chat/probe", headers=headers) as sock:
        sock.send_json({"type": "ping"})
        assert sock.receive_json() == {"type": "pong"}
        auth.sessions.clear()
        sock.send_json({"type": "chat", "message": "must not execute"})
        with pytest.raises(WebSocketDisconnect) as exc:
            sock.receive_json()
        assert exc.value.code == 1008
    assert called == []
    assert not ws.manager.is_connected("probe")


def test_local_desktop_still_connects_without_session(client):
    with client.websocket_connect("ws://localhost:8765/ws/chat/probe") as sock:
        sock.send_json({"type": "ping"})
        assert sock.receive_json() == {"type": "pong"}


def test_proxy_rewritten_local_host_requires_session(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://localhost:8765/ws/chat/probe",
                                      headers={"x-forwarded-proto": "https"}):
            pytest.fail("프록시 신호를 로컬로 오인했다")


@pytest.mark.parametrize("failing", ["is_external_request", "verify_session"])
def test_auth_failure_is_closed(client, monkeypatch, failing):
    import api_launcher_web as auth

    def fail(*args):
        raise RuntimeError("auth unavailable")

    monkeypatch.setattr(auth, failing, fail)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("wss://remote.invalid/ws/chat/probe",
                                      headers={"cookie": "launcher_session=valid-session"}):
            pytest.fail("판정 실패를 통과로 처리했다")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
