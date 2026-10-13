#!/usr/bin/env python3
"""Build a resumable IndieBiz source-update plan on the target PC.

Needs Git, supported Python and Node/npm already installed. No credentials or
runtime installers are downloaded implicitly. The generic executor is remote_steps.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: F401,E402

import argparse
from datetime import datetime
import json
import os
import shutil
import subprocess
import uuid


def git(root, *args):
    out = subprocess.check_output(["git", "-C", str(root), *args], text=True)
    return out if "-z" in args else out.strip()


def backup_root(root):
    path = root / "data" / "_backups" / (datetime.now().strftime("%Y-%m-%d_") + "remote_update_" + uuid.uuid4().hex[:12])
    path.mkdir(parents=True)
    return path


def update(root):
    """Fast forward only; preserve colliding local files, never reset/clean/stash."""
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked local changes exist; resolve before update")
    before = git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(root), "fetch", "origin"], check=True)
    target = git(root, "rev-parse", "origin/main")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", before, target]).returncode:
        raise ValueError("Local history diverges from origin/main; no automatic merge")
    # Include ignored files: Git may silently overwrite those on fast-forward.
    tracked = set(git(root, "ls-files", "-z").split("\0")) - {""}
    incoming = set(git(root, "ls-tree", "-r", "--name-only", "-z", target).split("\0")) - {""}
    collisions = set()
    for name in incoming - tracked:
        path = Path(name)
        for relative in [*reversed(path.parents), path]:
            if str(relative) == ".":
                continue
            source = root / relative
            if source.is_symlink() or (source.exists() and (relative == path or not source.is_dir())):
                text = relative.as_posix()
                if text in tracked or any(p.startswith(text + "/") for p in tracked):
                    raise ValueError(f"Tracked path obstructs update: {text}")
                collisions.add(text)
                break
    collisions = sorted(collisions)
    backup = None
    for name in collisions:
        source = root / name
        if backup is None:
            backup = backup_root(root)
            print(json.dumps({"backup": str(backup), "status": "preserving"}), flush=True)
        destination = backup / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        print(json.dumps({"preserved": name, "destination": str(destination)}), flush=True)
    subprocess.run(["git", "-C", str(root), "merge", "--ff-only", target], check=True)
    after = git(root, "rev-parse", "HEAD")
    print(json.dumps({"before": before, "target": target, "after": after,
                      "backup": str(backup) if backup else None, "preserved": collisions}))
    if after != target:
        raise ValueError("HEAD does not match the fetched target")


def reconcile_packages(root):
    """Retain tracked package locations; quarantine only wholly untracked duplicates."""
    packages = root / "data" / "packages"
    installed, sleeping = packages / "installed/tools", packages / "not_installed/tools"
    if not installed.is_dir() or not sleeping.is_dir():
        return
    moves = []
    for name in sorted(set(p.name for p in installed.iterdir()) & set(p.name for p in sleeping.iterdir())):
        pair = [installed / name, sleeping / name]
        if not all(p.is_dir() and not p.is_symlink() for p in pair):
            raise ValueError(f"Ambiguous duplicate package: {name}")
        tracked = [bool(git(root, "ls-files", "--", str(p.relative_to(root)))) for p in pair]
        if sum(tracked) != 1:
            raise ValueError(f"Cannot choose canonical package location: {name}")
        moves.append(pair[tracked.index(False)])
    if not moves:
        return
    backup = backup_root(root)
    print(json.dumps({"backup": str(backup), "status": "preserving_packages"}), flush=True)
    for source in moves:
        destination = backup / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
    print(json.dumps({"backup": str(backup), "preserved": [str(p) for p in moves]}))


def make_plan(root, run_id, python, npm):
    root = root.resolve()
    script = str(root / "scripts" / "remote_install.py")
    vpy = str(root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3"))
    env = {"PATH": str(Path(npm).parent) + os.pathsep + os.environ.get("PATH", ""),
           "PIP_NO_INPUT": "1", "GIT_TERMINAL_PROMPT": "0"}
    steps = []

    def step(name, argv, verify=None, cwd=None, timeout=3600):
        row = {"id": name, "argv": argv, "timeout": timeout}
        if verify:
            row["verify"] = verify
        if cwd:
            row["cwd"] = str(cwd)
        steps.append(row)

    step("preflight", [python, script, "preflight", "--root", str(root), "--npm", npm])
    step("update", [python, script, "update", "--root", str(root)],
         [python, script, "verify-head", "--root", str(root)])
    step("packages", [python, script, "packages", "--root", str(root)])
    step("venv", [python, script, "venv", "--root", str(root)],
         [vpy, "-c", "import sys; assert (3,10) <= sys.version_info[:2] < (3,14)"])
    for name in ("core", "tools", "ml"):
        step(name, [vpy, "-m", "pip", "install", "-r", str(root / "backend" / f"requirements-{name}.txt")], timeout=7200)
    step("browser", [vpy, str(root / "scripts/check_playwright_browsers.py"), "--install"],
         [vpy, str(root / "scripts/check_playwright_browsers.py")])
    for name, args in (("npm-ci", ["ci", "--no-audit", "--no-fund"]),
                       ("native-rebuild", ["run", "rebuild-trusted"]), ("frontend-build", ["run", "build"])):
        step(name, [npm, *args], cwd=root / "frontend")
    step("imports", [vpy, str(root / "scripts/check_import_coverage.py")])
    step("pip-check", [vpy, "-m", "pip", "check"])
    step("head-check", [python, script, "verify-head", "--root", str(root)])
    return {"version": 1, "run_id": run_id, "cwd": str(root), "env": env, "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("op", choices=["plan", "preflight", "update", "packages", "verify-head", "venv"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--npm", default=shutil.which("npm") or "")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.op == "plan":
            if not args.output or not args.run_id or not Path(args.npm).is_absolute():
                raise ValueError("--output, --run-id and absolute --npm required")
            plan = make_plan(root, args.run_id, sys.executable, args.npm)
            from remote_steps import validate
            validate(plan)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(plan, stream, ensure_ascii=False, indent=2)
        elif args.op == "preflight":
            if not (3, 10) <= sys.version_info[:2] < (3, 14):
                raise ValueError("Install Python 3.10..3.13 first")
            if not (root / "scripts/bootstrap.py").is_file():
                raise ValueError("Not an IndieBiz source checkout")
            if git(root, "status", "--porcelain", "--untracked-files=no"):
                raise ValueError("Tracked local changes exist")
            subprocess.run([args.npm, "--version"], check=True)
            node = shutil.which("node", path=str(Path(args.npm).parent))
            if not node:
                raise ValueError("Node must be beside npm; provision the runtime first")
            version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
            parts = tuple(int(p) for p in version.split("."))
            if not ((20, 19, 0) <= parts < (21, 0, 0) or parts >= (22, 12, 0)):
                raise ValueError("Node does not meet the current Vite runtime requirement")
            vpy = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
            if vpy.exists():
                subprocess.run([str(vpy), "-c", "import sys; assert (3,10) <= sys.version_info[:2] < (3,14)"], check=True)
        elif args.op == "update":
            update(root)
        elif args.op == "packages":
            reconcile_packages(root)
        elif args.op == "venv":
            vpy = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
            if not vpy.exists():
                if (root / ".venv").exists():
                    raise ValueError("Existing venv is incomplete; inspect it before replacement")
                subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
        else:
            head, target = git(root, "rev-parse", "HEAD"), git(root, "rev-parse", "origin/main")
            print(json.dumps({"head": head, "target": target, "matches": head == target}))
            if head != target:
                raise ValueError("HEAD differs from fetched origin/main")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
