#!/usr/bin/env python3
"""seed_each_literal.py — [table:each] 리터럴 items 팬아웃 시드 (2026-08-21, 사용자 승인).

배경: 08-16~21 에피소드 220건에서 같은 액션을 파라미터만 바꿔 연속 호출한 자리 ~700건
(realty 6~7연속·commercial 4연속·video transcript 4연속·slide 8연속). 기계(`each{items}`)는
이미 있었으나 카탈로그·교재·코퍼스(리터럴 2건)에 광고가 없어 모델이 `&` N번 또는 낱개로 갔다.
이 시드는 실사용에서 실제로 반복된 문형을 그대로 each 리터럴로 접은 것.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB
from ibl.ibl_parser import parse as parse_ibl  # 시드 전 문법 검증

# (intent, code, nodes, category, tags)
NEW = [
    # ── 실사용 반복 자리 그대로(ep1339 부동산 보고서) ──
    ("청주 서원구랑 흥덕구 아파트 전세 실거래 각각 4건씩 뽑아줘",
     '[table:each]{items: [{code: "43112"}, {code: "43113"}], do: "[sense:realty]{source: \'molit\', region_code: \'$it.code\', type: \'apt\', deal: \'rent\'} >> [table:take]{n: 4}"} >> [table:flatten]{}',
     "table,sense", "realty", "팬아웃,리터럴,실거래"),
    ("이 세 단지 매매 실거래를 각각 찾아줘 — 봉명아이파크, 주공6단지, 모아미래도",
     '[table:each]{items: [{name: "봉명아이파크"}, {name: "주공6단지"}, {name: "모아미래도"}], do: "[sense:realty]{source: \'molit\', region_code: \'43113\', type: \'apt\', deal: \'trade\'} >> [table:filter]{where: \'아파트명 == $it.name\'}"} >> [table:flatten]{}',
     "table,sense", "realty", "팬아웃,리터럴,단지"),
    ("충북 청주 구별로 아파트 전세 실거래 훑어줘",
     '[sense:realty]{op: "codes", city: "충북"} >> [table:filter]{where: "청주"} >> [table:each]{do: "[sense:realty]{source: \'molit\', region_code: \'$it.코드\', type: \'apt\', deal: \'rent\'} >> [table:take]{n: 3}"} >> [table:flatten]{}',
     "sense,table", "realty", "코드목록,적용,실거래"),
    ("이 좌표 세 곳 반경 1.5km 상권 업종 분포를 각각 집계해줘",
     '[table:each]{items: [{lat: 36.6371, lng: 127.4394}, {lat: 36.6207, lng: 127.3277}, {lat: 36.6108, lng: 127.4635}], do: "[sense:commercial]{lat: $it.lat, lng: $it.lng, radius: 1500} >> [table:groupby]{by: \'category\'} >> [table:sort]{by: \'count\', desc: true} >> [table:take]{n: 6}"}',
     "table,sense", "realty", "팬아웃,리터럴,상권"),
    # ── ep1340 유튜브 보고서 ──
    ("이 영상 네 개 자막을 각각 받아와",
     '[table:each]{items: [{id: "Xn-gtHDsaPY"}, {id: "_C57BxSXRbU"}, {id: "FhtzROwyung"}, {id: "q8vATE5Jwio"}], do: "[sense:video]{op: \'transcript\', video_id: \'$it.id\'}"}',
     "table,sense", "media", "팬아웃,리터럴,자막"),
    ("키워드 세 개로 유튜브 각각 검색해서 한 표로 모아줘",
     '[table:each]{items: [{q: "새로 나온 AI 도구 2026"}, {q: "new AI tools this month"}, {q: "AI 신규 서비스 후기"}], do: "[sense:search_youtube]{query: \'$it.q\', count: 10}"} >> [table:flatten]{} >> [table:dedup]{by: "url"}',
     "table,sense", "media", "팬아웃,리터럴,유튜브"),
    # ── 투자(ep1325·1355) ──
    ("삼성전자·SK하이닉스·TIGER200 1년 시세를 각각 가져와",
     '[table:each]{items: [{t: "005930"}, {t: "000660"}, {t: "102110"}], do: "[sense:stock]{op: \'history\', ticker: \'$it.t\', period: \'1y\'}"}',
     "table,sense", "invest", "팬아웃,리터럴,시세"),
    ("한국·프랑스·싱가포르 1인당 GDP를 세계은행에서 각각 뽑아 한 표로",
     '[table:each]{items: [{c: "KOR"}, {c: "FRA"}, {c: "SGP"}], do: "[sense:world_bank]{indicator: \'NY.GDP.PCAP.CD\', country: \'$it.c\', date: \'2020:2024\'}"} >> [table:flatten]{}',
     "table,sense", "research", "팬아웃,리터럴,세계은행"),
    ("검색어 세 개로 뉴스 각각 찾아서 합쳐줘",
     '[table:each]{items: [{q: "코스피 반도체 비중"}, {q: "방산 수출 2025 실적"}, {q: "콘텐츠 수출액 2025"}], do: "[sense:search]{source: \'gnews\', query: \'$it.q\', count: 8}"} >> [table:flatten]{}',
     "table,sense", "research", "팬아웃,리터럴,뉴스"),
    ("이 URL 세 개 본문을 각각 읽어와",
     '[table:each]{items: [{u: "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/171986/view"}, {u: "https://gonggam.korea.kr/newsContentView.es?news_id=ec9765ba"}, {u: "https://alphasquare.co.kr/home/insight/posts/5738d338"}], do: "[sense:crawl]{url: \'$it.u\'}"}',
     "table,sense", "research", "팬아웃,리터럴,크롤"),
    # ── 여행(가족 여행 — 이미 & 로 잘 접던 자리, each 형도 병기) ──
    ("수원→춘천, 춘천→속초, 속초→강릉 구간 경로를 각각 알려줘",
     '[table:each]{items: [{o: "수원역", d: "춘천역"}, {o: "춘천역", d: "속초 체스터톤스 호텔"}, {o: "속초 체스터톤스 호텔", d: "강릉 안목해변"}], do: "[sense:navigate_route]{origin: \'$it.o\', destination: \'$it.d\'}"}',
     "table,sense", "travel", "팬아웃,리터럴,경로"),
    ("청주·속초·강릉 날씨 한 번에 보여줘",
     '[table:each]{items: [{city: "청주"}, {city: "속초"}, {city: "강릉"}], do: "[sense:weather]{city: \'$it.city\'}"}',
     "table,sense", "travel", "팬아웃,리터럴,날씨"),
    ("속초·강릉·주문진 물회 맛집을 각각 5곳씩",
     '[table:each]{items: [{r: "속초"}, {r: "강릉"}, {r: "주문진"}], do: "[sense:restaurant]{query: \'$it.r 물회\'} >> [table:take]{n: 5}"} >> [table:flatten]{}',
     "table,sense", "travel", "팬아웃,리터럴,맛집"),
    ("온양온천·수안보·덕산온천 숙소를 같은 날짜로 각각 찾아줘",
     '[table:each]{items: [{r: "온양온천"}, {r: "수안보온천"}, {r: "덕산온천"}], do: "[sense:stay]{region: \'$it.r\', checkin: \'2026-08-22\', checkout: \'2026-08-23\', personal: 4} >> [table:take]{n: 5}"} >> [table:flatten]{}',
     "table,sense", "travel", "팬아웃,리터럴,숙소"),
    # ── 파일·몸 ──
    ("이 파일 세 개를 각각 읽어줘",
     '[table:each]{items: [{p: "outputs/housing_reports/_thesis.md"}, {p: "outputs/housing_reports/_coverage_ledger.json"}, {p: "outputs/housing_reports/db/rotation.json"}], do: "[self:read]{path: \'$it.p\'}"}',
     "table,self", "file", "팬아웃,리터럴,읽기"),
    ("이 세 파일의 git 이력을 각각 보여줘",
     '[table:each]{items: [{p: "backend/api.py"}, {p: "backend/ibl/ibl_parser.py"}, {p: "backend/cognition/prompt_builder.py"}], do: "[self:body]{op: \'file\', path: \'$it.p\', limit: 5}"}',
     "table,self", "system", "팬아웃,리터럴,이력"),
    ("이 패턴 세 개를 backend 에서 각각 grep 해줘",
     '[table:each]{items: [{pat: "_OP_DISPATCHERS"}, {pat: "always_on"}, {pat: "STANDARD_CORE_NODES"}], do: "[self:grep]{pattern: \'$it.pat\', path: \'backend\', max_results: 10}"}',
     "table,self", "system", "팬아웃,리터럴,grep"),
    # ── 대조: 목록이 이미 통화로 오면 items 불요(리터럴은 '네가 방금 정한 목록'일 때만) ──
    ("검색 결과 상위 3개 기사 본문을 각각 읽어와",
     '[sense:search]{source: "gnews", query: "청주 아파트 전세"} >> [table:take]{n: 3} >> [table:each]{do: "[sense:crawl]{url: \'$it.url\'}"}',
     "sense,table", "research", "적용,대조,파이프"),
]

# 문법 검증 — 깨진 문장을 코퍼스에 넣지 않는다
for i, c, *_ in NEW:
    try:
        parse_ibl(c)
    except Exception as e:
        sys.exit(f"파싱 실패: {i}\n  {c}\n  {e}")
print(f"문법 검증 통과 {len(NEW)}건")

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"

import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "ibl_usage.db"))
existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
conn.close()

batch = [
    {"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
     "source": "manual_seed", "tags": t}
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
print(f"ibl_distilled 이관: +{added} → {len(dist)}")
