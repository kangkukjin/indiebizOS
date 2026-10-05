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
    from test_document_app_support import mount_document_app, open_document
    ai_started, ai_release = threading.Event(), threading.Event()
    def ask(instruction, selected):
        if instruction == "지연 시험":
            ai_started.set()
            assert ai_release.wait(15), "AI 시험 응답 해제 시간 초과"
        return "수정한" if instruction == "고쳐" else "AI 수정"
    app = FastAPI()
    app.include_router(api_documents.router)
    mount_document_app(app, workspace, ask)

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
                def select(start, end):
                    editor.evaluate("(el, r) => { el.focus(); el.setSelectionRange(r[0], r[1]); el.dispatchEvent(new Event('select', {bubbles: true})); }", [start, end])
                def dock(instruction):
                    box = page.get_by_role("textbox", name="AI 요청", exact=True)
                    box.fill(instruction); box.press("Enter")
                try:
                    open_document(page, port, source, "cp949")
                    editor = page.get_by_role("textbox", name="문서 원문", exact=True)
                    expect(editor).to_have_value("처음 문장\n원본 보존\n", timeout=10000)
                except Exception as exc:
                    raise AssertionError({"page_errors": failures, "body": page.locator("body").inner_text()}) from exc
                status = page.get_by_role("status").first
                # 쓰면 초안이 저절로 서버에 올라간다(원본은 그대로).
                editor.fill("새로운 문장\n원본 보존\n")
                expect(status).to_contain_text("작업 저장됨")
                assert source.read_bytes() == original
                # AI 한 줄 — 선택한 부분만 고친다.
                select(0, 3)
                dock("고쳐")
                page.get_by_role("button", name="반영 (선택 대체)", exact=True).click()
                expect(editor).to_have_value("수정한 문장\n원본 보존\n")
                # ⚙ 도구 — 사본은 원본의 인코딩·줄바꿈으로.
                page.get_by_role("button", name="⚙ 도구", exact=True).last.click()
                page.get_by_label("사본 파일명").fill("결과.txt")
                page.get_by_role("button", name="다른 이름으로 저장", exact=True).click()
                expect(status).to_contain_text("사본 저장됨")
                assert (tmp_path / "결과.txt").read_bytes() == "수정한 문장\r\n원본 보존\r\n".encode("cp949")
                assert source.read_bytes() == original
                # 창을 새로 띄워도 초안이 남아 있다.
                open_document(page, port, source, fresh=True)
                editor = page.get_by_role("textbox", name="문서 원문", exact=True)
                expect(editor).to_have_value("수정한 문장\n원본 보존\n", timeout=10000)
                page.get_by_role("button", name="저장", exact=True).click()
                expect(status).to_contain_text("저장됨 · 원본 파일 기록 확인")
                assert source.read_bytes() == "수정한 문장\r\n원본 보존\r\n".encode("cp949")
                # 이전 버전 되살리기 → 초안. 저장해야 원본이 바뀐다.
                page.get_by_role("button", name="⚙ 도구", exact=True).last.click()
                page.get_by_role("button", name="되살리기", exact=True).last.click()
                expect(editor).to_have_value("처음 문장\n원본 보존\n")
                assert source.read_bytes() != original
                editor.press("Control+s")
                expect(status).to_contain_text("원본 파일 기록 확인")
                assert source.read_bytes() == original
                # AI 반영은 한 번 되돌릴 수 있다.
                select(0, 2)
                dock("다듬어")
                page.get_by_role("button", name="반영 (선택 대체)", exact=True).click()
                expect(editor).to_have_value("AI 수정 문장\n원본 보존\n")
                assert source.read_bytes() == original
                page.get_by_role("button", name="AI 반영 되돌리기", exact=True).click()
                expect(editor).to_have_value("처음 문장\n원본 보존\n")
                # AI 가 답하는 동안 사람이 고치면, 늦게 온 제안은 그 자리에 반영되지 않는다.
                select(0, 2)
                dock("지연 시험")
                assert ai_started.wait(5)
                expect(editor).to_be_editable()
                editor.fill("AI 대기 중 사람의 수정\n")
                ai_release.set()
                page.get_by_role("button", name="반영 (선택 대체)", exact=True).click()
                expect(status).to_contain_text("반영하지 않았습니다")
                expect(editor).to_have_value("AI 대기 중 사람의 수정\n")
                # 밖에서 원본이 바뀌었으면 저장을 거절하고 초안을 지킨다.
                expect(status).to_contain_text("작업 저장됨", timeout=10000)
                source.write_bytes("외부 수정\r\n".encode("cp949"))
                editor.fill("이후 초안\n")
                page.get_by_role("button", name="저장", exact=True).click()
                expect(status).to_contain_text("외부에서 원본이 바뀌었습니다")
                assert source.read_bytes() == "외부 수정\r\n".encode("cp949")
                expect(editor).to_have_value("이후 초안\n")
                assert not failures, failures
                spec = importlib.util.spec_from_file_location("document_live_probe", ROOT / "scripts/verify_document_workspace.py")
                verifier = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(verifier)
                assert verifier.live_probe(f"http://127.0.0.1:{port}", tmp_path)["ok"]
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "격리 UI 시험 서버 종료 실패"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
