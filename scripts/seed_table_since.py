#!/usr/bin/env python3
"""seed_table_since.py — [table:since] 검침 변환자 조합 시드 (2026-08-17).

since 신설(145 액션)과 한 몸 — "곱셈 어휘 하나 + 조합 용례 N개 = 한 단위":
since 는 N개 items 생산자에 곱해지는 시간 차분이라, 시드도 생산자별 조합으로 심는다
(feed·search·realty·used·stock + watch 축 + 트리거 시간 문형).
라이브 검증(2026-08-17): items 직접·실 RSS 파이프에서 seed/new/changed/peek/거절
전 계약 통과 + 트리거 조합 /ibl/validate step_count 5(재귀 펼침).
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
★nodes=콤마 문자열. usage db·distilled 둘 다 intent 로 dedupe.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    # ── 생산자 × since 조합 ──
    ("긱뉴스 피드에서 지난번 이후 새 글만 보여줘",
     '[sense:feed]{url: "https://news.hada.io/rss/news"} >> [table:since]{key: "하다뉴스"}',
     "sense,table", "web", "검침,피드,새것"),
    ("AI 규제 뉴스 새로 나온 것만 알려줘",
     '[sense:search]{source: "gnews", query: "AI 규제"} >> [table:since]{key: "AI규제뉴스"}',
     "sense,table", "web", "검침,검색,새것"),
    ("죽백동에 새 전세 매물 떴는지 봐줘",
     '[sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [table:since]{key: "죽백동전세"}',
     "sense,table", "realty", "검침,매물,새것"),
    ("당근에 자전거 새 매물만 보여줘",
     '[sense:used]{source: "danggeun", q: "자전거"} >> [table:since]{key: "자전거중고"}',
     "sense,table", "shopping", "검침,중고,새것"),
    ("크몽에 로고 디자인 새 서비스 올라온 것만",
     '[sense:freelance]{source: "kmong", query: "로고 디자인"} >> [table:since]{key: "로고외주"}',
     "sense,table", "shopping", "검침,외주,새것"),
    # ── watch 축: 값 변화 감시 ──
    ("관심 매물 가격 변동 있으면 알려줘",
     '[sense:realty]{source: "zigbang", region: "죽백동", type: "villa"} >> [table:since]{key: "죽백동빌라", watch: ["price"]}',
     "sense,table", "realty", "검침,가격변동"),
    ("다나와 그래픽카드 가격 바뀐 것만 보여줘",
     '[sense:search_shopping]{query: "RTX 4070"} >> [table:since]{key: "그래픽카드가격", watch: ["price"]}',
     "sense,table", "shopping", "검침,가격변동"),
    # ── 트리거 시간 문형: 정기 감시가 한 문장 ──
    ("매일 아침 9시에 긱뉴스 새 글 있으면 알려줘",
     "[self:trigger]{op: \"create\", name: \"하다 새 글 감시\", cron: \"0 9 * * *\", do: \"[sense:feed]{url: 'https://news.hada.io/rss/news'} >> [table:since]{key: '하다뉴스'} >> [table:each]{do: '[self:notify_user]{message: $it.title}'}\"}",
     "self,sense,table", "time", "검침,트리거,감시"),
    # ── peek + by 명시 ──
    ("기준선 안 올리고 새 글 뭐 있는지 미리 봐줘",
     '[sense:feed]{url: "https://news.hada.io/rss/news"} >> [table:since]{key: "하다뉴스", peek: true}',
     "sense,table", "web", "검침,미리보기"),
    ("통계 목록에서 지난번 이후 새로 생긴 것만, 이름 기준으로",
     '[sense:kosis]{query: "인구"} >> [table:since]{key: "인구통계", by: "title"}',
     "sense,table", "stats", "검침,식별필드"),
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
