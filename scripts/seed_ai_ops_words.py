"""ai-ops 원샷 낱말 해마 시딩 (2026-08-19, 체크리스트 3·4단계).

★파이프라인 모양으로 시드(단발 시드=반사 오발 역효과 — reflex-veto 교훈) + 대조 시드
 (기존 결정론 어휘의 영토 보존: read{tables}·sort·ask·document).
★실행: .venv 파이썬 필수(sqlite_vec) + _load_model_sync 후 색인(벡터 침묵 누락 함정).
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
import boot_paths  # noqa: F401

SEEDS = [
    # ── 입구 [self:struct] ──
    {"intent": "이 영수증 사진에서 지출 내역을 뽑아 정리해줘",
     "ibl_code": '[self:struct]{file: "영수증.jpg", schema: "finance"}', "nodes": "self"},
    {"intent": "이 웹페이지에서 행사 목록을 뽑아줘",
     "ibl_code": '[sense:crawl]{url: "https://example.com/events"} >> [self:struct]{schema: "행사명, 날짜, 장소"}',
     "nodes": "sense,self"},
    {"intent": "회의록 텍스트에서 할 일 목록을 추출해서 기한순으로 보여줘",
     "ibl_code": '[self:struct]{text: "회의록 본문...", schema: "할일, 담당자, 기한"} >> [table:sort]{by: "기한"}',
     "nodes": "self,table"},
    {"intent": "안내문 파일에서 일정만 구조화해서 표로 정리해줘",
     "ibl_code": '[self:struct]{file: "안내문.pdf", schema: "일정명, 날짜, 장소"} >> [table:document]{}',
     "nodes": "self,table"},
    # ── 중간 [table:ai] ──
    {"intent": "검색 결과에서 광고성 글은 빼줘",
     "ibl_code": '[sense:search]{query: "청주 맛집", source: "naver"} >> [table:ai]{instruction: "광고성 행 제거"}',
     "nodes": "sense,table"},
    {"intent": "매물 중에 리모델링 언급된 것만 골라줘",
     "ibl_code": '[sense:realty]{source: "naver", region: "오송"} >> [table:ai]{instruction: "리모델링이 언급된 매물만"}',
     "nodes": "sense,table"},
    {"intent": "기사마다 한 줄 요약을 붙여줘",
     "ibl_code": '[sense:search]{source: "gnews", query: "AI 규제"} >> [table:ai]{instruction: "각 행에 summary 필드로 한 줄 요약 추가"}',
     "nodes": "sense,table"},
    {"intent": "이 목록에서 실제 지원사업 공고만 남기고 마감일 필드를 붙여줘",
     "ibl_code": '[sense:search]{query: "창업 지원", source: "naver"} >> [table:ai]{instruction: "실제 지원사업 공고만 남기고 마감일 필드 추가"} >> [table:sort]{by: "마감일"}',
     "nodes": "sense,table"},
    # ── 출구 [table:brief] ──
    {"intent": "뉴스 검색해서 세 문장으로 보고해줘",
     "ibl_code": '[sense:search]{source: "gnews", query: "반도체 수출"} >> [table:brief]{instruction: "3문장 보고"}',
     "nodes": "sense,table"},
    {"intent": "관심 종목 시세를 조회해서 급변한 것 중심으로 요약해줘",
     "ibl_code": '[sense:stock]{op: "quote", symbols: ["005930", "000660"]} >> [table:brief]{instruction: "어제 대비 급변 종목 중심 요약"}',
     "nodes": "sense,table"},
    {"intent": "매물 다섯 개 중에 어떤 게 제일 나은지 판단해줘",
     "ibl_code": '[sense:realty]{source: "zigbang", region: "오송", deal: "lease"} >> [table:take]{n: 5} >> [table:brief]{instruction: "조건에 최적인 매물 판정과 이유"}',
     "nodes": "sense,table"},
    {"intent": "검색해서 광고 빼고 핵심 요약을 파일로 저장해줘",
     "ibl_code": '[sense:search]{query: "청주 부동산 동향", source: "naver"} >> [table:ai]{instruction: "광고성 행 제거"} >> [table:brief]{instruction: "핵심 동향 요약"} >> [self:write]{path: "outputs/동향요약.md"}',
     "nodes": "sense,table,self"},
    # ── 대조 시드 (기존 어휘 영토 보존) ──
    {"intent": "이 PDF에서 표를 뽑아줘",
     "ibl_code": '[self:read]{path: "문서.pdf", tables: true}', "nodes": "self"},
    {"intent": "결과를 가격순으로 정렬해줘",
     "ibl_code": '[sense:used]{q: "자전거", source: "bunjang"} >> [table:sort]{by: "price"}', "nodes": "sense,table"},
    {"intent": "이 글 요약해줘",
     "ibl_code": '[self:ask]{prompt: "다음 글을 세 줄로 요약: ..."}', "nodes": "self"},
    {"intent": "검색 결과를 보고서 문서로 만들어줘",
     "ibl_code": '[sense:search]{query: "전기차 시장"} >> [table:document]{title: "전기차 시장 조사"}', "nodes": "sense,table"},
]


def main():
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    db._load_model_sync()          # ★벡터 침묵 누락 함정 — 모델 동기 로드 후 색인
    rows = [{"intent": s["intent"], "ibl_code": s["ibl_code"], "nodes": s["nodes"],
             "source": "manual_seed", "tags": "ai-ops"} for s in SEEDS]
    n = db.add_examples_batch(rows)
    print(f"add_examples_batch: {n}")

    # 학습 JSON append (다음 재학습 대기열)
    p = os.path.join(_ROOT, "data", "training", "ibl_distilled.json")
    dist = json.load(open(p))
    existing = {(d.get("intent"), d.get("ibl_code")) for d in dist}
    added = 0
    for s in SEEDS:
        k = (s["intent"], s["ibl_code"])
        if k not in existing:
            dist.append({"intent": s["intent"], "ibl_code": s["ibl_code"]})
            added += 1
    json.dump(dist, open(p, "w"), ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added} → {len(dist)}")

    # 연상 스팟체크
    for q in ["영수증 사진에서 지출 뽑아줘", "검색 결과에서 광고 빼줘",
              "시세 조회해서 세 문장으로 보고해줘", "이 PDF에서 표를 뽑아줘"]:
        hits = db.search_hybrid(q, top_k=3)
        top = [(h.get("ibl_code", "")[:60], round(h.get("score", 0), 3)) for h in hits[:3]]
        print(f"  Q: {q}\n     {top}")


if __name__ == "__main__":
    main()
