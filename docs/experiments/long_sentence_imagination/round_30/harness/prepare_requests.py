"""Build fresh trainer requests; use a new output directory for each replay."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOCS = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve()
source = out / "source"
(out / "runs").mkdir(parents=True, exist_ok=True)
for version in ("v0", "v1"):
    for label, teams in (("main", ["사진", "설치", "영상"]), ("variant", ["사진", "영상"])):
        payload = {
            "origin": "training", "project_path": str(ROOT), "agent_id": "LSI30_trainer",
            "task_id": "LSI30", "code": (DOCS / "drafts" / f"main_{version}.ibl").read_text(),
            "budget": {"steps": 1000000, "rows": 100000},
            "inputs": {"source": str(source), "out": str(out / "trainer" / f"{label}_{version}"),
                       "teams": teams, "paths": [str(source / t) for t in teams] +
                       [str(source / "안내.txt"), str(source / "사진/작품 01/설명.txt")]},
        }
        (out / f"{label}_{version}_request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
