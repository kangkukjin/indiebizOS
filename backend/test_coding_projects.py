"""코딩 프로젝트(폴더 하나 = 프로젝트) 회귀 — docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md §2·§3.

실제 git·실제 파일. 목표 문서 틀·목록·읽기·직접 편집(제안/적용)·기록(커밋)·되돌리기·실행(샌드박스 프로세스)·
[self:workspace] 어댑터 계약·엔진 I/O(HTTP). 실행자(AI)는 여기 없다 — 위임 한 문장이라 모델 호출이 없다.
"""
import json
import os
import time
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from coding_git import CodingConflict, git
from coding_process import available
from coding_projects import GOAL_NAME, GOAL_SECTIONS, CodingProjects, goal_template, infer_goal, parse_goal
from coding_store import CodingStore
from runtime_utils import get_base_path
from workspace_sessions import Workspace


@pytest.fixture(autouse=True)
def no_delegation_lookup(monkeypatch):
    # 위임 원장(시스템 AI DB)은 시험이 건드리지 않는다 — 활성 위임은 없다고 본다.
    monkeypatch.setattr(CodingProjects, "_active_delegation", lambda self, row: None)


@pytest.fixture
def projects(tmp_path):
    return CodingProjects(CodingStore(tmp_path / "state"))


@pytest.fixture
def folder(tmp_path):
    p = tmp_path / "outputs" / "coding" / "사과-계산기"
    p.mkdir(parents=True)
    (p / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return p


def test_goal_template_roundtrip():
    text = goal_template("사과-계산기", {"무엇을 만드나": "사과 개수를 세는 작은 프로그램.", "실행 방법": "`python app.py` → http://localhost:5000"})
    g = parse_goal(text)
    assert g["summary"] == "사과 개수를 세는 작은 프로그램." and g["run_command"] == "python app.py" and g["run_url"] == "http://localhost:5000"
    assert parse_goal("# 📈 kospi — 코딩 목표\n\n## 무엇을 만드나\n\n현황판\n")["icon"] == "📈"
    assert parse_goal("")["summary"] == "" and parse_goal("")["run_command"] == ""


def test_open_initialises_git_and_goal_and_is_idempotent(projects, folder):
    row = projects.open(folder, goal="사과 개수를 세는 작은 프로그램.")
    assert (folder / ".git").is_dir() and (folder / GOAL_NAME).is_file()
    assert row["id"].startswith("coding_") and projects.open(folder)["id"] == row["id"]
    detail = projects.detail(row)
    assert detail["goal_exists"] and detail["summary"].startswith("사과 개수") and detail["dirty"] is True and detail["head"] == ""
    assert {f["path"] for f in projects.files(row)} == {"app.py", GOAL_NAME}


def _next_app(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "tetris-game", "private": True,
        "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
        "dependencies": {"next": "16.2.1", "react": "19.2.4"}}), encoding="utf-8")
    (root / "README.md").write_text("This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://x).\n\n## Getting Started\n", encoding="utf-8")
    return root


def test_import_without_goal_writes_inferred_goal(projects, tmp_path):
    app = _next_app(tmp_path / "tetris-game")
    projects.open(app)
    text = (app / GOAL_NAME).read_text(encoding="utf-8")
    assert all(f"## {s}" in text for s in GOAL_SECTIONS)
    g = parse_goal(text)
    assert g["run_command"] == "npm run dev" and g["run_url"] == "http://localhost:3000"
    assert g["summary"] == "This is a Next.js project bootstrapped with create-next-app."


def test_import_without_manifest_writes_placeholder_goal(projects, folder, tmp_path):
    bare = tmp_path / "빈폴더"
    bare.mkdir()
    (bare / "data.csv").write_text("a,b\n", encoding="utf-8")
    row = projects.open(bare)
    assert (bare / GOAL_NAME).read_text(encoding="utf-8") == goal_template("빈폴더")
    detail = projects.detail(row)
    assert detail["goal_exists"] and detail["run_command"] == "" and detail["run_url"] == "" and detail["summary"] == ""
    projects.open(folder)                       # app.py 만 있는 폴더 — 명령만, 주소는 추측하지 않는다
    g = parse_goal((folder / GOAL_NAME).read_text(encoding="utf-8"))
    assert g["run_command"] == "python3 app.py" and g["run_url"] == ""


def test_import_keeps_existing_goal_bytes_and_user_goal_wins(projects, tmp_path):
    app = _next_app(tmp_path / "있음")
    original = "# 내 문서\n\n손으로 쓴 목표 — 건드리지 마라.\n".encode("utf-8")
    (app / GOAL_NAME).write_bytes(original)
    projects.open(app, goal="덮어쓰면 안 됨")
    projects.open(app)
    assert (app / GOAL_NAME).read_bytes() == original
    other = _next_app(tmp_path / "새것")
    projects.open(other, goal="블록을 쌓는 게임")
    g = parse_goal((other / GOAL_NAME).read_text(encoding="utf-8"))
    assert g["summary"] == "블록을 쌓는 게임" and g["run_command"] == "npm run dev" and g["run_url"] == "http://localhost:3000"


@pytest.mark.parametrize("files, command, url", [
    ({"package.json": {"description": "할 일 목록", "scripts": {"dev": "vite --port 4000"}, "devDependencies": {"vite": "5"}},
      "yarn.lock": ""}, "yarn run dev", "http://localhost:4000"),
    ({"package.json": {"scripts": {"start": "node server.js"}}}, "npm start", ""),       # 프레임워크 밖 서버 — 주소 추측 안 함
    ({"package.json": {"scripts": {"dev": "next dev"}}}, "npm run dev", ""),           # next 의존성 없음 — 주소 추측 안 함
    ({"package.json": "{깨진 json"}, "", ""),
    ({"manage.py": ""}, "python manage.py runserver", "http://localhost:8000"),
    ({"requirements.txt": "streamlit\n", "app.py": ""}, "streamlit run app.py", "http://localhost:8501"),
    ({"index.html": "<html></html>"}, "python3 -m http.server 8000", "http://localhost:8000"),
])
def test_infer_goal_table(tmp_path, files, command, url):
    for name, content in files.items():
        (tmp_path / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    g = parse_goal(goal_template("x", infer_goal(tmp_path)))
    assert g["run_command"] == command and g["run_url"] == url


def test_projects_lists_registered_and_unregistered_folders(projects, folder, tmp_path):
    projects.open(folder, goal="하나")
    other = tmp_path / "outputs" / "coding" / "둘"
    other.mkdir()
    (tmp_path / "outputs" / "coding" / ".hidden").mkdir()
    items = projects.projects(root=tmp_path)
    names = [i["name"] for i in items]
    assert names[0] == "둘" or names[0] == "사과-계산기"
    assert set(names) == {"사과-계산기", "둘"}
    by = {i["name"]: i for i in items}
    assert by["사과-계산기"]["resource"] and by["사과-계산기"]["summary"] == "하나" and by["사과-계산기"]["icon"] == "💻"
    assert by["둘"]["resource"] is None and by["둘"]["summary"] == "목표 문서가 없습니다"


def test_edit_record_versions_and_restore(projects, folder):
    row = projects.open(folder, goal="기록 시험")
    first = projects.save(row, "프로젝트 만듦")
    assert first["state"] == "committed" and set(first["paths"]) == {"app.py", GOAL_NAME}
    assert projects.save(row, "다시")["state"] == "clean"
    p = projects.propose(row, {"path": "app.py", "start_line": 1, "end_line": 1}, "print('bye')")
    applied = projects.apply(row, p["proposal"])
    assert applied["applied"] and projects.read(row, {"path": "app.py"})["text"] == "print('bye')"
    with pytest.raises(CodingConflict):
        projects.apply(row, p["proposal"])          # 지문이 바뀐 뒤의 재적용은 거절
    diff = projects.diff(row)
    assert diff["paths"] == ["app.py"] and "+print('bye')" in diff["patch"]
    second = projects.save(row, "인사 바꿈")
    assert second["state"] == "committed" and second["commit"] != first["commit"]
    versions = projects.versions(row)
    assert [v["label"] for v in versions] == ["인사 바꿈", "프로젝트 만듦"]
    (folder / "new.txt").write_text("x", encoding="utf-8")      # 되돌리기 전 미기록 변경도 보관된다
    done = projects.restore(row, first["commit"])
    assert (folder / "app.py").read_text(encoding="utf-8") == "print('hi')\n" and done["kept"]
    labels = [v["label"] for v in projects.versions(row)]
    assert labels[0].startswith("되돌림: 프로젝트 만듦") and "되돌리기 전 상태 보관" in labels
    # 파일 하나만 되돌리기
    projects.apply(row, projects.propose(row, {"path": "app.py"}, "print('again')\n")["proposal"])
    projects.save(row, "또 바꿈")
    one = projects.restore(row, first["commit"], path="app.py")
    assert one["path"] == "app.py" and (folder / "app.py").read_text(encoding="utf-8") == "print('hi')\n"
    # 삭제 제안
    gone = projects.propose(row, {"path": "new.txt"}, None)
    assert gone["delete"] and projects.apply(row, gone["proposal"])["deleted"] and not (folder / "new.txt").exists()
    with pytest.raises(ValueError):
        projects.restore(row, "not-a-hash")


def test_self_repository_is_refused(projects):
    with pytest.raises(ValueError, match="자기 저장소"):
        projects.open(get_base_path())


@pytest.mark.skipif(not available(), reason="macOS 샌드박스 필요")
def test_run_streams_output_stops_and_reports_exit_code(projects, folder):
    row = projects.open(folder, goal="실행 시험")
    rec = projects.run(row, "printf started; sleep 30", serve=False)
    assert rec["state"] == "running"
    deadline = time.time() + 10
    while time.time() < deadline and "started" not in projects.output(rec["id"])["text"]:
        time.sleep(0.2)
    assert "started" in projects.output(rec["id"])["text"]
    stopped = projects.stop(rec["id"])
    assert stopped["state"] == "cancelled"
    done = projects.run(row, "echo out; exit 3")
    deadline = time.time() + 10
    while time.time() < deadline and projects.run_status(done["id"])["state"] == "running":
        time.sleep(0.2)
    final = projects.run_status(done["id"])
    assert final["state"] == "failed" and final["exit_code"] == 3 and "out" in projects.output(done["id"])["text"]
    assert projects.latest_run(row)["id"] == done["id"]
    outside = projects.run(row, f"touch {os.path.join(str(folder.parent), 'escape.txt')}")
    while projects.run_status(outside["id"])["state"] == "running":
        time.sleep(0.1)
    assert not (folder.parent / "escape.txt").exists()   # 샌드박스 — 프로젝트 밖 쓰기는 막힌다


def test_workspace_word_sees_projects_as_code_resources(tmp_path, folder):
    ws = Workspace(tmp_path / "state", coding_store=CodingStore(tmp_path / "cstate"))
    opened = ws.open(folder, goal="어댑터 시험")
    r = opened["resource"]
    assert opened["kind"] == "code" and opened["capabilities"]["restore"] is True and opened["capabilities"]["engine"] == "git"
    listing = ws.read(kind="code", selector={"projects": True}, root=tmp_path)
    assert listing["kind"] == "code" and listing["items"][0]["resource"] == r
    with pytest.raises(ValueError):
        ws.read(selector={"files": True})
    detail = ws.read(r, {"project": True})
    assert detail["goal_path"].endswith(GOAL_NAME) and detail["summary"] == "어댑터 시험"
    assert {f["path"] for f in ws.read(r)["items"]} == {"app.py", GOAL_NAME}
    saved = ws.save(r, message="첫 기록")
    assert saved["state"] == "committed"
    ws.apply(r, ws.propose(r, {"path": "app.py"}, replacement="print(1)\n")["proposal"])
    assert ws.read(r, {"diff": True})["paths"] == ["app.py"]
    ws.save(r, message="둘째")
    first = ws.versions(r)["items"][-1]["id"]
    back = ws.restore(r, first)
    assert back["restored"] == first and (folder / "app.py").read_text(encoding="utf-8") == "print('hi')\n"
    with pytest.raises(ValueError, match="message"):
        ws.save(r)
    assert ws.close(r)["closed"] is True


@pytest.mark.skipif(not available(), reason="macOS 샌드박스 필요")
def test_http_engine_io_run_output_stop(projects, folder, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_coding
    import principal
    monkeypatch.setattr(api_coding, "service", lambda: projects)
    monkeypatch.setattr(principal, "is_owner", lambda: True)
    row = projects.open(folder, goal="HTTP")
    app = FastAPI()
    app.include_router(api_coding.router)
    with TestClient(app) as client:
        receipt = client.post(f"/coding/projects/{row['id']}/run", json={"command": "printf hello; sleep 20"}).json()
        assert receipt["accepted"] and receipt["task_ref"]["kind"] == "coding_run" and receipt["state"] == "running"
        run_id = receipt["task_ref"]["task_id"]
        deadline = time.time() + 10
        text = ""
        while time.time() < deadline and "hello" not in text:
            text = client.get(f"/coding/runs/{run_id}", params={"offset": 0}).json()["text"]
            time.sleep(0.2)
        assert "hello" in text
        assert client.get(f"/coding/projects/{row['id']}/runs").json()["run"]["id"] == run_id
        assert client.post(f"/coding/runs/{run_id}/stop").json()["state"] == "cancelled"
        assert client.post(f"/coding/projects/{row['id']}/run", json={"command": "   "}).status_code == 400


def _essentials_workspace():
    import importlib.util
    import sys
    p = Path(get_base_path()) / "data/packages/installed/tools/system_essentials/essentials_workspace.py"
    if str(p.parent) not in sys.path:
        sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location("essentials_workspace", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_task_receipt_adapter_projects_run_state(projects, folder, monkeypatch):
    ew = _essentials_workspace()
    import task_receipts as T
    monkeypatch.setattr(ew, "_projects", lambda: projects)
    row = projects.open(folder, goal="접수증")
    rec = {"id": "run_fake", "project": row["id"], "command": "x", "state": "passed", "exit_code": 0, "output": str(folder / "none.log"),
           "started_at": 1.0, "finished_at": 2.0, "serve": False, "pid": 0}
    projects.store.save("run", rec)
    view = ew.coding_run_status(T.ref("coding_run", "run_fake", row["id"]))
    assert view["state"] == T.SUCCEEDED and view["terminal"] and view["result"]["exit_code"] == 0
    missing = ew.coding_run_status(T.ref("coding_run", "run_nope"))
    assert missing["state"] == T.UNKNOWN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
