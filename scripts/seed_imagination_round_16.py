#!/usr/bin/env python3
"""seed_imagination_round_16.py — 상상훈련 16회차 시드 (2026-08-20, 사용자 승인).

보고서 '시드 후보(실행 검증 통과만)' 7건 + material list op 신설 시드 3건(어휘 신설 선례).
★도서관+고전 병합은 F16-4 수리 후의 단순형(book title 병기로 rename 우회 불요)을 시드 —
  우회형을 가르치면 은퇴한 굽잇길이 코퍼스에 남는다.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    # ── 16회차 시드 후보 7건 ──
    ("내 웹앱 중 죽은 것만 골라줘",
     '[self:webapp]{op: "status"} >> [table:filter]{where: "alive == false"}',
     "self,table", "webapp", "생존,필터"),
    ("노트북마다 무슨 소스가 들었는지 보여줘",
     '[self:notebook]{op: "list"} >> [table:each]{do: "[self:notebook]{op: \'sources\', name: \'$it.title\'}"}',
     "self,table", "notebook", "적용,소스"),
    ("지금 내 위치 근처 칼국수집 찾아줘",
     '$위치 = [sense:here] ; [sense:restaurant]{query: "칼국수", x: "$위치.lng", y: "$위치.lat", radius: 3000, limit: 5}',
     "sense", "location", "변수,위치,맛집"),
    ("이 주제 조사해서 핵심 카드 이미지 한 장으로 만들어줘",
     '$카드 = [sense:search]{source: "naver", query: "오송 반도체 소부장", count: 5} >> [table:brief]{instruction: "핵심 3가지를 담은 HTML 카드 한 장 — <div> 마크업만"} ; [engines:render_html]{html: "$카드.message", output_path: "카드.png"}',
     "sense,table,engines", "media", "변수,AI종합,렌더"),
    ("도서관이랑 고전 원문에서 같이 찾아 중복 빼줘",
     '[sense:book]{query: "삼국지"} & [sense:classic]{query: "삼국지"} >> [table:union]{} >> [table:dedup]{by: "title"} >> [table:take]{n: 8}',
     "sense,table", "culture", "병렬,중복제거"),
    ("주택임대차보호법 찾아서 파일로 정리해둬",
     '[sense:legal]{query: "주택임대차보호법"} >> [table:take]{n: 3} >> [self:write]{path: "outputs/legal_요약.md"}',
     "sense,table,self", "legal", "축적,법령"),
    ("비트코인 10만불 넘으면 알려줘",
     '[if: sense:crypto{coin: "bitcoin"}.data.current_price_usd > 100000]{[self:notify_user]{message: "BTC 10만불 돌파"}}\n[else]{[self:time]}',
     "sense,self", "invest", "조건,알림"),
    # ── material list op 신설 시드 (V16-2 판정 집행) ──
    ("이 강의에 재료 뭐 들었어?",
     '[self:material]{op: "list", lecture_id: "ai-sahoeyi-jayulsingyeonggye"}',
     "self", "lecture", "재료,목록"),
    ("강의 재료 목록 보여줘",
     '[self:material]{op: "list", lecture_id: "ai-sahoeyi-jayulsingyeonggye"}',
     "self", "lecture", "재료,목록"),
    ("강의 재료 파일 두 개만 각각 읽어줘",
     '[self:material]{op: "list", lecture_id: "ai-sahoeyi-jayulsingyeonggye"} >> [table:take]{n: 2} >> [table:each]{do: "[self:read]{path: \'$it.path\'}"}',
     "self,table", "lecture", "재료,적용,읽기"),
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
