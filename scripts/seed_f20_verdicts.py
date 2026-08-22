#!/usr/bin/env python3
"""seed_f20_verdicts.py — 20회차 판정 3건이 새로 참으로 만든 문형 시드 (2026-08-22).

무엇을 가르치는가 (판정 = docs/VOCAB_COMPOSABILITY_HANDOFF.md §20회차 판정 절):
  ① F20-3 **감시자 문형** — `>> [table:since] >> [table:brief]` 의 꼬리. 이 모양은
     수리 전까지 *첫 실행마다 error 로 끝났고*, 그래서 코퍼스에 거의 없다
     (08-21 재학습 잔여 실패 5건이 전부 since·ai·brief 였다 — 희소가 원인).
     0행이 정상인 문형이라 "없으면 없다고" 류 intent 도 함께 넣는다.
  ② F20-1 **변이별 열 이름** — 같은 `[sense:realty]` 라도 source 마다 뒷문장의 필드가
     다르다(naver=price·title / zigbang=distance_m / molit=거래금액·전용면적).
     카탈로그가 이제 변이별 ⟨열⟩ 을 인쇄하므로, 코퍼스도 그 사실을 실측 문장으로 가르친다.
  ③ F20-5 **무제목 알림** — `[self:notify_user]{message:}` 와 파이프 꼬리 `{}`.
     title 을 message 복붙으로 채우는 습관이 생기지 않게 *제목 없는* 문장만 넣는다.

★시드는 교재다 — 넣기 전에 전건 `/ibl/validate` 통과 + 부작용 없는 8건은 라이브 실행까지
  확인했다(그 과정에서 `[sense:stock]{symbols:}` 오문이 잡혔다 — validate 는 통과시키고
  런타임이 거절하는 부류라, 검증만으로는 못 거른다).

실행: .venv/bin/python3 scripts/seed_f20_verdicts.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("새 매물 나오면 요약해서 알려줘",
     "[sense:realty]{source: \"naver\", region: \"평택 비전동\", type: \"apt\", deal: \"trade\"} >> [table:since]{key: \"비전동매물\", by: \"url\"} >> [table:brief]{instruction: \"새로 나온 매물의 단지·가격 핵심만 3문장\"} >> [self:notify_user]{}",
     "sense,table,self", "realty", "감시자,since,brief,0행정상"),
    ("AI 뉴스 새 글만 골라서 세 줄로 요약해줘",
     "[sense:feed]{url: \"https://news.hada.io/rss/news\"} >> [table:since]{key: \"하다뉴스\"} >> [table:brief]{instruction: \"새 글 세 줄 요약\"}",
     "sense,table", "web", "감시자,since,brief,0행정상"),
    ("전세 시세 바뀐 매물만 요약해서 알려줘",
     "[sense:realty]{source: \"naver\", region: \"평택 비전동\", deal: \"rent\", lease: \"전세\"} >> [table:since]{key: \"비전동전세\", by: \"url\", watch: [\"price\"]} >> [table:brief]{instruction: \"값이 바뀐 매물만 한 줄씩\"} >> [self:notify_user]{}",
     "sense,table,self", "realty", "감시자,since,watch,brief"),
    ("매일 아침 새 채용 공고만 모아서 파일로 남겨줘",
     "[sense:search]{source: \"gnews\", query: \"평택 채용\"} >> [table:since]{key: \"평택채용\"} >> [table:brief]{instruction: \"새 공고 요지\"} >> [self:write]{path: \"채용_새공고.md\"}",
     "sense,table,self", "web", "감시자,since,brief,write"),
    ("폰에 새로 들어온 사진만 데스크탑에 복사해줘",
     "[self:photo]{source: \"usb\"} >> [table:since]{key: \"폰사진\", by: \"path\"} >> [self:copy]{dest: \"~/Desktop/폰사진\"}",
     "self,table", "photo", "감시자,since,copy,0행정상"),
    ("조건에 맞는 전세가 없으면 없다고만 해줘",
     "[sense:realty]{source: \"naver\", region: \"평택 비전동\", deal: \"rent\", lease: \"전세\", deposit_max: 15000} >> [table:brief]{instruction: \"조건에 맞는 전세를 요약하고, 없으면 없다고\"}",
     "sense,table", "realty", "0행정상,brief,빈손"),
    ("네이버부동산에서 3억 이하 아파트 매물만 싼 순으로 보여줘",
     "[sense:realty]{source: \"naver\", region: \"평택 비전동\", type: \"apt\", deal: \"trade\", limit: 30} >> [table:filter]{where: \"price <= 300000000\"} >> [table:sort]{by: \"price\"}",
     "sense,table", "realty", "변이열,naver,price,filter"),
    ("네이버 매물 호가 합계 내줘",
     "[sense:realty]{source: \"naver\", region: \"평택 비전동\", type: \"apt\", deal: \"trade\"} >> [table:reduce]{init: 0, step: \"acc + price\", as: \"총호가\"}",
     "sense,table", "realty", "변이열,naver,price,reduce"),
    ("직방 원룸 매물 가까운 순으로 다섯 개만",
     "[sense:realty]{source: \"zigbang\", region: \"평택 죽백동\", type: \"oneroom\", deal: \"rent\"} >> [table:sort]{by: \"distance_m\"} >> [table:take]{n: 5}",
     "sense,table", "realty", "변이열,zigbang,distance_m,sort"),
    ("강남구 아파트 실거래가로 평단가 계산해서 비싼 순으로",
     "[sense:realty]{op: \"query\", region: \"강남구\", type: \"apt\", deal: \"trade\"} >> [table:compute]{set: {\"평단가\": \"round(거래금액 / 전용면적, 1)\"}} >> [table:sort]{by: \"평단가\", desc: true}",
     "sense,table", "realty", "변이열,molit,거래금액,compute"),
    ("삼성전자 오늘 시세 한 줄로 알려줘",
     "[sense:stock]{ticker: \"삼성전자\"} >> [table:brief]{instruction: \"오늘 등락을 한 줄로\"} >> [self:notify_user]{}",
     "sense,table,self", "invest", "brief,notify,무제목"),
    ("정산 끝났다고 알림 하나 띄워줘",
     "[self:notify_user]{message: \"월간 정산 집계 완료 — 검토할 지출 3건\"}",
     "self", "system", "notify,무제목,제목파생"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단(★_index_batch 는 실패를 삼킨다)"
import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
conn.close()
batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
          "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
print(f"시드 추가: {db.add_examples_batch(batch)}건 (중복 스킵 {len(NEW) - len(batch)}건)")
dist_path = os.path.join(os.path.dirname(__file__), "..", "data", "training", "ibl_distilled.json")
with open(dist_path, encoding="utf-8") as f:
    dist = json.load(f)
have = {d.get("intent") for d in dist}
added = 0
for i, c, n, cat, t in NEW:
    if i not in have:
        dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2, "source": "manual_seed"})
        added += 1
with open(dist_path, "w", encoding="utf-8") as f:
    json.dump(dist, f, ensure_ascii=False, indent=2)
print(f"ibl_distilled: +{added}건 → {len(dist)}건")
