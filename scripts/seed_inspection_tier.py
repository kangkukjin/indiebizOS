"""검수 비용 계층화 시딩 (2026-08-27, INSPECTION_COST_TIER Phase 6).

render 행의 prescreen(0층 기계 관측)을 critic 에 넘겨 걸린 화면은 비전 호출 없이
실패 처리하는 문형 — 직접 파이프 판 2건 + 장부 판 1건.

실행: .venv/bin/python3 scripts/seed_inspection_tier.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("이 페이지 검수하되 기계 관문에 걸린 화면은 비전 심사 없이 바로 실패 처리해줘",
     '[engines:render]{path: "index.html", viewports: ["1280x800", "390x844"]} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'페이지가 $it.label 폭에서 성립하는가\', criteria: \'web\', '
     'prescreen: \'$it.prescreen\'}"}',
     "engines,table", "pipeline", "검수,비용계층화,prescreen,critic"),
    ("Inspect this page but skip the paid vision check for screens that already failed the machine gate",
     '[engines:render]{path: "landing.html", viewports: ["1440x900", "390x844"]} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'landing page quality at $it.label\', criteria: \'web\', '
     'prescreen: \'$it.prescreen\'}"}',
     "engines,table", "pipeline", "검수,prescreen,english"),
    ("장부 렌더해서 쪽마다 심사하되 수식 오류나 빈 쪽은 비전 없이 걸러줘",
     '[engines:render]{op: "xlsx", path: "거래장부.xlsx"} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'장부 $it.page 쪽이 온전히 읽히는가\', criteria: \'sheet\', '
     'prescreen: \'$it.prescreen\'}"}',
     "engines,table", "pipeline", "검수,xlsx,prescreen,sheet기준"),
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
    print(f"ibl_distilled: +{added}건 -> {len(dist)}건")
