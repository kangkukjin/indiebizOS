#!/usr/bin/env python3
"""seed_imagination_round_53.py — 53회차(축적 왕복) 시드 7건 (2026-09-02, 사용자 지시).

무엇을 가르치는가 (보고서 outputs/imagination_training/2026-09-02_53회차.md "시드 후보"):
  ① **쌓은 것을 되읽어 다음 문장의 통화로** — 장부 xlsx 를 `[self:sheet]{find}` 로 되읽어
     filter/sort/reduce 에 물리는 문형(축적 문형은 행동 지표 최저 2건 — 47회차가 검수만 했던 밭).
  ② **원장 안티조인** — `${본.items.*.f}` 열 벡터를 **구조형 where** `{field, op:"not_in", value}` 로
     (문자열 where 엔 JSON 이 박힌다 — F53-4).
  ③ **원장 누적 관용구** — `$본.items & (새 조회 >> …) >> union >> dedup{by} >> write{format:"json"}`
     (V53-1 ⓑ, 2026-09-02 사용자 판정: format:"json" 이 통화 보존 스위치).
  ④ **저장 스냅샷 대 현재** — 파일 변수 경로(`$전.items.0.f`)와 식 할당으로 델타 판정.
  ⑤ **효과 봉투 되먹임** — 이름으로 되읽은 `$b.items.0.id` 를 다음 쓰기의 인자로.

★시드는 교재다 — 전건 `/ibl/validate` 통과 + 스크래치 경로로 라이브 실행 검증(2026-09-02,
  B4·B2·I4b·L2·D2·C3c·A2b2 + 재검증 7/7). 경로는 일반 이름으로 바꿔 넣는다.

실행: .venv/bin/python scripts/seed_imagination_round_53.py   (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("장부 xlsx 에 없는 단지의 실거래만 골라 장부에 행으로 추가해줘",
     "$장부 = [self:sheet]{op: \"find\", path: \"실거래.xlsx\"}\n"
     "[sense:realty]{source: \"molit\", region: \"청주시 흥덕구\", type: \"apt\", deal: \"trade\"} >> [table:take]{n: 12} >> "
     "[table:filter]{where: {field: \"아파트명\", op: \"not_in\", value: \"${장부.items.*.아파트명}\"}} >> "
     "[self:sheet]{op: \"append\", path: \"실거래.xlsx\"}",
     "self,sense,table", "realty", "축적,되읽기,안티조인,구조형where,sheet_append"),
    ("장부에서 5억 넘는 거래만 비싼 순으로 보여줘",
     "[self:sheet]{op: \"find\", path: \"실거래.xlsx\"} >> [table:filter]{where: \"price > 500000000\"} >> [table:sort]{by: \"price\", desc: true}",
     "self,table", "realty", "축적,되읽기,sheet_find,filter,sort"),
    ("쌓아 둔 한 달 시세 시트에서 최고 종가 알려줘",
     "[self:sheet]{op: \"find\", path: \"시세이력.xlsx\", limit: 100} >> [table:reduce]{init: 0, step: \"max(acc, 종가)\", as: \"max_close\"}",
     "self,table", "invest", "축적,되읽기,sheet_find,reduce"),
    ("저장해 둔 시세 원장에 네이버 시세를 합쳐서 중복 없이 다시 저장해줘",
     "$본 = [self:read]{path: \"시세원장.json\"}\n"
     "$본.items & ([sense:stock]{op: \"quote\", ticker: \"035420\"} >> [table:select]{columns: [\"symbol\", \"name\", \"current_price\", \"change_percent\"]}) >> "
     "[table:union] >> [table:dedup]{by: \"symbol\"} >> [self:write]{path: \"시세원장.json\", format: \"json\"}",
     "self,sense,table", "invest", "축적,원장누적,변수병렬,union,dedup,format_json"),
    ("저장해 둔 시세와 지금 삼성전자 시세가 다르면 알려줘",
     "$전 = [self:read]{path: \"시세원장.json\"}\n"
     "$지금 = [sense:stock]{op: \"quote\", ticker: \"005930\"}\n"
     "$차 = $지금.items.0.current_price - $전.items.0.current_price\n"
     "[if: $차 != 0]{[self:notify_user]{message: \"삼성전자 저장 시세 대비 $차 원 변동\"}} [else]{[self:notify_user]{message: \"삼성전자 시세 변동 없음\"}}",
     "self,sense", "invest", "축적,되읽기,스냅샷,식할당,조건"),
    ("사업 원장에서 '구합니다' 사업을 찾아 새 상품을 붙여줘",
     "$b = [self:business]{store: \"business\", op: \"list\", search: \"구합니다\"}\n"
     "[self:business]{store: \"item\", op: \"save\", business_id: \"$b.items.0.id\", title: \"새 상품\"}",
     "self", "business", "축적,되읽기,ledger,id되먹임"),
    ("본 글 원장에 없는 긱뉴스 새 글만 골라줘",
     "$본 = [self:read]{path: \"본글원장.json\"}\n"
     "[sense:feed]{url: \"https://news.hada.io/rss/news\", limit: 8} >> [table:filter]{where: {field: \"url\", op: \"not_in\", value: \"${본.items.*.url}\"}}",
     "self,sense,table", "web", "축적,되읽기,안티조인,구조형where,열벡터"),
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
