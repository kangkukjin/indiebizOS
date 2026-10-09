"""Repair the two stale deck-video examples found by the contract review; idempotent."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_usage_db import DB_PATH, IBLUsageDB  # noqa: E402

REPLACEMENTS = {
    "강의 동영상 렌더 다 됐는지 확인해줘":
        '[self:deck]{op: "video", lecture_id: "<강의 ID>", check: true}',
    "남자 목소리로 강의 영상 다시 만들어줘":
        '[self:deck]{op: "video", lecture_id: "<강의 ID>", engine: "edge", voice: "ko-KR-InJoonNeural"}',
}


def main():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, intent, ibl_code FROM ibl_examples").fetchall()
    stale = [r for r in rows if r[1] in REPLACEMENTS and r[2] != REPLACEMENTS[r[1]]]
    present = {(r[1], r[2]) for r in rows}
    fresh = [{"intent": intent, "ibl_code": code, "nodes": "self",
              "source": "synthetic", "tags": "lecture_workspace,video"}
             for intent, code in REPLACEMENTS.items() if (intent, code) not in present]
    if stale or fresh:
        backup = ROOT / "data/_backups/2026-10-09_round42_repair"
        backup.mkdir(parents=True, exist_ok=True)
        saved = backup / "stale_deck_examples.json"
        if not saved.exists():
            saved.write_text(json.dumps(stale, ensure_ascii=False, indent=2))
        db = IBLUsageDB()
        assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
        assert db.add_examples_batch(fresh) == len(fresh)
        db._delete_examples([r[0] for r in stale])
    corpus = ROOT / "data/training/ibl_distilled.json"
    examples = json.loads(corpus.read_text())
    for row in examples:
        if row.get("intent") in REPLACEMENTS:
            row["ibl_code"] = REPLACEMENTS[row["intent"]]
    known = {r.get("intent") for r in examples}
    examples += [{"intent": i, "ibl_code": c} for i, c in REPLACEMENTS.items() if i not in known]
    corpus.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"replaced": len(stale), "added": len(fresh)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
