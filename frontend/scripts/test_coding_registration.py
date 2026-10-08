"""빌드된 코딩 앱의 등록 해제·취소·실패 복구. 업무 API는 합성이며 실제 폴더는 건드리지 않는다."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from playwright.sync_api import expect, sync_playwright

from launcher_browser import prepare_launcher

ROOT = Path(__file__).resolve().parents[1]


def test_unregister_confirmation_failure_and_list_refresh():
    manifest = yaml.safe_load((ROOT.parent / "data/instruments/coding.yaml").read_text())
    manifest["id"] = "coding"
    resource = "coding_registration_test"
    project = {"resource": resource, "name": "등록해제 시험", "path": "/example/project",
               "icon": "💻", "summary": "보존할 프로젝트", "status_label": ""}
    detail = {**project, "kind": "code", "goal_path": "/example/project/목표.md",
              "goal_exists": True, "run_command": "", "run_url": "", "log": "",
              "head": "1234567", "dirty": False, "changed": [], "active_task": None, "run": None}
    state = {"registered": True, "fail": True, "unregister_calls": 0, "list_reads": 0}

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT / "dist")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 850})
            errors = prepare_launcher(page, origin)

            def api(route):
                path = urlsplit(route.request.url).path
                if path == "/launcher/instruments":
                    payload = {"instruments": [manifest]}
                elif path == "/ibl/execute" and route.request.method == "POST":
                    request = route.request.post_data_json
                    code = request["code"]
                    if "unregister: true" in code:
                        assert request["inputs"]["resource"] == resource
                        state["unregister_calls"] += 1
                        if state["fail"]:
                            payload = {"success": False, "error": "등록 해제 저장 실패"}
                        else:
                            state["registered"] = False
                            payload = {"success": True, "unregistered": True, "closed": True}
                    elif "projects: true" in code:
                        state["list_reads"] += 1
                        payload = {"success": True, "kind": "code", "items": [project] if state["registered"] else []}
                    elif 'op: "open"' in code:
                        payload = {"success": True, **detail}
                    elif "project: true" in code:
                        payload = {"success": True, **detail}
                    else:
                        payload = {"success": True, "text": "# 보존할 목표\n", "fingerprint": "sample", "items": []}
                else:
                    route.fallback()
                    return
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload),
                              headers={"Access-Control-Allow-Origin": "*"})

            page.route("**/*", api)
            page.goto(origin + "/#/coding")
            page.get_by_text("💻 등록해제 시험", exact=True).click()
            page.get_by_title("프로젝트 도구", exact=True).click()
            button = page.get_by_role("button", name="등록 해제", exact=True)
            expect(button).to_be_visible()
            page.once("dialog", lambda dialog: dialog.dismiss())
            button.click()
            expect(button).to_be_enabled()
            assert state["unregister_calls"] == 0
            page.once("dialog", lambda dialog: dialog.accept())
            button.click()
            expect(page.get_by_text("등록 해제 저장 실패", exact=True)).to_be_visible()
            assert state["registered"]
            state["fail"] = False
            page.once("dialog", lambda dialog: dialog.accept())
            button.click()
            expect(page.get_by_text('아직 코딩 프로젝트가 없습니다 — "새 프로젝트" 에서 만들고 싶은 것을 말해 보세요.', exact=True)).to_be_visible()
            assert state["unregister_calls"] == 2 and state["list_reads"] >= 2
            page.reload()
            expect(page.get_by_text('아직 코딩 프로젝트가 없습니다 — "새 프로젝트" 에서 만들고 싶은 것을 말해 보세요.', exact=True)).to_be_visible()
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
