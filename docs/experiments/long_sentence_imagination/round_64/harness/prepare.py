"""Recreate public input copies and an HTTP request; no remote work is performed."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pc", required=True)
    p.add_argument("--remote-root", required=True)
    p.add_argument("--tag", required=True, help="fresh namespace for receipts and remote folder")
    p.add_argument("--revision", default="a40b2414ebfc0d529317aafb166fb0dbd1d31ecf")
    args = p.parse_args()
    assets = {str(f.relative_to(HERE / "assets")).replace(".fixture.json", ".json"): f.read_text(encoding="utf-8")
              for f in (HERE / "assets").rglob("*") if f.is_file()}
    for name in ("vocabulary_state.py", "vocabulary_policy.py"):
        assets[name] = subprocess.check_output(
            ["git", "show", f"{args.revision}:backend/datastore/{name}"], cwd=ROOT).decode("utf-8")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in assets.items():
        path = args.out / "input" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    code = (HERE.parent / "drafts/main_v2.ibl").read_text(encoding="utf-8")
    code = code.replace("r64-trainer-", args.tag + "-")
    request = {"code": code, "edition": 2, "origin": "training", "project_id": "수동모드",
               "inputs": {"pc": args.pc, "rd": args.remote_root, "out": str(args.out),
                          "assets": [{"path": k, "content": v} for k, v in assets.items()]}}
    (args.out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
