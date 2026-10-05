"""문서 앱 브라우저 인수 시험의 공용 대역 — 시험 자체는 없다(test_document_browser·hwp·office_live 가 쓴다).

문서 앱 화면은 계기 선언(data/instruments/document.yaml) 하나다. 격리 서버에는 그 선언을 내주는 길과
IBL 운반 길이 필요한데, 여기서는 운반만 대역으로 세운다: 열기는 시험이 준 작업 공간 서비스로 바로 잇고,
AI 한 줄([self:ask])은 시험이 준 함수가 답한다. 편집·초안·저장·버전은 진짜 /documents 경로가 받는다.
IBL 쪽 계약([self:workspace])은 test_workspace_sessions 가 따로 지킨다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mount_document_app(app, workspace, ask=None):
    import yaml
    manifest = yaml.safe_load((ROOT / "data/instruments/document.yaml").read_text(encoding="utf-8"))
    instrument = {**manifest, "id": manifest["instrument"]}

    @app.get("/launcher/instruments")
    def instruments():
        return {"version": 2, "instruments": [instrument]}

    @app.post("/ibl/execute")
    def execute(body: dict):
        code, inputs = body.get("code") or "", body.get("inputs") or {}
        if "[self:ask]" in code:
            if ask is None:
                return {"error": "이 시험은 AI 대역을 주지 않았습니다"}
            return {"result": ask(inputs.get("dock"), inputs.get("text"))}
        if "[self:workspace]" in code and "[self:write]" not in code and "$item" not in code:
            try:
                row = workspace.open(inputs["path"], inputs.get("encoding") or None)["document"]
            except Exception as exc:  # 화면이 보여 줄 거절 문장
                return {"error": str(exc)}
            return {"success": True, "resource": row["id"], "kind": "document", "title": row["title"]}
        return {"items": []}  # 문서함 목록 등 — 이 시험들이 보지 않는 길


def open_document(page, port, path, encoding=None, fresh=False):
    """열기 탭에서 경로로 문서를 연다. fresh 면 앱을 새로 띄운다(새로고침 뒤 다시 열기)."""
    if fresh or "#/documents" not in page.url:
        page.goto(f"http://127.0.0.1:{port}/#/documents")
        if fresh:
            page.reload()
    page.get_by_role("button", name="열기", exact=True).first.click()
    box = page.get_by_placeholder("문서 경로", exact=False)
    box.wait_for(timeout=10000)
    if encoding:
        page.locator("select").filter(has=page.locator("option[value='cp949']")).select_option(encoding)
    box.fill(str(path))
    box.press("Enter")


def test_stub_follows_the_declared_open_mode(tmp_path):
    """대역이 선언에서 벗어나면 인수 시험이 엉뚱한 화면을 통과시킨다 — 열기 모드의 계약을 여기서 묶는다."""
    import sys
    here = Path(__file__).resolve().parent
    for layer in ("datastore", "services", "surface"):
        sys.path.insert(0, str(here / layer))
    import yaml
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from document_workspace import DocumentWorkspace

    manifest = yaml.safe_load((ROOT / "data/instruments/document.yaml").read_text(encoding="utf-8"))
    mode = next(m for m in manifest["modes"] if m["name"] == "열기")
    assert "[self:workspace]" in mode["action"] and "$path" in mode["action"] and "$encoding" in mode["action"]
    assert {i["key"] for i in mode["inputs"]} == {"path", "encoding"}
    assert any(o["value"] == "cp949" for o in next(i for i in mode["inputs"] if i["key"] == "encoding")["options"])
    canvas = mode["view"][0]
    assert canvas["type"] == "engine" and canvas["ref"] == "{resource}" and "[self:ask]" in canvas["ai_dock"]["action"]

    app = FastAPI()
    mount_document_app(app, DocumentWorkspace(tmp_path / "workspace"), ask=lambda dock, text: f"{dock}:{text}")
    client = TestClient(app)
    assert client.get("/launcher/instruments").json()["instruments"][0]["id"] == "document"
    source = tmp_path / "메모.txt"
    source.write_text("본문", encoding="utf-8")
    opened = client.post("/ibl/execute", json={"code": mode["action"], "inputs": {"path": str(source), "encoding": ""}}).json()
    assert opened["kind"] == "document" and opened["resource"]
    missing = client.post("/ibl/execute", json={"code": mode["action"], "inputs": {"path": str(tmp_path / "없음.txt")}}).json()
    assert missing.get("error")
    asked = client.post("/ibl/execute", json={"code": canvas["ai_dock"]["action"], "inputs": {"dock": "고쳐", "text": "글"}}).json()
    assert asked == {"result": "고쳐:글"}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
