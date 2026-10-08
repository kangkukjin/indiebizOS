"""빌드된 실행 탭: 숫자 전송·IME·실패 재시도·빈 줄·종료/연결 상실. 업무 API는 합성."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import yaml
from playwright.sync_api import expect, sync_playwright

from launcher_browser import prepare_launcher
from test_coding_registration import ROOT


def test_run_input_retry_ime_empty_and_completion():
    manifest = yaml.safe_load((ROOT.parent / "data/instruments/coding.yaml").read_text())
    manifest["id"] = "coding"
    project = {"resource": "coding_input_test", "name": "사과 입력 시험", "path": "/example/apples",
               "icon": "💻", "summary": "입력 시험", "status_label": ""}
    run = {"id": "run_test", "command": "python3 app.py", "state": "running", "stdin": True,
           "started_at": 1791453600, "finished_at": None, "exit_code": None, "serve": False}
    detail = {**project, "kind": "code", "goal_path": "/example/apples/목표.md", "goal_exists": True,
              "run_command": run["command"], "run_url": "", "log": "", "head": "1234567",
              "dirty": False, "changed": [], "active_task": None, "run": run}
    state = {"fail": True, "inputs": [], "output": "사과 개수를 입력하세요: "}
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
                status = 200
                if route.request.method == "OPTIONS":
                    payload = {}
                elif path == "/launcher/instruments":
                    payload = {"instruments": [manifest]}
                elif path == "/ibl/execute":
                    code = route.request.post_data_json["code"]
                    if "projects: true" in code:
                        payload = {"success": True, "kind": "code", "items": [project]}
                    elif 'op: "open"' in code or "project: true" in code:
                        payload = {"success": True, **detail}
                    else:
                        payload = {"success": True, "text": "# 사과 입력 시험\n", "fingerprint": "test", "items": []}
                elif path == "/coding/runs/run_test":
                    offset = int(parse_qs(urlsplit(route.request.url).query).get("offset", [0])[0])
                    output = state["output"].encode("utf-8")
                    payload = {"run": run, "text": output[offset:].decode("utf-8"), "offset": len(output)}
                elif path == "/coding/runs/run_test/input":
                    value = route.request.post_data_json["text"]
                    state["inputs"].append(value)
                    if state["fail"]:
                        status, payload = 409, {"detail": "아직 입력을 읽지 않았습니다. 다시 보내세요."}
                    else:
                        payload = {"accepted": True}
                        if value == "3":
                            state["output"] += "사과 3개의 총 가격은 4,500원입니다."
                            run.update(state="passed", stdin=False, exit_code=0)
                else:
                    route.fallback()
                    return
                route.fulfill(status=status, content_type="application/json", body=json.dumps(payload),
                              headers={"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true",
                                       "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"})

            page.route("**/*", api)
            page.goto(origin + "/#/coding")
            page.get_by_text("💻 사과 입력 시험", exact=True).click()
            page.get_by_role("button", name="실행", exact=True).click()
            field = page.get_by_role("textbox", name="프로그램 입력", exact=True)
            send = page.get_by_role("button", name="입력 보내기", exact=True)
            expect(field).to_be_enabled()
            expect(page.locator("pre")).to_contain_text("사과 개수를 입력하세요")
            field.fill("사과")
            field.dispatch_event("keydown", {"key": "Enter", "isComposing": True})
            assert state["inputs"] == []
            field.press("Enter")
            expect(page.get_by_role("alert")).to_contain_text("다시 보내세요")
            expect(field).to_have_value("사과")
            state["fail"] = False
            field.press("Enter")
            expect(field).to_have_value("")
            expect(field).to_be_focused()
            with page.expect_response("**/coding/runs/run_test/input"):
                send.click()  # 빈 줄도 프로그램에 그대로 전달한다.
            expect(page.get_by_role("status")).to_contain_text("입력을 보냈습니다")
            assert state["inputs"] == ["사과", "사과", ""]
            run["stdin"] = False
            expect(field).to_be_disabled()
            expect(page.get_by_text("입력 연결이 없습니다. 중지한 뒤 다시 실행하세요.", exact=False)).to_be_visible()
            run["stdin"] = True
            expect(field).to_be_enabled()
            field.fill("3")
            field.press("Enter")
            expect(page.locator("pre")).to_contain_text("4,500원")
            expect(field).to_be_disabled()
            expect(send).to_be_disabled()
            assert state["inputs"] == ["사과", "사과", "", "3"]
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
