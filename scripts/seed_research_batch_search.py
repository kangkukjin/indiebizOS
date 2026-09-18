#!/usr/bin/env python3
"""seed_research_batch_search.py — 조사 의도의 묶음 검색 시드 (2026-09-18, ep3854 수리).

배경: "…어떤 식으로 도입하는지 조사해줘" 같은 조사 요청은 해마 점수가 0.30 이라 용례가 하나도 실리지 않았고,
실행자는 검색 26건을 한 건씩 호출했다(같은 날 ep3853 은 회상된 묶음 골격을 따라 한 호출에 여러 검색을 던졌다 —
묶는 습관이 회상에 달려 있었다). `queries` 배치를 모든 소스로 넓힌 것(web handler `_batch_search`)과 짝이다.
조사 의도의 말씨(조사해줘·알아봐줘·어떻게 하는지·사례·동향·비교)를 실제 요청 모양 그대로 싣는다.
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: E402,F401
from ibl_parser import parse as parse_ibl  # noqa: E402
from ibl_usage_db import IBLUsageDB  # noqa: E402

TOPIC = "웹 검색·크롤링"
TAIL = ' ⏎ $후보 >> [table:union]{} >> [table:dedup]{by: "url"} >> [table:select]{fields: ["title", "url", "summary", "query"]}'


def _two(ko, en, limit=5):
    k = ", ".join(f'"{q}"' for q in ko)
    e = ", ".join(f'"{q}"' for q in en)
    return (f'$후보 = [sense:search]{{source: "naver", queries: [{k}], limit: {limit}}} & '
            f'[sense:search]{{source: "ddg", queries: [{e}], limit: {limit}}}' + TAIL).replace(" ⏎ ", "\n")


def _one(source, qs, limit=5):
    k = ", ".join(f'"{q}"' for q in qs)
    return (f'[sense:search]{{source: "{source}", queries: [{k}], limit: {limit}}} >> [table:dedup]{{by: "url"}} '
            f'>> [table:select]{{fields: ["title", "url", "summary", "query"]}}')


# (intent, code, tags)
NEW = [
    ("사람들이 기업이나 사무실에 AI를 도입할 때 어떤 식으로 도입하는지 조사해줘",
     _two(["기업 생성형 AI 도입 사례", "사무실 AI 도입 단계 교육 파일럿", "중소기업 AI 도입 실패 요인"],
          ["enterprise generative AI adoption case study", "AI rollout training pilot lessons learned"]), "조사,도입사례"),
    ("요즘 회사들이 재택근무를 어떻게 운영하는지 조사해줘",
     _two(["재택근무 운영 사례 기업", "하이브리드 근무 제도 도입 현황", "재택근무 생산성 조사"],
          ["hybrid work policy case study", "remote work productivity survey"]), "조사,운영사례"),
    ("전기차 배터리 재활용이 지금 어디까지 왔는지 알아봐줘",
     _two(["전기차 배터리 재활용 현황", "폐배터리 재활용 기업 기술", "배터리 재활용 정책 규제"],
          ["EV battery recycling state of the art", "battery recycling capacity forecast"]), "조사,현황"),
    ("소상공인들이 무인 매장을 어떻게 도입하는지 사례를 찾아줘",
     _one("naver", ["무인 매장 도입 사례 소상공인", "무인 점포 창업 비용 후기", "무인 매장 운영 문제점"]), "조사,국내사례"),
    ("노코드 툴로 업무 자동화하는 방법들을 조사해서 비교해줘",
     _two(["노코드 업무 자동화 도구 비교", "노코드 자동화 도입 사례", "업무 자동화 실패 사례"],
          ["no-code workflow automation tools comparison", "Zapier Make n8n comparison"]), "조사,비교"),
    ("이 주제에 대해 여러 각도로 자료를 찾아봐줘 — 고령자 돌봄 로봇",
     _two(["돌봄 로봇 도입 사례 요양원", "고령자 돌봄 로봇 효과 연구", "돌봄 로봇 가격 지원 사업"],
          ["elder care robot deployment study", "care robot acceptance older adults"]), "조사,다각도"),
    ("해외에서는 도시 재생을 어떻게 하는지 사례를 조사해줘",
     _one("ddg", ["urban regeneration case study", "brownfield redevelopment success factors", "community-led regeneration examples"]),
     "조사,해외사례"),
    ("대학들이 생성형 AI 과제 부정행위에 어떻게 대응하는지 알아봐줘",
     _two(["대학 생성형 AI 과제 가이드라인", "챗GPT 표절 대응 대학 정책", "AI 활용 평가 방식 변화"],
          ["university generative AI assessment policy", "academic integrity ChatGPT guidelines"]), "조사,정책"),
    ("중소 제조업체의 스마트공장 도입 과정과 비용을 조사해줘",
     _one("naver", ["스마트공장 도입 과정 중소기업", "스마트공장 구축 비용 지원금", "스마트공장 도입 효과 사례", "스마트공장 실패 원인"]),
     "조사,과정·비용"),
    ("양자컴퓨터 상용화가 어디까지 왔는지 알아봐줘",
     _two(["양자컴퓨터 상용화 현황", "양자컴퓨터 기업 로드맵", "양자 우위 실용 사례"],
          ["quantum computing commercialization status", "quantum advantage practical applications"]), "조사,현황"),
    ("요즘 소형 원자로 개발 동향을 알아봐줘",
     _two(["소형모듈원자로 SMR 개발 동향", "SMR 인허가 상용화 일정", "SMR 경제성 논란"],
          ["small modular reactor deployment timeline", "SMR licensing progress"]), "조사,동향"),
    ("인공 배양육 시장 전망이 어떤지 조사해줘",
     _two(["배양육 시장 전망", "배양육 규제 승인 현황", "배양육 가격 생산 단가"],
          ["cultivated meat market outlook", "cultivated meat regulatory approval"]), "조사,전망"),
    ("키워드 몇 개로 웹을 한 번에 검색해서 중복 없이 모아줘",
     _one("ddg", ["retrieval augmented generation evaluation", "RAG benchmark 2026", "long context vs retrieval"]), "묶음검색,중복제거"),
]

for intent, code, _t in NEW:
    try:
        parse_ibl(code)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"파싱 실패: {intent}\n  {code}\n  {e}")
print(f"문법 검증 통과 {len(NEW)}건")

db = IBLUsageDB()
assert db._load_model_sync(), "임베딩 모델 로드 실패 — 시딩 중단"
with db._get_connection() as conn:
    have = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples WHERE source = 'seed'")}
rows = [{"intent": i, "ibl_code": c, "nodes": "sense,table", "category": "pipeline", "difficulty": 2,
         "source": "seed", "tags": t, "topic": TOPIC} for i, c, t in NEW if i not in have]   # 다시 돌려도 겹치지 않는다
print(f"이미 있는 시드 {len(NEW) - len(rows)}건 건너뜀")
added = db.add_examples_batch(rows)
print(f"추가 {added}건 / 요청 {len(rows)}건")
