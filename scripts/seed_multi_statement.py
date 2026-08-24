#!/usr/bin/env python3
"""seed_multi_statement.py — `;` 다중 문장 문형 시드 (2026-08-24, 사용자 승인).

배경: `;`(독립 문장)·`$변수` 문장 간 반출·"effect 뒤에도 프로그램은 계속된다"가 기계로는
전부 열려 있는데(라이브 실증 steps 4/4), 코퍼스 용례가 **2건**·최근 에피소드 실사용 **0회**
였다. 에이전트가 문장 하나 끝날 때마다 execute_ibl 을 다시 부르는 왕복 낭비가 기계 부재가
아니라 용례 부재 때문에 일어나고 있었다 — 08-15 판정("미사용=아직 좋은 언어가 못 된 신호,
처방=조합 용례 시딩")의 자리.

★모든 코드는 시드 전 라이브 실행으로 검증했다(발명 필드 방지 — 발명률 5.9% 부류).
★함정: add 전에 _load_model_sync() — 모델이 백그라운드 로딩 중이면 벡터가 조용히 안 붙는다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import boot_paths  # noqa: F401,E402
from ibl_usage_db import IBLUsageDB  # noqa: E402
from ibl.ibl_parser import parse as parse_ibl  # noqa: E402  시드 전 문법 검증

# (intent, code, nodes, category, tags)
NEW = [
    # ── $변수 문장 간 반출 + effect 가 뒤 문장에 온다 ──
    ("이 좌표 주소 확인해서 메모 파일에 적어줘",
     '$주소 = [sense:reverse_geocode]{lat: 37.5665, lon: 126.978} ; '
     '[self:write]{path: "outputs/위치메모.md", content: "여기는 $주소.address"}',
     "sense,self", "compose", "다중문장,변수반출,기록"),
    ("지금 시각을 확인해서 점검 로그에 남겨줘",
     '$지금 = [self:time] ; '
     '[self:write]{path: "outputs/점검로그.md", content: "확인 시각: $지금"}',
     "self", "compose", "다중문장,변수반출,시각"),
    # ── effect 가 가운데 있어도 프로그램은 계속된다 (한 실행 = 여러 문장) ──
    ("초안을 저장하고, 저장된 내용을 되읽어서 확인해줘",
     '[self:write]{path: "outputs/초안.md", content: "1차 초안"} ; '
     '[self:read]{path: "outputs/초안.md"}',
     "self", "compose", "다중문장,쓰기후확인"),
    ("뉴스 3건을 파일로 저장하고, 끝났다고 알림 보내줘",
     '[sense:search]{source: "gnews", query: "AI 에이전트"} >> [table:take]{n: 3} '
     '>> [self:write]{path: "outputs/뉴스요약.md"} ; '
     '[self:notify_user]{title: "뉴스 저장 완료", message: "AI 에이전트 뉴스 3건을 outputs/뉴스요약.md 에 저장했습니다"}',
     "sense,table,self", "compose", "다중문장,파이프후알림"),
    # ── 독립 작업 두 개를 한 번에 (왕복 절약) ──
    ("서울이랑 부산 좌표 주소를 각각 확인해줘 — 한 번에",
     '[sense:reverse_geocode]{lat: 37.5665, lon: 126.978} ; '
     '[sense:reverse_geocode]{lat: 35.1796, lon: 129.0756} >> [table:select]{columns: ["address"]}',
     "sense,table", "compose", "다중문장,독립작업"),
]


def main():
    db = IBLUsageDB()
    if hasattr(db, "_load_model_sync"):
        db._load_model_sync()   # ★벡터가 조용히 안 붙는 함정 방지
    bad = []
    for intent, code, *_ in NEW:
        try:
            parse_ibl(code)
        except Exception as e:
            bad.append((intent, f"{type(e).__name__}: {e}"))
    if bad:
        for i, e in bad:
            print(f"[문법 실패] {i}\n   {e}")
        raise SystemExit("문법 검증 실패 — 시드 중단")

    rows = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat,
             "difficulty": 2, "source": "seed_multi_statement", "tags": t}
            for i, c, n, cat, t in NEW]
    added = db.add_examples_batch(rows)
    print(f"시드 {added}/{len(rows)}건 추가 (거부분은 소유-게이트)")


if __name__ == "__main__":
    main()
