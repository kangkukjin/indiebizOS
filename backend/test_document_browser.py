"""Actual Chromium + source API workflow. Not an Electron or Office acceptance test."""
import importlib.util
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for layer in ("datastore", "services", "surface"):
    sys.path.insert(0, str(HERE / layer))
import api_documents
from document_workspace import DocumentWorkspace


@pytest.mark.system
def test_browser_source_workflow(tmp_path, monkeypatch):
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright, expect
    from runtime_utils import get_base_path

    frontend = ROOT / "frontend"
    dependencies = frontend / "node_modules"
    installed = Path(get_base_path()) / "frontend/node_modules"
    assert installed.is_dir(), "프론트엔드 의존성을 먼저 설치해야 합니다"
    dependencies.mkdir(exist_ok=True)
    if dependencies.resolve() != installed.resolve():
        for package in installed.iterdir():
            target = dependencies / package.name
            if not target.exists():
                target.symlink_to(package, target_is_directory=package.is_dir())
    # Use the same registered build runner, after preparing the isolated deps.
    spec = importlib.util.spec_from_file_location("document_web_check", ROOT / "data/scripts/webapp_work.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan = runner.plan(frontend, ["build"])
    built = runner.run_check(frontend, "build", 180, plan["fingerprint"])
    assert built["ok"], built.get("output_tail", str(built))

    workspace = DocumentWorkspace(tmp_path / "workspace")
    monkeypatch.setattr(api_documents, "service", lambda: workspace)
    app = FastAPI()
    app.include_router(api_documents.router)

    # This loopback fixture exercises document UI, not remote authentication.
    @app.get("/launcher/auth/session")
    def session():
        return {"authenticated": True, "external": False}

    @app.get("/health")
    def health():
        return {"status": "ok"}
    html = (frontend / "dist/index.html").read_text()
    html = html.replace("<html", '<html data-indiebiz-surface="remote"', 1)

    @app.get("/")
    def index():
        return HTMLResponse(html)

    app.mount("/assets", StaticFiles(directory=frontend / "dist/assets"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        source = tmp_path / "보고서.txt"
        original = "처음 문장\r\n원본 보존\r\n".encode("cp949")
        source.write_bytes(original)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                failures = []
                page.on("pageerror", lambda error: failures.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}/#/documents")
                try:
                    page.get_by_label("로컬 파일 경로").wait_for(timeout=10000)
                except Exception as exc:
                    raise AssertionError({"page_errors": failures, "body": page.locator("body").inner_text()}) from exc
                page.get_by_label("로컬 파일 경로").fill(str(source))
                page.get_by_label("인코딩", exact=True).select_option("cp949")
                page.get_by_role("button", name="파일 열기", exact=True).click()
                editor = page.get_by_role("textbox", name="문서 원문", exact=True)
                expect(editor).to_have_value("처음 문장\n원본 보존\n")
                editor.fill("새로운 문장\n원본 보존\n")
                page.get_by_role("button", name="작업 저장", exact=True).click()
                expect(page.locator("footer")).to_contain_text("작업 저장됨")
                editor.evaluate("el => { el.focus(); el.setSelectionRange(0, 3); }")
                page.get_by_role("button", name="선택 고정", exact=True).click()
                expect(page.get_by_label("교체할 문구")).to_have_value("새로운")
                page.get_by_label("교체할 문구").fill("수정한")
                page.get_by_role("button", name="제안 만들기", exact=True).click()
                page.get_by_role("button", name="제안 적용", exact=True).click()
                expect(editor).to_have_value("수정한 문장\n원본 보존\n")
                page.get_by_label("사본 파일명").fill("결과.txt")
                page.get_by_role("button", name="사본 저장", exact=True).click()
                expect(page.locator("footer")).to_contain_text("사본 저장됨")
                expect(page.locator("footer")).to_be_in_viewport()
                assert (tmp_path / "결과.txt").read_bytes() == "수정한 문장\r\n원본 보존\r\n".encode("cp949")
                assert source.read_bytes() == original
                page.reload()
                page.get_by_role("button", name="보고서.txt TXT").click()
                expect(page.get_by_role("textbox", name="문서 원문", exact=True)).to_have_value("수정한 문장\n원본 보존\n")
                assert not failures, failures
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "격리 UI 시험 서버 종료 실패"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
