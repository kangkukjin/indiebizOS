#!/usr/bin/env python3
"""seed_program_grade_m1m2.py — 프로그램급 IBL M1·M2 조합 시드 (2026-08-22).

술어 언어(`$변수` 좌변·count/empty/exists·matches·and/or/not·AI 술어)와 스필 싱크가 **한 문장**
이 되는 용례를 심는다 — 08-21 진단에서 `[if:]` 표본이 1회(실패)였던 자리. 다단계는 한 시드 안에
파이프라인으로(단발 시드=역효과, reflex-veto 선례). 어휘 증가 0(문법만).
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
★nodes=콤마 문자열. usage db·distilled 둘 다 intent 로 dedupe.
실행: .venv/bin/python3 scripts/seed_program_grade_m1m2.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    # ── $변수 + count/empty ──
    ("청주 부동산 뉴스 검색해서 결과가 있으면 알려주고 없으면 네이버로 다시 찾아줘",
     '$r = [sense:search]{source: "gnews", query: "청주 부동산"}\n'
     '[if: count($r) > 0]{[table:brief]{items: "$r", instruction: "핵심 3문장"} >> [self:notify_user]{}}\n'
     '[else]{[sense:search]{source: "naver", query: "청주 부동산"} >> [table:brief]{instruction: "핵심 3문장"} >> [self:notify_user]{}}',
     "sense,table,self", "web", "조건,변수,count,폴백"),
    ("죽백동 전세 매물 찾아서 하나도 없으면 나한테 알려줘",
     '$m = [sense:realty]{source: "naver", region: "죽백동", deal: "lease"}\n'
     '[if: empty($m)]{[self:notify_user]{message: "죽백동 전세 매물 0건"}}\n'
     '[else]{[table:take]{items: "$m", n: 5} >> [self:notify_user]{}}',
     "sense,self,table", "realty", "조건,변수,empty"),
    # ── matches 정규식 ──
    ("긱뉴스 새 글 중에 제목에 AI나 LLM 들어간 게 있으면 텔레그램으로 보내줘",
     '$f = [sense:feed]{url: "https://news.hada.io/rss/news"} >> [table:since]{key: "하다뉴스"}\n'
     '[if: count($f) > 0 and $f.items.0.title matches "AI|LLM"]{[others:channel_send]{channel_type: "telegram", body: "$f.items.0.title"}}',
     "sense,table,others", "web", "조건,정규식,matches,피드"),
    # ── 소스 참조 + and/or ──
    ("CPU가 80 넘고 메모리도 90 넘으면 경고해줘",
     '[if: sense:host{op: "status"}.cpu_percent > 80 and sense:host{op: "status"}.memory.percent > 90]{[self:notify_user]{message: "CPU·메모리 동시 과부하"}}',
     "sense,self", "system", "조건,and,호스트"),
    ("업무시간(9시~18시)이면 슬랙으로, 아니면 텔레그램으로 보내줘",
     '[if: self:time.hour >= 9 and self:time.hour < 18]{[others:channel_send]{channel_type: "slack", body: "업무 알림"}}\n'
     '[else]{[others:channel_send]{channel_type: "telegram", body: "업무 알림"}}',
     "self,others", "time", "조건,and,시간"),
    # ── exists ──
    ("검색 첫 결과에 링크가 있으면 그 페이지 크롤링해서 요약해줘",
     '$s = [sense:search]{query: "M4 맥미니 리뷰"}\n'
     '[if: exists($s.items.0.url)]{[sense:crawl]{url: "$s.items.0.url"} >> [table:brief]{instruction: "5문장 요약"}}\n'
     '[else]{[self:notify_user]{message: "크롤링할 링크 없음"}}',
     "sense,table,self", "web", "조건,exists,크롤링"),
    # ── AI 술어 ──
    ("기사들이 청주 부동산과 직접 관련 있을 때만 보고서로 저장해줘",
     '$n = [sense:search]{source: "gnews", query: "청주 아파트"}\n'
     '[if: [table:brief]{items: "$n", instruction: "이 기사들이 청주 부동산과 직접 관련 있으면 yes, 아니면 no 한 단어로"} == "yes"]{[table:brief]{items: "$n", instruction: "청주 부동산 동향 보고서 10문장"} >> [self:write]{path: "청주_부동산_동향.md"}}\n'
     '[else]{[self:notify_user]{message: "관련 기사 없음 — 저장 안 함"}}',
     "sense,table,self", "web", "조건,AI술어,brief"),
    ("이 메일이 결제 관련이면 재무 장부에 넣어줘",
     '$mail = [others:channel_read]{channel_type: "email", limit: 1}\n'
     '[if: [table:brief]{items: "$mail", instruction: "결제·청구·영수증 메일이면 yes 아니면 no"} == "yes"]{[self:finance]{op: "ingest", items: "$mail"}}',
     "others,table,self", "finance", "조건,AI술어,메일"),
    # ── case $변수 소스 ──
    ("코스피가 2400 밑이면 매수 알림, 2600 위면 매도 알림",
     '$k = [sense:stock]{op: "quote", ticker: "^KS11"}\n'
     '[case: $k.data.current_price]{"<2400": [self:notify_user]{message: "코스피 2400 하회 — 매수 검토"}, ">2600": [self:notify_user]{message: "코스피 2600 상회 — 매도 검토"}, default: [self:time]}',
     "sense,self", "finance", "case,변수,주가"),
    # ── not / 괄호 ──
    ("당근에 자전거 매물이 있는데 가격이 10만원 넘지 않으면 알려줘",
     '$u = [sense:used]{source: "danggeun", q: "자전거"}\n'
     '[if: not empty($u) and ($u.items.0.price < 100000 or $u.items.0.price == null)]{[self:notify_user]{message: "$u.items.0.title"}}',
     "sense,self", "shopping", "조건,not,괄호,중고"),
    # ── 스필 싱크 ──
    ("검색 결과 원본은 파일로 내려놓고 요약만 알려줘",
     '[sense:search]{query: "반도체 수출 통계"} >> [self:write]{path: "반도체_원본.json", spill: true}\n'
     '[self:read]{path: "반도체_원본.json"} >> [table:brief]{instruction: "핵심 3문장"} >> [self:notify_user]{}',
     "sense,self,table", "web", "스필,write,read"),
    ("매물 전부 저장해두고 상위 3개만 보여줘",
     '$all = [sense:realty]{source: "zigbang", region: "죽백동", type: "villa"}\n'
     '[self:write]{path: "죽백동_빌라_전체.json", content: "$all", spill: true}\n'
     '[table:take]{items: "$all", n: 3}',
     "sense,self,table", "realty", "스필,변수,take"),
    # ── 트리거 안의 조건(정기 감시가 한 문장) ──
    ("매일 아침 8시에 새 전세 매물 있으면 텔레그램으로 보내줘",
     "[self:trigger]{op: \"create\", name: \"죽백동 전세 감시\", cron: \"0 8 * * *\", do: \"$m = [sense:realty]{source: 'naver', region: '죽백동', deal: 'lease'} >> [table:since]{key: '죽백동전세'}\\n[if: count($m) > 0]{[others:channel_send]{channel_type: 'telegram', body: '$m.items.0.title'}}\"}",
     "self,sense,table,others", "time", "트리거,조건,변수,검침"),
    ("디스크가 90% 넘으면 outputs 정리하고 알려줘",
     '[if: sense:host{op: "status"}.disk.percent > 90]{[self:file_find]{pattern: "outputs/**/*.tmp"} >> [self:delete]{} >> [self:notify_user]{message: "임시 파일 정리 완료"}}\n'
     '[else]{[self:notify_user]{message: "디스크 여유 있음"}}',
     "sense,self", "system", "조건,호스트,정리"),
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
skipped = len(NEW) - len(batch)
n_added = db.add_examples_batch(batch)
print(f"시드 추가: {n_added}건 (중복 스킵 {skipped}건)")

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
