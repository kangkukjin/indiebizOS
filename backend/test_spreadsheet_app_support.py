"""스프레드시트 앱 브라우저 인수 시험의 공용 대역 — 시험 자체는 아래 계약 시험 하나뿐(test_spreadsheet_browser_live 가 쓴다).

앱 화면은 계기 선언(data/instruments/spreadsheet.yaml) 하나다. 격리 서버에는 그 선언을 내주는 길과 IBL 운반 길이
필요한데, 여기서는 운반만 대역으로 세운다: 빈 통합문서(랜딩)·열기는 시험이 준 작업 공간 서비스로 바로 잇고,
AI 작업창([table:ai])은 시험이 준 함수가 values 2차원으로 답한다. 격자 I/O·초안·저장·스냅샷·제안 적용은 진짜 /spreadsheets 경로가 받는다.
IBL 쪽 계약([self:workspace])은 test_workspace_sessions 가 따로 지킨다.
"""
import pytest
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def blank_workbook_bytes():
    from openpyxl import Workbook
    book = Workbook(); book.active.title = 'Sheet1'
    buffer = io.BytesIO(); book.save(buffer); return buffer.getvalue()


def mount_spreadsheet_app(app, workspace, folder, ai=None):
    import yaml
    manifest = yaml.safe_load((ROOT / "data/instruments/spreadsheet.yaml").read_text(encoding="utf-8"))
    instrument = {**manifest, "id": manifest["instrument"]}
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)

    @app.get("/launcher/instruments")
    def instruments():
        return {"version": 2, "instruments": [instrument]}

    @app.post("/ibl/execute")
    def execute(body: dict):
        code, inputs = body.get("code") or "", body.get("inputs") or {}
        if "[table:ai]" in code:
            if ai is None:
                return {"error": "이 시험은 AI 대역을 주지 않았습니다"}
            # 실서버의 판본 2 봉투와 같게(edition·success·value) — 표면은 이 셋이 있어야 value 를 푼다
            return {"edition": 2, "success": True, "source_complete": True, "value": {"items": [{"range": inputs.get("range"), "values": ai(inputs.get("dock"), inputs.get("table"))}]}}
        if "[self:workspace]" in code:
            try:
                if "[self:copy]" in code and not inputs.get("path"):   # 빈 통합문서(랜딩) — 빈 틀 복사 대역
                    path = folder / "무제.xlsx"
                    if not path.exists():
                        path.write_bytes(blank_workbook_bytes())
                else:
                    path = Path(inputs["path"])
                row = workspace.open(path)["document"]
            except Exception as exc:  # 화면이 보여 줄 거절 문장
                return {"error": str(exc)}
            return {"success": True, "resource": row["id"], "kind": "sheet", "title": row["title"]}
        return {"items": []}


def set_cell(page, address, text):
    """이름 상자로 셀을 고르고 수식 입력줄로 값을 넣는다 — 캔버스 좌표에 기대지 않는 결정적 입력."""
    box = page.get_by_label("이름 상자")
    box.fill(address); box.press("Enter")
    bar = page.get_by_label("수식 입력줄")
    bar.click(); bar.fill(text); bar.press("Enter")


def test_stub_follows_the_declared_modes(tmp_path):
    """대역이 선언에서 벗어나면 인수 시험이 엉뚱한 화면을 통과시킨다 — 랜딩·열기 모드와 AI 독의 계약을 여기서 묶는다."""
    import sys
    here = Path(__file__).resolve().parent
    for layer in ("datastore", "services", "surface"):
        sys.path.insert(0, str(here / layer))
    import yaml
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from spreadsheet_workspace import SpreadsheetWorkspace

    manifest = yaml.safe_load((ROOT / "data/instruments/spreadsheet.yaml").read_text(encoding="utf-8"))
    landing, opener = manifest["modes"][0], next(m for m in manifest["modes"] if m["name"] == "열기")
    assert landing["auto_run"] and not landing.get("inputs") and "[self:copy]" in landing["action"] and "[self:workspace]" in landing["action"]
    assert "[self:workspace]" in opener["action"] and "$path" in opener["action"] and {i["key"] for i in opener["inputs"]} == {"path"}
    canvas = landing["view"][0]
    assert canvas["type"] == "engine" and canvas["ref"] == "{resource}" and "[table:ai]" in canvas["ai_dock"]["action"] and "$table" in canvas["ai_dock"]["action"]

    app = FastAPI()
    mount_spreadsheet_app(app, SpreadsheetWorkspace(tmp_path / "office"), tmp_path / "sheets", ai=lambda dock, table: [[1, "=A1*2"]])
    client = TestClient(app)
    assert client.get("/launcher/instruments").json()["instruments"][0]["id"] == "spreadsheet"
    opened = client.post("/ibl/execute", json={"code": landing["action"], "inputs": {}, "edition": 2}).json()
    assert opened["kind"] == "sheet" and opened["resource"] and (tmp_path / "sheets/무제.xlsx").exists()
    again = client.post("/ibl/execute", json={"code": landing["action"], "inputs": {}, "edition": 2}).json()
    assert again["resource"] == opened["resource"]
    proposal = client.post("/ibl/execute", json={"code": canvas["ai_dock"]["action"], "inputs": {"range": "A1:B1", "table": [[1, None]], "dock": "x"}, "edition": 2}).json()
    assert proposal["value"]["items"][0]["values"] == [[1, "=A1*2"]]
    missing = client.post("/ibl/execute", json={"code": opener["action"], "inputs": {"path": str(tmp_path / "없음.xlsx")}, "edition": 2}).json()
    assert "error" in missing


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
