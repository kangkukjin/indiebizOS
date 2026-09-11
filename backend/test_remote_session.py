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
    monkeypatch.setattr(ws.streams, "_stream_agent_keys", {})
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

    monkeypatch.setattr(ws.streams, "handle_chat_message", chat)
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


@pytest.fixture
def web_client(monkeypatch, tmp_path):
    import api_launcher_web as auth
    import launcher_react
    from fastapi.responses import JSONResponse
    root = tmp_path / "dist"
    root.mkdir()
    (root / "assets").mkdir()
    (root / "assets/app.js").write_text("/* test bundle */")
    (root / "assets/app.css").write_text("body {}")
    (root / "index.html").write_text('<html lang="ko"><head><meta name="indiebiz-remote-shell" content="1" />'
                                    '<script type="module" src="./assets/app.js"></script></head><body><div id="root"></div></body></html>')
    monkeypatch.setattr(launcher_react, "bundle_root", lambda: root)
    monkeypatch.setattr(auth, "sessions", {})
    monkeypatch.setattr(auth, "load_config", lambda: {"enabled": True, "password_hash": auth.hash_password("test-password")})
    app = FastAPI()

    @app.middleware("http")
    async def guard(request, next_call):
        if auth.is_external_request(request) and not (
                auth.is_public_remote_path(request.method, request.url.path) or auth.verify_session(request)):
            return JSONResponse({"detail": "login required"}, status_code=401)
        return await next_call(request)

    app.include_router(auth.router)

    @app.get("/projects")
    def projects():
        return {"test": True}

    with TestClient(app, base_url="https://remote.invalid") as test_client:
        yield test_client, root


def test_shared_stream_tool_event_preserves_failure_and_call_identity():
    from chat_streams import tool_event_payload
    result = tool_event_payload({"type": "tool_result", "id": "parallel-call-a", "name": "execute_ibl",
                                 "result": {"error": "failed", "result_ref": "retained"},
                                 "is_error": True, "images": ["not duplicated"]}, "agent")
    assert result == {"type": "tool_result", "agent": "agent", "id": "parallel-call-a", "name": "execute_ibl",
                      "result": {"error": "failed", "result_ref": "retained"}, "is_error": True}
    assert tool_event_payload({"type": "tool_start", "id": "b", "input": {"code": "test"}}, "agent") == {
        "type": "tool_start", "agent": "agent", "name": "unknown", "id": "b", "input": {"code": "test"}}


def test_react_shell_public_assets_and_session_cookie_flow(web_client):
    client, _ = web_client
    shell = client.get("/launcher/app")
    assert shell.status_code == 200
    assert 'data-indiebiz-surface="remote"' in shell.text
    assert '<base href="/launcher/ui/">' in shell.text
    assert shell.headers["cache-control"] == "no-store"
    assert client.get("/launcher/ui/assets/app.js").status_code == 200
    assert client.get("/launcher/ui/assets/app.css").headers["content-type"].startswith("text/css")
    assert client.get("/launcher/auth/session").json() == {"external": True, "authenticated": False}
    assert client.get("/projects").status_code == 401
    assert client.post("/launcher/auth/login", json={"password": "wrong"}).status_code == 401
    login = client.post("/launcher/auth/login", json={"password": "test-password"})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"] and "Secure" in login.headers["set-cookie"]
    assert client.get("/launcher/auth/session").json()["authenticated"] is True
    assert client.get("/projects").status_code == 200
    assert client.post("/launcher/auth/logout").status_code == 200
    assert client.get("/projects").status_code == 401


def test_bundle_asset_boundary_and_no_private_formats(web_client, tmp_path):
    client, root = web_client
    outside = tmp_path / "private.js"
    outside.write_text("private")
    (root / "assets/escape.js").symlink_to(outside)
    (root / "assets/private.json").write_text("{}")
    (root / "assets/app.js.map").write_text("{}")
    for path in ["assets/escape.js", "assets/private.json", "assets/app.js.map", "index.html", "%2e%2e/private.js"]:
        assert client.get("/launcher/ui/" + path).status_code == 404
    assert client.post("/launcher/ui/assets/app.js").status_code == 401
    assert client.get("/launcher/ui/missing.js").status_code == 404


def test_missing_old_or_partial_bundle_retains_legacy_and_portal_helper(web_client, monkeypatch):
    import api_launcher_web as auth
    import launcher_react
    client, root = web_client
    monkeypatch.setattr(auth, "_launcher_surface_html", lambda: "legacy-shared-phone-portal")
    assert auth.get_launcher_webapp_html() == "legacy-shared-phone-portal"
    (root / "assets/app.js").unlink()
    assert client.get("/launcher/app").text == "legacy-shared-phone-portal"
    (root / "index.html").write_text("old desktop bundle")
    assert client.get("/launcher/app").text == "legacy-shared-phone-portal"
    monkeypatch.setattr(launcher_react, "bundle_root", lambda: None)
    assert client.get("/launcher/app").text == "legacy-shared-phone-portal"
    assert client.get("/launcher/lite").status_code == 200


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
