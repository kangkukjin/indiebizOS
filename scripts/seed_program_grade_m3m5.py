#!/usr/bin/env python3
"""seed_program_grade_m3m5.py — 프로그램급 IBL M3·M4·M5 조합 시드 (2026-08-22).

try/catch·on_error·?? 괄호 가지·repeat·reduce·spill 이 **한 문장**이 되는 용례. 어휘 증가 = reduce 1(기능어).
★함정: add 전에 _load_model_sync(). ★nodes=콤마 문자열. usage db·distilled 둘 다 intent 로 dedupe.
실행: .venv/bin/python3 scripts/seed_program_grade_m3m5.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── try/catch/finally ──
    ("이 페이지 크롤링해서 구조화하고, 안 되면 네이버 검색으로 대신하고, 끝나면 알려줘",
     '[try]{[sense:crawl]{url: "https://example.com/post/1"} >> [self:struct]{schema: "제목, 날짜, 본문"}}\n'
     '[catch]{[sense:search]{source: "naver", query: "example post 1"}}\n'
     '[finally]{[self:notify_user]{message: "수집 시도 끝: $error.summary"}}',
     "sense,self", "web", "try,catch,finally,크롤링"),
    ("주가 조회가 실패하면 검색으로 대체해서 첫 결과만 보여줘",
     '[sense:stock]{op: "quote", ticker: "AAPL"} ?? ([sense:search]{query: "AAPL 주가"} >> [table:take]{n: 1})',
     "sense,table", "finance", "폴백,괄호가지"),
    ("뉴스 수집해서 AI 요약이 실패해도 원본은 저장되게 해줘",
     '[on_error: skip] [sense:search]{source: "gnews", query: "반도체 수출"} >> [table:ai]{instruction: "광고·중복 제거"} >> [self:write]{path: "반도체_뉴스.json"}',
     "sense,table,self", "web", "on_error,skip,저장"),
    ("매물 조회가 죽어도 빈 표라도 스프레드시트로 만들어줘",
     '[on_error: null] [sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [table:spreadsheet]{path: "죽백동_전세.xlsx"}',
     "sense,table", "realty", "on_error,null,스프레드시트"),
    # ── repeat ──
    ("긴 렌더 스크립트 돌리고 끝날 때까지 10초마다 확인해줘",
     '$job = [self:script]{op: "run", id: "render_video", background: true}\n'
     '[repeat: until $st.status == "done", max: 30, every: "10s"]{$st = [self:script]{op: "status", job_id: "$job.job_id"}}',
     "self", "system", "repeat,until,대기,스크립트"),
    ("AI 뉴스 3페이지까지 모아서 중복 빼고 저장해줘",
     '[table:each]{items: [{page: 1}, {page: 2}, {page: 3}], collect: true, do: "[sense:feed]{url: \'https://news.hada.io/rss/news?page=$it.page\'}"} >> [table:dedup]{by: "title"} >> [self:write]{path: "AI뉴스_3페이지.json"}',
     "sense,table,self", "web", "each,collect,페이지"),
    ("새 글이 없어질 때까지 피드 검침 반복해서 전부 모아줘",
     '$f = [sense:feed]{url: "https://news.hada.io/rss/news"} >> [table:since]{key: "하다뉴스"}\n'
     '[repeat: while count($f) > 0, max: 5, collect: true]{$f = [sense:feed]{url: "https://news.hada.io/rss/news"} >> [table:since]{key: "하다뉴스"}}',
     "sense,table", "web", "repeat,while,검침"),
    # ── reduce ──
    ("죽백동 전세 매물 보증금 총합 구해줘",
     '[sense:realty]{source: "naver", region: "죽백동", deal: "lease"} >> [table:reduce]{init: 0, step: "acc + 보증금", as: "총보증금"}',
     "sense,table", "realty", "reduce,합계,누적"),
    ("검색 결과 제목들을 쉼표로 이어서 한 줄로 만들어줘",
     '[sense:search]{query: "청주 맛집"} >> [table:take]{n: 5} >> [table:reduce]{init: "", step: "acc + title + \\", \\"", as: "제목모음"}',
     "sense,table", "web", "reduce,문자열,이어붙이기"),
    ("매물 중 최고가가 얼마인지 알려주고 3억 넘으면 경고해줘",
     '$m = [sense:realty]{source: "zigbang", region: "죽백동", type: "villa"} >> [table:reduce]{init: 0, step: "max(acc, price)", as: "최고가"}\n'
     '[if: $m.value > 30000]{[self:notify_user]{message: "최고가 $m.value 만원 — 3억 초과"}}\n'
     '[else]{[self:notify_user]{message: "최고가 $m.value 만원"}}',
     "sense,table,self", "realty", "reduce,max,조건,변수"),
    # ── 스필 + 재개 관용 ──
    ("대량 파일 목록은 파일로 내려놓고 상위 10개만 보여줘",
     '[self:file_find]{pattern: "**/*.pdf", path: "~/Documents"} >> [self:write]{path: "pdf_전체목록.json", spill: true}\n'
     '[self:read]{path: "pdf_전체목록.json"} >> [table:take]{n: 10}',
     "self,table", "system", "스필,write,read,목록"),
    ("큰 통계 데이터 받아서 정렬하고 상위 20개 차트로",
     '[sense:kosis]{query: "시군구 인구"} >> [table:sort]{by: "value", desc: true} >> [table:take]{n: 20} >> [table:chart]{type: "bar", x: "region", y: "value"}',
     "sense,table", "stats", "파이프,정렬,차트,자동스필"),
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
