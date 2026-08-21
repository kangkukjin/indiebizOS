#!/usr/bin/env python3
"""seed_program_grade_m6.py — M6 조합 시드 (2026-08-22): 식 할당·while 카운터·블록-인-파이프·$return.
실행: .venv/bin/python3 scripts/seed_program_grade_m6.py  (★_load_model_sync 뒤 add, intent dedupe)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    ("AI 뉴스 새 글이 더 안 나올 때까지 페이지 넘기며 전부 저장해줘",
     '$n = 0\n[repeat: while $n < 10, max: 10]{$n = $n + 1\n[sense:feed]{url: "https://news.hada.io/rss/news?page=$n"} >> [table:since]{key: "AI뉴스"} >> [if: empty($items)]{[self:notify_user]{message: "$n 페이지에서 새 글 끝"}} [else]{[self:write]{path: "ai_news_$n.json"}}}',
     "sense,table,self", "web", "while,카운터,블록인파이프,페이지"),
    ("매물이 10개 넘으면 상위 10개만, 아니면 전부 스프레드시트로",
     '[sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [if: count($items) > 10]{[table:take]{n: 10}} [else]{[table:sort]{by: "price"}} >> [table:spreadsheet]{path: "죽백동_전세.xlsx"}',
     "sense,table", "realty", "블록인파이프,조건,스프레드시트"),
    ("전세 보증금 평균 구해서 2억 넘으면 알려줘",
     '$t = [sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [table:reduce]{init: 0, step: "acc + 보증금"}\n$avg = $t.value / $t.reduced_rows\n[if: $avg > 20000]{[self:notify_user]{message: "평균 보증금 $avg 만원 — 2억 초과"}} [else]{[self:notify_user]{message: "평균 보증금 $avg 만원"}}',
     "sense,table,self", "realty", "식할당,reduce,조건,평균"),
    ("검색 결과가 비면 소스를 바꿔 한 번 더 찾고 그래도 없으면 알려줘",
     '[sense:search]{source: "gnews", query: "청주 스타트업"} >> [if: empty($items)]{[sense:search]{source: "naver", query: "청주 스타트업"}} >> [if: empty($items)]{[self:notify_user]{message: "청주 스타트업 기사 없음"}} [else]{[table:brief]{instruction: "3문장 요지"} >> [self:notify_user]{}}',
     "sense,table,self", "web", "블록인파이프,empty,재시도"),
    ("시도 횟수 세면서 크롤링 3번까지 재시도해줘",
     '$tries = 0\n$ok = 0\n[repeat: while $ok == 0 and $tries < 3, max: 3]{$tries = $tries + 1\n[try]{[sense:crawl]{url: "https://example.com/report"} >> [self:write]{path: "report.html"}\n$ok = 1} [catch]{[self:notify_user]{message: "$tries 번째 시도 실패: $error.summary"}}}',
     "sense,self", "web", "while,카운터,try,재시도"),
    ("주간 보고 워크플로우로 저장해줘 — 수집·요약은 하되 반환은 요약 표로",
     "[self:workflow]{op: \"save\", name: \"주간 부동산 보고\", do: \"$return = [sense:realty]{source: 'naver', region: '죽백동', deal: 'lease'} >> [table:take]{n: 10}\\n[table:brief]{items: '$return', instruction: '주간 요지 5문장'} >> [self:notify_user]{}\"}",
     "self,sense,table", "realty", "workflow,return,저장"),
    ("저장한 주간 보고 돌려서 결과 표를 스프레드시트로",
     '[self:workflow]{op: "run", name: "주간 부동산 보고"} >> [table:spreadsheet]{path: "주간보고.xlsx"}',
     "self,table", "realty", "workflow,run,return,스프레드시트"),
    ("기사 중 긴급 표시 몇 건인지 세서 3건 넘으면 텔레그램",
     '$r = [sense:search]{source: "gnews", query: "청주 화재"} >> [table:filter]{where: {title: {contains: "긴급"}}}\n$k = count($r)\n[if: $k > 3]{[others:channel_send]{channel_type: "telegram", body: "긴급 기사 $k 건"}}',
     "sense,table,others", "web", "식할당,count,조건,알림"),
    ("페이지 3장 모아 중복 빼고 제목만 알려줘",
     '[repeat: 3, collect: true]{[sense:feed]{url: "https://news.hada.io/rss/news?page=$i"}} >> [table:dedup]{by: "title"} >> [table:select]{columns: ["title"]} >> [self:notify_user]{}',
     "sense,table,self", "web", "repeat,collect,블록인파이프,dedup"),
    ("잔여 예산 계산해서 0 이하면 경고",
     '$spent = [self:finance]{op: "summary", month: "2026-08"} >> [table:reduce]{init: 0, step: "acc + amount"}\n$left = 3000000 - $spent.value\n[if: $left <= 0]{[self:notify_user]{message: "이달 예산 초과: $left 원"}} [else]{[self:notify_user]{message: "남은 예산 $left 원"}}',
     "self,table", "finance", "식할당,reduce,예산,조건"),
]

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
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
