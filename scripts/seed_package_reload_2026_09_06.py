"""[self:package]{op:"reload"} 해마 시딩 (2026-09-06, ep2904 curl 우회 ×4 → 낱말 자리 신설).

★파이프라인 모양 + 대조 시드(list/install 영토 보존). ★.venv 파이썬 + _load_model_sync 후 색인.
실행: .venv/bin/python scripts/seed_package_reload_2026_09_06.py
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
import boot_paths  # noqa: F401

SEEDS = [
    {"intent": "패키지 handler.py 를 고쳤어, 실행기가 다시 읽게 해줘",
     "ibl_code": '[self:package]{op: "reload"}', "nodes": "self"},
    {"intent": "어휘 선언(ibl_actions.yaml)을 바꿨으니 새 사전을 읽게 리로드해줘",
     "ibl_code": '[self:package]{op: "reload"}', "nodes": "self"},
    {"intent": "패키지 캐시 초기화하고 뭐가 되살아났는지 알려줘",
     "ibl_code": '[self:package]{op: "reload"} >> [table:brief]{instruction: "reloaded 와 not_reloaded 를 두 줄로"}',
     "nodes": "self,table"},
    {"intent": "핸들러 수정 반영시키고 그 패키지 정보 다시 확인해줘",
     "ibl_code": '[self:package]{op: "reload"}\n[self:package]{op: "info", package_id: "web"}', "nodes": "self"},
    {"intent": "handler 고쳤는데 리로드해줘",
     "ibl_code": '[self:package]{op: "reload"}', "nodes": "self"},
    {"intent": "패키지 reload 해줘 (POST /packages/reload 대신)",
     "ibl_code": '[self:package]{op: "reload"}', "nodes": "self"},
    # 대조 — 기존 op 영토 보존
    {"intent": "설치된 패키지 목록 보여줘", "ibl_code": '[self:package]{op: "list"}', "nodes": "self"},
    {"intent": "house-designer 패키지 설치해줘",
     "ibl_code": '[self:package]{op: "install", package_id: "house-designer"}', "nodes": "self"},
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    db._load_model_sync()
    rows = [{"intent": s["intent"], "ibl_code": s["ibl_code"], "nodes": s["nodes"],
             "source": "manual_seed", "tags": "package-reload"} for s in SEEDS]
    print(f"add_examples_batch: {db.add_examples_batch(rows)}")
    p = os.path.join(_ROOT, "data", "training", "ibl_distilled.json")
    dist = json.load(open(p))
    existing = {(d.get("intent"), d.get("ibl_code")) for d in dist}
    added = 0
    for s in SEEDS:
        if (s["intent"], s["ibl_code"]) not in existing:
            dist.append({"intent": s["intent"], "ibl_code": s["ibl_code"]}); added += 1
    json.dump(dist, open(p, "w"), ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added} → {len(dist)}")
    for q in ["handler 고쳤는데 리로드해줘", "패키지 목록 보여줘"]:
        hits = db.search_hybrid(q, top_k=3)
        print(f"  Q: {q}\n     {[(getattr(h, 'ibl_code', '')[:50], round(getattr(h, 'score', 0) or 0, 3)) for h in hits[:3]]}")


if __name__ == "__main__":
    main()
