"""[self:body] op:commit 각인 굴절 시딩 (2026-08-27 신설).

수리→확인→각인의 조합 문형 위주 — 정본=docs/SELF_EVOLUTION_AUTOMATION_HANDOFF.md A-6.

실행: .venv/bin/python3 scripts/seed_body_commit.py
(system python3 은 sqlite_vec 가 없다 — .venv 필수)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:                       # 시딩은 라이브 원장에만 — 워크트리 사본 금지
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── 단문: 각인 ──
    ("방금 고친 백엔드 파일 두 개 커밋해줘",
     '[self:body]{op: "commit", message: "escape 처리 수리", paths: ["backend/ibl/ibl_parser.py", "backend/ibl/ibl_executor.py"]}',
     "self", "single", "commit,각인,수리"),
    ("가이드 문서 고친 거 원장에 기록해",
     '[self:body]{op: "commit", message: "가이드 갱신: body 각인 절", paths: ["data/guides/body.md"]}',
     "self", "single", "commit,각인,문서"),
    ("Commit the scheduler fix with a short message",
     '[self:body]{op: "commit", message: "scheduler tick guard fix", paths: ["backend/services/scheduler.py"]}',
     "self", "single", "commit,english"),
    # ── 조합: 확인→각인 (수리 마무리의 골격) ──
    ("지금 바뀐 줄 보고 나서 그 파일만 커밋하자",
     '[self:body]{op: "diff", path: "backend/cognition"} >> [self:body]{op: "commit", message: "인지층 수리", paths: ["backend/cognition/agent_pipeline.py"]}',
     "self", "pipeline", "commit,diff,조합"),
    ("수리 끝났으면 바뀐 파일 확인하고 각인까지 마무리해",
     '[self:body]{op: "changes", days: 1} >> [self:body]{op: "commit", message: "수리 마무리", paths: ["backend/ibl/ibl_safety.py"]}',
     "self", "pipeline", "commit,changes,마무리"),
]

if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 - 시딩 중단(_index_batch 는 실패를 삼킨다)"
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = ROOT / "data" / "training" / "ibl_distilled.json"
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    have = {d.get("intent") for d in dist}
    added = 0
    for i, c, n, cat, t in NEW:
        if i not in have:
            dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                         "difficulty": 2, "source": "manual_seed"})
            added += 1
    if added:
        with open(dist_path, "w", encoding="utf-8") as f:
            json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"distilled 동기: {added}건 추가")
