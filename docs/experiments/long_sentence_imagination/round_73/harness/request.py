"""훈련자 요청 봉투 생성 — 과제 단계는 구현하지 않는다."""
import argparse, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-15_73회차"
p = argparse.ArgumentParser()
p.add_argument("version"); p.add_argument("label"); p.add_argument("--executor", default="trainer")
p.add_argument("--check", action="store_true"); p.add_argument("--previous", default="")
p.add_argument("--tag", default="")
a = p.parse_args()
out = OUT / a.label
out.mkdir(parents=True, exist_ok=True)
payload = {
    "code": (HERE / f"{a.version}.ibl").read_text(encoding="utf-8"),
    "edition": 2, "origin": "training", "project_id": "study",
    "inputs": {
        "input": str(OUT / "inputs/sample.json"),
        "script": str(OUT / "inputs/process.py"),
        "out": str(out),
        "tag": a.tag or f"r73-{a.executor}-{a.label}",
        "remote_rel": f"indiebiz-training/fleet/73/{a.executor}",
        "phone_rel": f"outputs/long_sentence_imagination/round73/{a.executor}",
        "previous": str(Path(a.previous).resolve()) if a.previous else "",
    },
}
if a.check: payload["check"] = True
path = OUT / f"{a.label}-request.json"
path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print(path)
