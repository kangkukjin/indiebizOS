"""コ딩 화면의 실제 HTTP 계약과 브라우저 인수. UI 시험은 명시적으로 실행한다."""
import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import api_coding
import principal
from coding_git import text_git
from coding_process import available
from test_coding_workspace import workspace


@pytest.fixture
def surface(workspace, monkeypatch):
    service, repository, repo = workspace
    monkeypatch.setattr(api_coding, "service", lambda: service)
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5178"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(api_coding.router)
    return app, service, repository, repo


def test_http_conditional_text_save_and_owner(surface):
    app, service, repository, _ = surface
    with TestClient(app) as client:
        task = client.post("/coding/tasks", json={"repository_id": repository["id"], "goal": "edit"}).json()
        base = "/coding/tasks/" + task["id"]
        opened = client.get(base + "/file", params={"path": "a.txt"}).json()
        payload = {"path": "a.txt", "content": "saved\n", "expected": opened["fingerprint"]}
        assert client.put(base + "/file", json=payload).status_code == 200
        assert client.put(base + "/file", json=payload).status_code == 409
        assert client.get(base + "/file", params={"path": "../outside"}).status_code == 400
        for name, data in [("binary", b"\0bytes"), ("legacy", b"\xff\xfe"), ("large", b"a" * 200001)]:
            (Path(task["workspace"]) / name).write_bytes(data)
            item = client.get(base + "/file", params={"path": name}).json()
            assert item["binary"] or item["truncated"]
            assert client.put(base + "/file", json={"path": name, "content": "overwrite", "expected": item["fingerprint"]}).status_code == 400
        assert client.post("/coding/tasks", json={"repository_id": repository["id"], "goal": "bad"},
                           headers={"origin": "https://attacker.invalid"}).status_code == 403
        with principal.narrow(principal.ANONYMOUS):
            assert client.get("/coding/state").status_code == 403
        detail = client.get(base).json()
        assert detail["pursuit"] and "a.txt" in detail["files"]
        events = client.get(base + "/events").json()
        assert any(e["type"] == "file.saved" for e in events["items"])
        assert client.get(base + "/events", params={"after": events["next"]}).json()["items"] == []


@pytest.mark.skipif(not available(), reason="macOS sandbox required")
def test_http_verify_review_apply(surface):
    app, service, repository, repo = surface
    with TestClient(app) as client:
        task = client.post("/coding/tasks", json={"repository_id": repository["id"], "goal": "change"}).json()
        base = "/coding/tasks/" + task["id"]
        opened = client.get(base + "/file", params={"path": "a.txt"}).json()
        client.put(base + "/file", json={"path": "a.txt", "content": "after\n", "expected": opened["fingerprint"]}).raise_for_status()
        command = {"command": "test \"$(cat a.txt)\" = after && printf verified", "command_id": "verify-once"}
        run = client.post(base + "/verify", json=command).json()
        assert client.post(base + "/verify", json=command).json()["id"] == run["id"]
        deadline = time.monotonic() + 15
        while service.store.get("task", task["id"])["active_run"]:
            assert time.monotonic() < deadline
            time.sleep(.05)
        review = client.post(base + "/review", json={"selected": []}).json()
        assert review["paths"] == ["a.txt"] and "+after" in review["patch"]
        assert review["verifications"][0]["fresh"] and review["verifications"][0]["state"] == "passed"
        approval = {"review_id": review["id"], "fingerprint": review["fingerprint"]}
        client.post(base + "/approve", json=approval).raise_for_status()
        applied = client.post(base + "/apply", json={**approval, "command_id": "apply-once", "message": "HTTP acceptance"}).json()
        assert applied["state"] == "completed", applied
        assert text_git(repo, "rev-parse", "HEAD") == applied["commit"]
        assert (repo / "a.txt").read_text() == "after\n"


@contextmanager
def serve(app):
    import uvicorn
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline
        time.sleep(.05)
    try:
        yield "http://127.0.0.1:" + str(sock.getsockname()[1])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


@pytest.mark.system
def test_browser_launcher_to_commit(surface, tmp_path):
    """Vite 격리본 + 실제 서비스/OS/Git. 코딩 HTTP만 임시 저장소 서버로 프록시한다."""
    url = os.environ.get("CODING_UI_URL")
    if not url:
        pytest.skip("Start isolated Vite on 127.0.0.1:5178 and set CODING_UI_URL")
    from playwright.sync_api import sync_playwright, expect
    app, service, _, repo = surface
    with serve(app) as backend, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script("localStorage.setItem('indiebiz_launcher_mode','app'); localStorage.setItem('indiebiz_has_seen_guide','true');")
        def proxy(route):
            if "/coding/" in route.request.url:
                response = route.fetch(url=route.request.url.replace("http://127.0.0.1:8765", backend))
                route.fulfill(response=response)
            else:
                route.abort()
        page.route("http://127.0.0.1:8765/**", proxy)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(url)
            page.get_by_text("코딩", exact=True).dblclick()
            expect(page).to_have_url(url.rstrip("/") + "/#/coding")
            page.get_by_label("저장소 경로").fill(str(repo))
            page.get_by_role("button", name="열기", exact=True).click()
            page.get_by_label("새 과제 목표").fill("화면에서 수정, 테스트, 검토, 커밋")
            page.get_by_role("button", name="과제 시작", exact=True).click()
            page.get_by_role("button", name="a.txt", exact=True).click()
            expect(page.get_by_label("파일 내용")).to_have_value("before\n")
            page.get_by_label("파일 내용").fill("after\n")
            page.get_by_role("button", name="변경 저장", exact=True).click()
            expect(page.get_by_role("button", name="변경 저장", exact=True)).to_be_disabled()
            page.reload()
            page.get_by_role("button", name="a.txt", exact=True).click()
            expect(page.get_by_label("파일 내용")).to_have_value("after\n")
            if os.environ.get("CODING_UI_EXECUTOR"):
                page.get_by_label("실행자", exact=True).select_option(os.environ["CODING_UI_EXECUTOR"])
                page.get_by_label("AI 지시").fill("Read a.txt, change it to exactly ready followed by a newline. Run cat a.txt and report the result. Do not change other files or commit.")
                page.get_by_role("button", name="실행", exact=True).click()
                expect(page.get_by_role("button", name="실행 중단", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_role("button", name="실행 중단", exact=True)).not_to_be_visible(timeout=240000)
                task = service.store.list("task")[0]
                assert (Path(task["workspace"]) / "a.txt").read_text() == "ready\n"
                assert service.store.list("run")[0]["state"] == "completed"
                expect(page.locator(".coding-messages")).to_contain_text("ready")
            expected = "ready" if os.environ.get("CODING_UI_EXECUTOR") else "after"
            page.get_by_label("검증 명령").fill(f'test "$(cat a.txt)" = {expected} && printf UI_VERIFIED')
            page.get_by_role("button", name="검증 실행", exact=True).click()
            expect(page.locator(".coding-output")).to_contain_text("UI_VERIFIED", timeout=15000)
            expect(page.get_by_role("button", name="검토 묶음 갱신", exact=True)).to_be_enabled(timeout=15000)
            page.get_by_role("button", name="검토 묶음 갱신", exact=True).click()
            expect(page.locator(".coding-diff .added").filter(has_text="+" + expected)).to_be_visible()
            expect(page.locator(".coding-verification")).to_contain_text("현재 변경과 일치")
            page.get_by_label("커밋 메시지").fill("Coding UI acceptance")
            page.get_by_role("button", name="검토 완료", exact=True).click()
            page.get_by_role("button", name="정본 반영·커밋", exact=True).click()
            expect(page.locator(".coding-verification [role=status]")).to_contain_text("완료", timeout=15000)
            applied = service.store.list("apply")[0]
            assert text_git(repo, "rev-parse", "HEAD") == applied["commit"]
            assert (repo / "a.txt").read_text() == expected + "\n"
            page.reload()
            expect(page.locator(".coding-diff")).to_contain_text("+" + expected)
            expect(page.locator(".coding-output")).to_contain_text("UI_VERIFIED", timeout=10000)
            assert not errors, errors
            page.screenshot(path=str(tmp_path / "coding-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 720, "height": 900})
            page.get_by_role("button", name="대화", exact=True).click()
            expect(page.get_by_label("AI 지시")).to_be_visible()
            page.get_by_role("button", name="변경", exact=True).click()
            expect(page.locator(".coding-diff")).to_be_visible()
            page.screenshot(path=str(tmp_path / "coding-narrow.png"), full_page=True)
            print({"repository": str(repo), "state": str(service.store.root), "commit": applied["commit"],
                   "executor": os.environ.get("CODING_UI_EXECUTOR", "manual"), "screenshots": str(tmp_path)})
        finally:
            page.screenshot(path=str(tmp_path / "coding-last-screen.png"), full_page=True)
            browser.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
