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
    ".gitignore",
    "backend/api.py", "backend/datastore/document_store.py",
    "backend/services/document_workspace.py", "backend/surface/api_documents.py",
    "backend/test_document_workspace.py", "backend/test_document_browser.py",
    "frontend/electron/windows.js", "frontend/src/App.tsx",
    "frontend/src/components/ActionDesktop.tsx", "frontend/src/components/DocumentWorkspace.tsx",
    "frontend/src/components/document-workspace.css", "frontend/src/lib/api-documents.ts",
    "frontend/src/lib/surface-navigation.ts", "frontend/src/types/index.ts",
    "scripts/check_backend_layers.py", "scripts/verify_document_workspace.py",
    "data/bodies/android.engine.json", "frontend/i18n/catalog.json", "frontend/i18n/translations.json",
    "data/system_docs/system_structure.md", "data/system_docs/architecture.md",
    "data/system_docs/technical.md",
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


def main():
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
                    "Add isolated source document workspace with safe copy saves", "--", *FILES], timeout=600))
    result = {"ok": all(r["ok"] for r in rows), "release_complete": False, "items": rows}
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get("INDIEBIZ_SCRIPT_RESULT"):
        Path(os.environ["INDIEBIZ_SCRIPT_RESULT"]).write_text(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
