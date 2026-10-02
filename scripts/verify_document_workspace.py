#!/usr/bin/env python3
"""Verify the implemented source workspace subset, never full document release.

--prepare regenerates derived manifests and runs the registered gate runner.
--active runs source/browser regressions and commits only this change's paths.
The complete Office/Hancom/PDF acceptance criteria remain open.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

FILES = [
    "backend/services/document_workspace.py", "backend/surface/api_documents.py",
    "backend/test_document_workspace.py", "backend/test_document_browser.py",
    "frontend/src/components/DocumentWorkspace.tsx", "scripts/verify_document_workspace.py",
    "data/bodies/android.engine.json", "frontend/i18n/catalog.json", "frontend/i18n/translations.json",
]


def command(argv, stdin=None, timeout=240):
    run = subprocess.run(argv, input=stdin, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return {"argv": argv, "exit_code": run.returncode, "ok": run.returncode == 0,
            "output": run.stdout + run.stderr}


def registered(filename, args):
    row = command([sys.executable, str(ROOT / "data/scripts" / filename)], json.dumps(args))
    if row["ok"]:
        # Registered runners report test/gate failures as JSON, not exit codes.
        output = row["output"]
        # stderr progress is appended after the stdout JSON by command().
        value, _ = json.JSONDecoder().raw_decode(output.lstrip())
        row["result"] = value
        row["ok"] = value.get("ok", False)
    return row


def live_probe(origin="http://127.0.0.1:8765", root=None):
    """Fast post-restart behavior check; commit/test batteries run separately.

    Keep the apply controller's 180-second deadline separate from a commit
    hook's execution time. These are synthetic app fixtures, not user files.
    """
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from uuid import uuid4
    import hashlib

    def request(route, body=None):
        payload = None if body is None else json.dumps(body).encode()
        req = Request(origin + "/documents" + route, data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    folder = (root or ROOT) / "data/document_workspace/verification"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("source-save-" + uuid4().hex + ".txt")
    path.write_text("원본 문장", encoding="utf-8")
    d = request("/open", {"path": str(path)})["document"]
    detail = request("/" + d["id"] + "/sessions", {"args": {"client_id": "verify-" + uuid4().hex}})
    s = detail["session"]

    def command(op, extra):
        args = {"session_id": s["id"], "client_id": s["client_id"], "epoch": s["engine_epoch"],
                "expected": s["session_revision"], **extra}
        return request("/" + d["id"] + "/" + op, {"args": args})

    s = command("draft", {"operation_id": "probe-draft", "text": "미저장 초안"})["session"]
    snap = command("snapshots", {})
    p = request("/" + d["id"] + "/proposals", {"args": {
        "snapshot_id": snap["id"], "start": 0, "end": 3,
        "selected_sha256": hashlib.sha256("미저장".encode()).hexdigest(), "replacement": "수정한"}})
    s = command("apply", {"operation_id": "probe-apply", "proposal_id": p["id"]})["session"]
    save_args = {"operation_id": "probe-save", "expected_revision": d["revision_id"]}
    result = command("save", save_args)
    assert result["state"] == "saved" and path.read_text(encoding="utf-8") == "수정한 초안"
    assert command("save", save_args) == result
    assert len(request("/" + d["id"] + "/versions")["items"]) == 2
    s = command("draft", {"operation_id": "probe-later", "text": "보존할 초안"})["session"]
    path.write_text("외부 수정", encoding="utf-8")
    try:
        command("save", {"operation_id": "probe-conflict", "expected_revision": result["revision_id"]})
    except HTTPError as exc:
        assert exc.code == 409
    else:
        raise AssertionError("외부 수정 충돌이 거절되지 않았습니다")
    assert path.read_text(encoding="utf-8") == "외부 수정"
    assert request("/" + d["id"])["text"] == "보존할 초안"
    return {"ok": True, "release_complete": False, "live_source_save": True,
            "snapshot_proposal": True, "duplicate_save": True, "external_conflict": True,
            "document_id": d["id"], "fixture": str(path), "scope": "source service; not live UI or Office engines"}


def main():
    if "--live-only" in sys.argv:
        result = live_probe()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    active = "--active" in sys.argv
    rows = []
    if active:
        branch = command(["git", "branch", "--show-current"])
        if branch["output"].strip() != "main":
            raise RuntimeError("정본 main에서만 각인합니다")
        # 문서 통계는 git 추적 목록에서 파생되므로 신규 파일을 먼저 등록한다.
        rows.append(command(["git", "add", "--", *FILES]))
    if all(r["ok"] for r in rows):
        rows.append(command([sys.executable, "scripts/build_ibl_nodes.py"]))
    if all(r["ok"] for r in rows):
        rows.append(command([sys.executable, "scripts/build_body_bundle.py", "android"]))
    if rows[-1]["ok"]:
        rows.append(registered("빌드검증.py", {"gates": ["build", "layers", "size", "paths"]}))
    if active and all(r["ok"] for r in rows):
        rows.append(registered("시험.py", {"files": ["backend/test_document_workspace.py",
            "backend/test_document_browser.py", "backend/test_document_sheet_transit_2026_09_15.py"]}))
        if all(r["ok"] for r in rows):
            from urllib.request import urlopen
            with urlopen("http://127.0.0.1:8765/documents", timeout=15) as response:
                state = json.load(response)
            rows.append({"ok": state.get("release_complete") is False and isinstance(state.get("items"), list),
                         "live_api": "/documents", "release_complete": False})
        if all(r["ok"] for r in rows):
            branch = command(["git", "branch", "--show-current"])
            if branch["output"].strip() != "main":
                raise RuntimeError("정본 main에서만 각인합니다")
            rows.append(command(["git", "add", "--", *FILES]))
            if rows[-1]["ok"]:
                rows.append(command(["git", "commit", "--only", "-m",
                    "Add conditional source saves and snapshot-bound AI proposals", "--", *FILES], timeout=600))
    result = {"ok": all(r["ok"] for r in rows), "release_complete": False, "items": rows}
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get("INDIEBIZ_SCRIPT_RESULT"):
        Path(os.environ["INDIEBIZ_SCRIPT_RESULT"]).write_text(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
