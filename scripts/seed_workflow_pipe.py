#!/usr/bin/env python3
"""seed_workflow_pipe.py — workflow run 파이프 시민화 조합 시드 (2026-08-17).

통화 조건 판정 A안(5fd44a2)으로 열린 새 문형: 저장 워크플로우가 >> 파이프와
&/?? 가지에 선다("이름 붙인 묶음이 곧 괄호"). 라이브 검증 완료 문형만 시드.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    ("저장해둔 죽백동전세 워크플로우 돌려서 상위 3개만 보여줘",
     '[self:workflow]{op: "run", name: "죽백동전세"} >> [table:take]{n: 3}',
     "self,table", "workflow", "파이프,저장본"),
    ("네이버 매물 워크플로우랑 직방 매물 워크플로우 같이 돌려서 합쳐줘",
     '[self:workflow]{op: "run", name: "네이버 매물"} & [self:workflow]{op: "run", name: "직방 매물"} >> [table:union]{}',
     "self,table", "workflow", "병렬가지,저장본,괄호"),
    ("주간보고 워크플로우 돌려서 결과를 엑셀로 만들어줘",
     '[self:workflow]{op: "run", name: "주간보고"} >> [table:spreadsheet]{}',
     "self,table", "workflow", "파이프,엑셀"),
    ("뉴스 요약 워크플로우 반도체로 돌려서 지난번 이후 새 것만",
     '[self:workflow]{op: "run", name: "뉴스 요약", params: {주제: "반도체"}} >> [table:since]{key: "반도체뉴스"}',
     "self,table", "workflow", "매개변수,검침,파이프"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"

import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
conn.close()

batch = [
    {"intent": i, "ibl_code": c, "nodes": n, "category": cat,
     "difficulty": 2, "source": "manual_seed", "tags": t}
    for i, c, n, cat, t in NEW if i not in existing
]
n_added = db.add_examples_batch(batch)
print(f"시드 추가: {n_added}건 (중복 스킵 {len(NEW) - len(batch)}건)")

dist_path = os.path.join(os.path.dirname(__file__), "..", "data", "training", "ibl_distilled.json")
with open(dist_path, encoding="utf-8") as f:
    dist = json.load(f)
have = {d.get("intent") for d in dist}
added = 0
for i, c, n, cat, t in NEW:
    if i not in have:
        dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                     "difficulty": 2, "source": "manual_seed"})
        added += 1
with open(dist_path, "w", encoding="utf-8") as f:
    json.dump(dist, f, ensure_ascii=False, indent=2)
print(f"ibl_distilled: +{added}건 → {len(dist)}건")
