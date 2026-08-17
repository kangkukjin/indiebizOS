#!/usr/bin/env python3
"""seed_workflow_params.py — workflow run params($변수 주입) 조합 문형 시드 (2026-08-17).

9711b2e(주입 구현)로 params 가 진짜가 됐는데 코퍼스에 params 문형이 0건 —
"곱셈 어휘 하나 + 조합 용례 N개 = 한 단위" 규칙의 집행. name 호출 문형은
기존 코퍼스에 이미 있어(run/get/delete name) 여기선 params 축만 심는다.
전 문형 라이브 검증: save($변수 do)→run(name+params 주입 실측)→delete 종단
+ 트리거 조합은 /ibl/validate dry-run 통과(2026-08-17).
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
★nodes=콤마 문자열. usage db·distilled 둘 다 intent 로 dedupe.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    # ── run: 이름 + params (새 문형의 핵심) ──
    ("주간보고 워크플로우 청주 버전으로 돌려줘",
     '[self:workflow]{op: "run", name: "주간보고", params: {지역: "청주"}}',
     "self", "workflow", "이름실행,매개변수"),
    ("아침 브리핑 워크플로우 서울 날씨로 실행해줘",
     '[self:workflow]{op: "run", name: "아침 브리핑", params: {도시: "서울"}}',
     "self", "workflow", "이름실행,매개변수"),
    ("시세 점검 워크플로우 삼성전자로 돌려",
     '[self:workflow]{op: "run", name: "시세 점검", params: {종목: "삼성전자"}}',
     "self", "workflow", "이름실행,매개변수"),
    ("월간 리포트 워크플로우 3월 청주 걸로 실행해줘",
     '[self:workflow]{op: "run", name: "월간 리포트", params: {월: "3", 지역: "청주"}}',
     "self", "workflow", "이름실행,매개변수,복수키"),
    # ── save: $변수 자리 있는 매개변수화 정의 ──
    ("지역만 바꿔 쓸 수 있게 부동산 브리핑을 워크플로우로 저장해줘",
     "[self:workflow]{op: \"save\", name: \"부동산 브리핑\", do: \"[sense:realty]{region: '$지역'} >> [table:take]{n: 5}\"}",
     "self,sense,table", "workflow", "저장,매개변수화"),
    ("검색어 받아 쓰는 뉴스 요약 워크플로우 만들어줘",
     "[self:workflow]{op: \"save\", name: \"뉴스 요약\", do: \"[sense:search]{source: 'gnews', query: '$주제'} >> [table:take]{n: 5}\"}",
     "self,sense,table", "workflow", "저장,매개변수화"),
    ("뉴스 요약 워크플로우 반도체 주제로 돌려줘",
     '[self:workflow]{op: "run", name: "뉴스 요약", params: {주제: "반도체"}}',
     "self", "workflow", "이름실행,매개변수"),
    # ── 시간 문형 조합: 트리거가 저장본을 params 와 함께 정기 실행 ──
    ("매일 아침 8시에 주간보고 워크플로우 청주로 돌려줘",
     "[self:trigger]{op: \"create\", name: \"아침 주간보고\", cron: \"0 8 * * *\", do: \"[self:workflow]{op: 'run', name: '주간보고', params: {지역: '청주'}}\"}",
     "self", "workflow", "트리거,시간문형,매개변수"),
    # ── 대조: 등록 스크립트는 id+args(stdin), 워크플로우는 name+params($변수) ──
    ("등록해둔 매출정리 스크립트 실행해줘",
     '[self:script]{op: "run", id: "매출정리"}',
     "self", "system", "스크립트,대조"),
    ("재고정리 스크립트에 창고 A 넘겨서 돌려줘",
     '[self:script]{op: "run", id: "재고정리", args: {창고: "A"}}',
     "self", "system", "스크립트,인자,대조"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"

import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
conn.close()

batch = [
    {"intent": i, "ibl_code": c, "nodes": n, "category": cat,
     "difficulty": 2 if any(x in c for x in (">>", "&", "??", "[if:", ";")) else 1,
     "source": "manual_seed", "tags": t}
    for i, c, n, cat, t in NEW if i not in existing
]
skipped = len(NEW) - len(batch)
n_added = db.add_examples_batch(batch)
print(f"시드 추가: {n_added}건 (중복 스킵 {skipped}건)")

# ibl_distilled 이관 (재학습 코퍼스)
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
