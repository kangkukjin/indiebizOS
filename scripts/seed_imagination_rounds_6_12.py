#!/usr/bin/env python3
"""seed_imagination_rounds_6_12.py — 상상훈련 6~12회차 시드 일괄 (2026-08-17).

각 회차 보고서의 '시드 후보(실행 검증 통과만)' 절에서 승격 — 관문: 실측 통과 + 갭 제약 없음.
placeholder(…)는 회차의 실제 프로브 값으로 구체화. 파라미터는 코퍼스·레지스트리 관용 준수.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
★nodes=콤마 문자열. 같은 intent 재실행 방지를 위해 usage db·distilled 둘 다 intent 로 dedupe.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

# (intent, code, nodes, category, tags)
NEW = [
    # ── 6회차 ──
    ("구글뉴스 안 되면 네이버로라도 AI 규제 뉴스 검색해줘",
     '[sense:search]{source: "gnews", query: "AI 규제"} ?? [sense:search]{source: "naver", query: "AI 규제"} >> [table:take]{n: 3}',
     "sense,table", "web", "폴백,검색"),
    ("GPS 있는 내 사진 3장 지도에 찍어줘",
     '[self:photo]{has_gps: true, limit: 20} >> [table:take]{n: 3} >> [limbs:show_map]{markers: "$items"}',
     "self,table,limbs", "photo", "사진,지도"),
    ("메모에서 회의 관련 내용 찾아줘",
     '[self:memory]{op: "search", query: "회의"} >> [table:take]{n: 1}',
     "self,table", "memory", "메모,검색"),
    ("청주 브이로그 유튜브 3건 보여줘",
     '[sense:search_youtube]{query: "청주 브이로그"} >> [table:take]{n: 3}',
     "sense,table", "media", "유튜브"),
    ("이순신 관련 정보 위키데이터에서 찾아줘",
     '[sense:entity]{query: "이순신"} >> [table:take]{n: 3}',
     "sense,table", "knowledge", "개체해소"),
    ("파이썬 asyncio 공식 문서 찾아줘",
     '[sense:devdocs]{op: "search", query: "asyncio", library_name: "python"} >> [table:take]{n: 3}',
     "sense,table", "dev", "문서"),
    ("근처 CCTV 3개 지도에 보여줘",
     '[sense:cctv]{op: "webcam", lat: 36.62, lng: 127.33} >> [table:take]{n: 3} >> [limbs:show_map]{markers: "$items"}',
     "sense,table,limbs", "cctv", "지도"),
    ("에이전트 누구누구 있는지 프로젝트랑 이름만 보여줘",
     '[others:agents] >> [table:take]{n: 5} >> [table:select]{columns: ["project", "name"]}',
     "others,table", "agents", "명부"),
    ("볼륨별 용량 큰 순으로 정리해줘",
     '[self:storage]{op: "summary"} >> [table:sort]{by: "total_size_mb", desc: true}',
     "self,table", "storage", "디스크"),
    ("긱뉴스 피드 최신 기사 파일로 받아둬",
     "[sense:feed]{url: \"https://news.hada.io/rss/news\"} >> [table:take]{n: 1} >> [table:each]{do: \"[self:download]{url: '$it.url'}\"}",
     "sense,table,self", "web", "피드,다운로드,적용"),
    # ── 7회차 ──
    ("긱뉴스 피드 안 되면 BBC 피드로라도 3개 보여줘",
     '[sense:feed]{url: "https://news.hada.io/rss/news"} ?? [sense:feed]{url: "https://feeds.bbci.co.uk/news/rss.xml"} >> [table:take]{n: 3}',
     "sense,table", "web", "폴백,피드"),
    ("폰에서 시간 확인해봐",
     '[self:time]@폰-9f2b', "self", "body", "몸라우팅"),
    ("가족용 자유게시판 만들어줘",
     '[others:bulletin]{op: "create", title: "가족 게시판"}', "others", "bulletin", "게시판"),
    ("공개 중인 폴더 뭐 있어?",
     '[others:showcase]{op: "status"} >> [table:take]{n: 5}', "others,table", "share", "공개파일"),
    # ── 8회차 ──
    ("폰한테 지금 몇 시냐고 물어봐",
     '[others:ask]{to: "폰-9f2b", message: "지금 몇 시야?"}', "others", "body", "몸간부탁"),
    ("15초 뒤에 알려줘",
     "[self:schedule]{seconds: 15, do: \"[self:notify_user]{message: '요청하신 시간입니다'}\"}",
     "self", "time", "지연,알림"),
    ("지금 화면 찍어줘",
     '[limbs:screen]{op: "screenshot"}', "limbs", "screen", "스크린샷"),
    ("커뮤니티 보드 뭐 있어?",
     '[others:board]{op: "list"}', "others", "community", "보드"),
    ("파인만 강의 영상 찾아서 정보 자세히 보여줘",
     "[sense:search_youtube]{query: \"파인만 강의\"} >> [table:take]{n: 1} >> [table:each]{do: \"[sense:video]{op: 'info', url: '$it.url'}\"}",
     "sense,table", "media", "유튜브,적용"),
    # ── 9회차 ──
    ("코스피 높으면 관련 뉴스 2건만 보여줘",
     '[if: sense:stock{op: "quote", ticker: "^KS11"}.data.current_price > 1000]{[sense:search]{source: "gnews", query: "코스피"} >> [table:take]{n: 2}}',
     "sense,table", "invest", "조건,블록파이프"),
    ("시간 보고, 청주 날씨도 알려줘",
     '[self:time]; [sense:weather]{city: "청주"}', "self,sense", "daily", "독립문장"),
    ("내 블로그에서 기억에 관한 글 찾아줘",
     '[self:blog]{op: "search", mode: "semantic", query: "기억"} >> [table:take]{n: 3}',
     "self,table", "blog", "시맨틱"),
    ("설치된 패키지 보여줘",
     '[self:package]{op: "list"} >> [table:take]{n: 5}', "self,table", "meta", "패키지"),
    ("경량 AI한테 바로 물어봐줘",
     '[self:ask]{prompt: "오늘 집중할 일 한 줄 추천"}', "self", "meta", "경량질의"),
    # ── 10회차 (문법 축 완주분) ──
    ("비트코인, 코스피, 이더리움 시세 한 표로 보여줘",
     '[sense:crypto]{coin: "bitcoin"} & [sense:stock]{op: "quote", ticker: "^KS11"} & [sense:crypto]{coin: "ethereum"} >> [table:union]{}',
     "sense,table", "invest", "3항병렬"),
    ("맥이랑 폰 시간 동시에 알려줘",
     '[self:time] & [self:time]@폰-9f2b', "self", "body", "병렬,몸라우팅"),
    ("코스피 2400 밑이면 방어 목표 걸어줘",
     '[if: sense:stock{op: "quote", ticker: "^KS11"}.data.current_price < 2400]{[goal: "방어적 포트폴리오 점검"]{max_rounds: 10}}',
     "sense,self", "invest", "조건,목표"),
    # ── 11회차 ──
    ("삼성전자 기업정보랑 최근 공시 한눈에 보여줘",
     '[sense:company]{op: "profile", market: "kr", query: "삼성전자"} & [sense:company]{op: "disclosures", market: "kr", query: "삼성전자"} >> [table:union]{}',
     "sense,table", "invest", "기업,병렬"),
    ("다나와에서 무선 청소기 30만원 이하만 싸게 5개 골라줘",
     '[sense:search_shopping]{query: "무선 청소기"} >> [table:filter]{where: {field: "price", op: "le", value: 300000}} >> [table:sort]{by: "price"} >> [table:take]{n: 5}',
     "sense,table", "shopping", "가격비교,필터"),
    ("이순신이랑 세종대왕 위키데이터에서 동시에 찾아줘",
     '[sense:entity]{op: "resolve", query: "이순신"} & [sense:entity]{op: "resolve", query: "세종대왕"} >> [table:union]{}',
     "sense,table", "knowledge", "개체해소,병렬"),
    ("FastAPI 웹소켓 공식 문서 찾아서 파일로 저장해줘",
     '[sense:devdocs]{op: "search", query: "WebSocket", library_name: "fastapi"} >> [self:write]{path: "outputs/fastapi_websocket.md"}',
     "sense,self", "dev", "문서,축적"),
    ("디스크 사용률 90% 넘으면 자원 점유 프로세스 보여줘",
     '[if: sense:host{op: "status"}.disk_root.percent > 90]{[sense:host]{op: "apps"}} [else]{[sense:host]{op: "resources"}}',
     "sense", "system", "조건"),
    ("매일 아침 8시에 세계 브리핑 알림 걸어줘",
     "[self:trigger]{op: \"create\", name: \"아침 세계 브리핑\", cron: \"0 8 * * *\", do: \"[sense:world]{} >> [self:notify_user]{message: '아침 세계 브리핑'}\"}",
     "self,sense", "time", "트리거,시간문형"),
    ("커뮤니티 피드 최근 글 3개 보여줘",
     '[others:feed]{op: "read"} >> [table:take]{n: 3}', "others,table", "community", "피드"),
    ("내 에이전트 명부 보여줘",
     '[others:agents]{} >> [table:take]{n: 5}', "others,table", "agents", "명부"),
    ("다가오는 일정 5개 보여줘",
     '[self:manage_events]{op: "list"} >> [table:take]{n: 5}', "self,table", "time", "일정"),
    # ── 12회차 ──
    ("출산율 통계 찾아줘",
     '[sense:kosis]{query: "출산율"} >> [table:take]{n: 5}', "sense,table", "stats", "통계"),
    ("공연이랑 전시 한 표로 정리해줘, 중복은 빼고",
     '[sense:performance]{query: "뮤지컬"} & [sense:exhibit]{query: "미술"} >> [table:union]{} >> [table:dedup]{by: "title"} >> [table:take]{n: 5}',
     "sense,table", "culture", "병렬,중복제거"),
    ("고전 원문에서 난중일기 찾아줘",
     '[sense:classic]{op: "korean", query: "난중일기"} >> [table:take]{n: 3}', "sense,table", "culture", "고전"),
    ("최근 일주일 세계 상황 추이 보여줘",
     '[sense:world]{op: "trend", days: 7} >> [table:take]{n: 5}', "sense,table", "world", "추이"),
    ("받은 메시지 최근 3개 보여줘",
     '[others:messages]{op: "inbox"} >> [table:take]{n: 3}', "others,table", "messenger", "수신함"),
    ("이웃 목록 보여줘",
     '[others:neighbor]{op: "list"} >> [table:take]{n: 5}', "others,table", "neighbor", "이웃"),
    ("이 웹페이지 받아서 읽어줘",
     '[self:download]{url: "https://example.com/", path: "outputs/page.html"} >> [self:read]{}',
     "self", "file", "다운로드,읽기"),
    ("메모리 사용률 95% 넘으면 프로세스 점검해줘",
     '[if: sense:host{op: "status"}.memory.percent > 95]{[sense:host]{op: "apps"}} [else]{[sense:host]{op: "resources"}}',
     "sense", "system", "조건"),
    ("자동응답 상태 보고, 연결된 손발도 보여줘",
     '[others:auto_response]{op: "status"} ; [self:limb]{op: "list"}', "others,self", "system", "독립문장"),
    ("매주 월요일 9시에 주간 브리핑 걸어줘",
     "[self:trigger]{op: \"create\", name: \"주간 브리핑\", cron: \"0 9 * * 1\", do: \"[sense:world]{} >> [self:notify_user]{message: '주간 브리핑'}\"}",
     "self,sense", "time", "트리거,주간"),
    ("팔로우 목록 보여줘",
     '[others:follow]{op: "list"}', "others", "community", "팔로우"),
    ("내 노스트 프로필 보여줘",
     '[others:nostr]{op: "profile"}', "others", "community", "노스트"),
    ("폰에 최근 알림 뭐 왔어?",
     '[sense:phone]{op: "notifications"} >> [table:take]{n: 3}', "sense,table", "body", "폰알림"),
    ("근처 CCTV 목록 보여줘",
     '[sense:cctv]{op: "nearby", lat: 36.62, lng: 127.33} >> [table:take]{n: 3}', "sense,table", "cctv", "근처"),
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
